from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

import discord

from hmwz import events, sqlite_db
from hmwz.i18n import t
from hmwz.modules.basic_module import BasicModule
from hmwz.modules.registry import register

from .overview import DonationOverview
from .repository import DonationRepository, DonationType
from .rush_pricing import (
    RUSH_DURATIONS_HOURS,
    is_rush_donation_open,
    rush_donation_cost,
    rush_zone_index,
)
from .views import (
    DonationAmountModal,
    DonationAmountChoiceView,
    DonationOverviewView,
    DonationRushConfirmationView,
    DonationTimeReductionView,
)

_logger = logging.getLogger(__name__)


@register
class DonationModule(BasicModule):
    """Guild-scoped donation tracking with channel-specific summaries."""

    def __init__(self, guild: discord.Guild, client: discord.Client) -> None:
        super().__init__(guild, client)
        if not isinstance(self.database, sqlite_db.Database):
            raise RuntimeError("Donation module requires a database.")
        self.donations = DonationRepository(self.database)
        self._views: dict[int, DonationOverviewView] = {}
        self._registered_message_ids: set[int] = set()
        self._rush_view_states: dict[int, tuple[bool, int | None]] = {}
        self._maintenance_task: asyncio.Task[None] | None = None

    async def sync(self, startup: bool = False) -> bool:
        """Ensure the donation schema exists."""
        return await self.donations.ensure_schema()

    async def ensure(self) -> bool:
        """Refresh configured overviews and register their persistent views."""
        channels = await self.donations.get_channels(guild=self.guild)
        if not channels:
            return True
        results = await asyncio.gather(
            *(self.compose_overview(channel_id) for channel_id in channels)
        )
        self._ensure_maintenance_task()
        return all(results)

    async def configure_donation(
        self,
        channel_id: int,
        *,
        title: str,
        description: str,
        donation_type: DonationType,
        goal_hours: int | None = None,
        recent_limit: int = 20,
        show_ranking: bool = True,
        rush_start_at: datetime | None = None,
    ) -> bool:
        """Persist the channel's single-unit donation setup and publish it."""
        history_units = await self.donations.get_history_units(
            guild=self.guild, channel_id=channel_id
        )
        if history_units is None or (
            history_units and set(history_units) != {donation_type.unit}
        ):
            _logger.error(
                "%s Cannot change donation unit for channel %s because history "
                "already contains donations with another unit.",
                self.guild.name,
                channel_id,
            )
            return False
        if not await self.donations.configure_channel(
            guild=self.guild,
            channel_id=channel_id,
            title=title,
            description=description,
            goal_hours=goal_hours,
            recent_limit=recent_limit,
            show_ranking=show_ranking,
            rush_start_at=rush_start_at,
        ):
            return False
        if not await self.donations.configure_type(
            guild=self.guild,
            channel_id=channel_id,
            donation_type=donation_type,
        ):
            return False
        result = await self.compose_overview(channel_id)
        if donation_type.kind == "time_reduction":
            self._ensure_maintenance_task()
        return result

    async def remove_channel(self, channel_id: int) -> bool:
        """Remove a channel's setup, messages, and donation history."""
        return await self._remove_channel(channel_id)

    async def delete_channel(self, channel_id: int) -> bool:
        """Permanently remove a channel's setup, messages, and donation history."""
        return await self._remove_channel(channel_id)

    async def _remove_channel(self, channel_id: int) -> bool:
        configuration = await self.donations.get_channel(
            guild=self.guild, channel_id=channel_id
        )
        if configuration is None:
            return False
        channel = self.guild.get_channel(channel_id)
        message_ids = (
            configuration.overview_message_id,
            configuration.ranking_message_id,
        )
        if any(message_id is not None for message_id in message_ids) and not isinstance(
            channel, discord.TextChannel
        ):
            _logger.error(
                "%s Cannot remove donation messages because channel %s is unavailable.",
                self.guild.name,
                channel_id,
            )
            return False

        if not await self.donations.delete_channel(
            guild=self.guild, channel_id=channel_id
        ):
            return False

        view = self._views.pop(channel_id, None)
        self._rush_view_states.pop(channel_id, None)
        if view is not None:
            self.client.remove_view(view)
        for message_id in message_ids:
            if message_id is not None:
                self._registered_message_ids.discard(message_id)

        success = True
        if isinstance(channel, discord.TextChannel):
            for message_id in message_ids:
                if message_id is None:
                    continue
                try:
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                except discord.NotFound:
                    continue
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to remove donation message %s in channel %s.",
                        self.guild.name,
                        message_id,
                        channel_id,
                    )
                    success = False
        return success

    async def start_donation(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        *,
        time_reduction: str | None = None,
    ) -> None:
        """Start a configured donation flow."""
        if channel_id not in await self.donations.get_channels(guild=self.guild):
            await interaction.response.send_message(
                t(interaction, "donation.error.not_configured"), ephemeral=True
            )
            return
        donation_type = await self.donations.get_type(
            guild=self.guild, channel_id=channel_id
        )
        if donation_type is None:
            await interaction.response.send_message(
                t(interaction, "donation.error.not_configured"), ephemeral=True
            )
            return
        if donation_type.kind == "time_reduction":
            configuration = await self.donations.get_channel(
                guild=self.guild, channel_id=channel_id
            )
            now = datetime.now(timezone.utc)
            if (
                configuration is None
                or configuration.rush_start_at is None
                or not is_rush_donation_open(configuration.rush_start_at, now)
            ):
                await interaction.response.send_message(
                    t(interaction, "donation.error.rush_closed"), ephemeral=True
                )
                return
            if time_reduction is None:
                await interaction.response.send_message(
                    t(interaction, "donation.setup.hours_donation_prompt"),
                    view=DonationTimeReductionView(self, channel_id, donation_type),
                    ephemeral=True,
                )
                return
            if time_reduction not in {f"{hours}h" for hours in RUSH_DURATIONS_HOURS}:
                await interaction.response.send_message(
                    t(interaction, "donation.error.choose_time"), ephemeral=True
                )
                return
            hours = int(time_reduction.removesuffix("h"))
            cost = rush_donation_cost(
                started_at=configuration.rush_start_at,
                now=now,
                duration_hours=hours,
            )
            await interaction.response.send_message(
                t(
                    interaction,
                    "donation.rush.confirm",
                    hours=hours,
                    cost=format(cost, "f"),
                ),
                view=DonationRushConfirmationView(
                    self,
                    channel_id,
                    donation_type,
                    hours,
                    cost,
                    configuration.current_cycle,
                    configuration.rush_start_at,
                    now,
                    interaction.user.id,
                ),
                ephemeral=True,
            )
            return
        elif time_reduction is not None:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_type"), ephemeral=True
            )
            return
        if donation_type.input_mode == "choice" and donation_type.choices:
            await interaction.response.send_message(
                t(interaction, "donation.setup.amount_donation_prompt"),
                view=DonationAmountChoiceView(self, channel_id, donation_type),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            DonationAmountModal(self, channel_id, donation_type, time_reduction)
        )

    async def record_donation(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        donation_type: DonationType,
        amount: Decimal,
        *,
        time_reduction: str | None,
    ) -> tuple[bool, bool]:
        """Save a donation and refresh both public messages."""
        guild = interaction.guild
        member = interaction.user
        if (
            guild is None
            or guild.id != self.guild.id
            or not isinstance(member, discord.Member)
            or amount <= 0
            or (donation_type.kind != "simple" or time_reduction is not None)
            or (
                donation_type.input_mode == "choice"
                and amount not in {Decimal(choice) for choice in donation_type.choices}
            )
        ):
            return False, False

        current_type = await self.donations.get_type(
            guild=self.guild, channel_id=channel_id
        )
        configuration = await self.donations.get_channel(
            guild=self.guild, channel_id=channel_id
        )
        if current_type != donation_type or configuration is None:
            return False, False
        if not await self.donations.add_donation(
            guild=guild,
            channel_id=channel_id,
            member=member,
            donation_type=donation_type,
            amount=amount,
            time_reduction=time_reduction,
            cycle=configuration.current_cycle,
        ):
            return False, False
        public_messages_updated = await self.compose_overview(channel_id)
        return True, public_messages_updated

    async def record_rush_donation(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        donation_type: DonationType,
        duration_hours: int,
        amount: Decimal,
        expected_cycle: int,
        expected_start_at: datetime,
        quoted_at: datetime,
    ) -> tuple[bool, bool]:
        """Confirm a priced Rush donation if its cycle and time window remain valid."""
        guild = interaction.guild
        member = interaction.user
        if (
            guild is None
            or guild.id != self.guild.id
            or not isinstance(member, discord.Member)
            or donation_type.kind != "time_reduction"
            or duration_hours not in RUSH_DURATIONS_HOURS
            or amount <= 0
            or not is_rush_donation_open(expected_start_at, quoted_at)
            or rush_donation_cost(
                started_at=expected_start_at,
                now=quoted_at,
                duration_hours=duration_hours,
            )
            != amount
        ):
            return False, False
        configuration = await self.donations.get_channel(
            guild=self.guild, channel_id=channel_id
        )
        current_type = await self.donations.get_type(
            guild=self.guild, channel_id=channel_id
        )
        if (
            configuration is None
            or current_type != donation_type
            or configuration.current_cycle != expected_cycle
            or configuration.rush_start_at != expected_start_at
            or not is_rush_donation_open(expected_start_at, datetime.now(timezone.utc))
        ):
            return False, False
        if not await self.donations.add_donation(
            guild=guild,
            channel_id=channel_id,
            member=member,
            donation_type=donation_type,
            amount=amount,
            time_reduction=f"{duration_hours}h",
            cycle=configuration.current_cycle,
            rush_quoted_at=quoted_at,
        ):
            return False, False
        messages_updated = await self.compose_overview(channel_id)
        return True, messages_updated

    async def reset_cycle(
        self, channel_id: int, *, rush_start_at: datetime | None
    ) -> tuple[bool, bool]:
        """Start a new current cycle and refresh the channel's public messages."""
        if not await self.donations.reset_cycle(
            guild=self.guild,
            channel_id=channel_id,
            rush_start_at=rush_start_at,
        ):
            return False, False
        return True, await self.compose_overview(channel_id)

    async def compose_overview(self, channel_id: int) -> bool:
        """Create or update the overview and ranking messages in a channel."""
        configuration = await self.donations.get_channel(
            guild=self.guild, channel_id=channel_id
        )
        donation_type = await self.donations.get_type(
            guild=self.guild, channel_id=channel_id
        )
        if configuration is None or donation_type is None:
            return False

        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            _logger.error(
                "%s Donation channel %s is unavailable or is not a text channel.",
                self.guild.name,
                channel_id,
            )
            return False

        donations = await self.donations.get_donations(
            guild=self.guild,
            channel_id=channel_id,
            limit=configuration.recent_limit,
            cycle=configuration.current_cycle,
        )
        ranking = (
            await self.donations.get_ranking(
                guild=self.guild,
                channel_id=channel_id,
                unit=donation_type.unit,
            )
            if configuration.show_ranking
            else ()
        )
        summary = await self.donations.get_summary(
            guild=self.guild,
            channel_id=channel_id,
            cycle=configuration.current_cycle,
        )
        if summary is None:
            return False
        now = datetime.now(timezone.utc)
        rush_open = configuration.rush_start_at is not None and is_rush_donation_open(
            configuration.rush_start_at, now
        )
        zone_index = (
            rush_zone_index(configuration.rush_start_at, now)
            if configuration.rush_start_at is not None
            else None
        )
        overview_embed = DonationOverview.create_embed(
            self.guild, configuration, donation_type, donations, summary, now
        )
        view = self._views.get(channel_id)
        if (
            view is None
            or view.donation_type != donation_type
            or view.rush_open != rush_open
            or view.rush_zone_index != zone_index
        ):
            if view is not None and configuration.overview_message_id is not None:
                self.client.remove_view(view)
                self._registered_message_ids.discard(configuration.overview_message_id)
            view = DonationOverviewView(
                self,
                channel_id,
                donation_type,
                rush_open=rush_open,
                rush_zone_index=zone_index,
            )
            self._views[channel_id] = view
        overview_ok = await self._sync_message(
            channel=channel,
            channel_id=channel_id,
            message_id=configuration.overview_message_id,
            embed=overview_embed,
            view=view,
        )
        if configuration.show_ranking:
            ranking_embed = DonationOverview.create_ranking_embed(
                self.guild, donation_type, ranking
            )
            ranking_ok = await self._sync_message(
                channel=channel,
                channel_id=channel_id,
                message_id=configuration.ranking_message_id,
                embed=ranking_embed,
                ranking=True,
            )
        else:
            ranking_ok = await self._clear_ranking_message(
                channel_id, configuration.ranking_message_id
            )
        if overview_ok and donation_type.kind == "time_reduction":
            self._rush_view_states[channel_id] = (rush_open, zone_index)
        elif overview_ok:
            self._rush_view_states.pop(channel_id, None)
        return overview_ok and ranking_ok

    def _ensure_maintenance_task(self) -> None:
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def _maintenance_loop(self) -> None:
        while True:
            try:
                now = datetime.now(timezone.utc)
                for channel_id in await self.donations.get_channels(guild=self.guild):
                    configuration = await self.donations.get_channel(
                        guild=self.guild, channel_id=channel_id
                    )
                    donation_type = await self.donations.get_type(
                        guild=self.guild, channel_id=channel_id
                    )
                    if (
                        configuration is None
                        or donation_type is None
                        or donation_type.kind != "time_reduction"
                    ):
                        continue
                    rush_open = (
                        configuration.rush_start_at is not None
                        and is_rush_donation_open(configuration.rush_start_at, now)
                    )
                    zone_index = (
                        rush_zone_index(configuration.rush_start_at, now)
                        if configuration.rush_start_at is not None
                        else None
                    )
                    if self._rush_view_states.get(channel_id) != (
                        rush_open,
                        zone_index,
                    ):
                        if not await self.compose_overview(channel_id):
                            _logger.error(
                                "%s Failed to refresh Rush overview in channel %s "
                                "after a price-zone or availability change.",
                                self.guild.name,
                                channel_id,
                            )
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("%s Donation maintenance failed.", self.guild.name)
            await asyncio.sleep(30)

    async def _sync_message(
        self,
        *,
        channel: discord.TextChannel,
        channel_id: int,
        message_id: int | None,
        embed: discord.Embed,
        view: discord.ui.View | None = None,
        ranking: bool = False,
    ) -> bool:
        """Create or update one persistent message and store its identifier."""
        message: discord.Message | None = None
        if message_id is not None:
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                if not await self.donations.set_message(
                    guild=self.guild,
                    channel_id=channel_id,
                    message_id=None,
                    ranking=ranking,
                ):
                    return False
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to fetch donation message %s in channel %s.",
                    self.guild.name,
                    message_id,
                    channel_id,
                )
                return False

        try:
            if message is None:
                message = (
                    await channel.send(embed=embed, view=view)
                    if view is not None
                    else await channel.send(embed=embed)
                )
                if not await self.donations.set_message(
                    guild=self.guild,
                    channel_id=channel_id,
                    message_id=message.id,
                    ranking=ranking,
                ):
                    await message.delete()
                    return False
            else:
                await message.edit(embed=embed, view=view)

            if view is not None and message.id not in self._registered_message_ids:
                self.client.add_view(view, message_id=message.id)
                self._registered_message_ids.add(message.id)
            return True
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to publish donation message in channel %s.",
                self.guild.name,
                channel_id,
            )
            return False

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Remove donation data when the bot leaves this guild."""
        if guild.id != self.guild.id:
            return False
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            self._maintenance_task = None
        return await self.donations.remove_guild(guild=guild)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Remove the channel setup when its Discord channel is deleted."""
        if channel.guild.id != self.guild.id:
            return False
        return await self.donations.remove_channel(
            guild=self.guild, channel_id=channel.id
        )

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Recreate either public message if Discord reports its deletion."""
        if payload.guild_id != self.guild.id or payload.channel_id is None:
            return False
        configuration = await self.donations.get_channel(
            guild=self.guild, channel_id=payload.channel_id
        )
        if configuration is None:
            return True
        if payload.message_id == configuration.overview_message_id:
            cleared_overview = await self.donations.set_message(
                guild=self.guild,
                channel_id=payload.channel_id,
                message_id=None,
            )
            if not cleared_overview or not await self._clear_ranking_message(
                payload.channel_id, configuration.ranking_message_id
            ):
                return False
            return await self.compose_overview(payload.channel_id)
        if payload.message_id == configuration.ranking_message_id:
            return await self.donations.set_message(
                guild=self.guild,
                channel_id=payload.channel_id,
                message_id=None,
                ranking=True,
            ) and await self.compose_overview(payload.channel_id)
        return True

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Recreate either overview message if it was bulk deleted."""
        if payload.guild_id != self.guild.id:
            return False
        configuration = await self.donations.get_channel(
            guild=self.guild, channel_id=payload.channel_id
        )
        if configuration is None:
            return True
        deleted = set(payload.message_ids)
        if configuration.overview_message_id in deleted:
            if not await self.donations.set_message(
                guild=self.guild,
                channel_id=payload.channel_id,
                message_id=None,
            ):
                return False
            if (
                configuration.ranking_message_id not in deleted
                and not await self._clear_ranking_message(
                    payload.channel_id, configuration.ranking_message_id
                )
            ):
                return False
        if configuration.ranking_message_id in deleted:
            if not await self.donations.set_message(
                guild=self.guild,
                channel_id=payload.channel_id,
                message_id=None,
                ranking=True,
            ):
                return False
        if (
            configuration.overview_message_id in deleted
            or configuration.ranking_message_id in deleted
        ):
            return await self.compose_overview(payload.channel_id)
        return True

    async def _clear_ranking_message(
        self, channel_id: int, message_id: int | None
    ) -> bool:
        """Delete the old ranking before a recreated overview to retain ordering."""
        if message_id is None:
            return True
        channel = self.guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(message_id)
                await message.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to move donation ranking in channel %s.",
                    self.guild.name,
                    channel_id,
                )
                return False
        return await self.donations.set_message(
            guild=self.guild,
            channel_id=channel_id,
            message_id=None,
            ranking=True,
        )
