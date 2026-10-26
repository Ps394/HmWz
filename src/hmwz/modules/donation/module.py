from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal

import discord

from hmwz import events, sqlite_db
from hmwz.interactions import send_temporary_response as _send_temporary_response
from hmwz.i18n import t
from hmwz.modules.basic_module import BasicModule
from hmwz.modules.registry import register

from .overview import DonationOverview
from .models import DonationType
from .repositories import DonationRepository
from hmwz.modules.snapshots import Snapshot
from hmwz.modules.snapshots.json_discord import DiscordJsonSnapshotExporter
from .rush_pricing import (
    RUSH_BUTTON_DURATIONS_HOURS,
    RUSH_DURATIONS_HOURS,
    available_rush_durations,
    rush_donation_cost,
    rush_donation_prices,
)
from .views import (
    MAX_DONATION_BUTTONS,
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
        self._snapshot_exporter = DiscordJsonSnapshotExporter(guild)
        self._views: dict[int, DonationOverviewView] = {}
        self._registered_message_ids: set[int] = set()
        self._rush_view_states: dict[
            int, tuple[bool, bool, tuple[Decimal | None, ...]]
        ] = {}
        self._maintenance_task: asyncio.Task[None] | None = None
        self._cycle_locks: dict[int, asyncio.Lock] = {}

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
        timezone_name: str = "UTC",
        show_donations: bool = True,
        donations_enabled: bool = True,
        export_channel_id: int | None = None,
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
            timezone_name=timezone_name,
            show_donations=show_donations,
            donations_enabled=donations_enabled,
            export_channel_id=export_channel_id,
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
            configuration.history_message_id,
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

        self._views.pop(channel_id, None)
        self._rush_view_states.pop(channel_id, None)
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
        replace_prompt: bool = False,
    ) -> None:
        """Start a configured donation flow."""
        if channel_id not in await self.donations.get_channels(guild=self.guild):
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.not_configured")
            )
            return
        configuration = await self.donations.get_channel(
            guild=self.guild, channel_id=channel_id
        )
        if configuration is None:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.not_configured")
            )
            return
        if not configuration.donations_enabled:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.stopped")
            )
            return
        donation_type = await self.donations.get_type(
            guild=self.guild, channel_id=channel_id
        )
        if donation_type is None:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.not_configured")
            )
            return
        if donation_type.kind == "time_reduction":
            configuration = await self.donations.get_channel(
                guild=self.guild, channel_id=channel_id
            )
            now = discord.utils.utcnow()
            if configuration is None or configuration.rush_start_at is None:
                await _send_temporary_response(
                    interaction, t(interaction, "donation.error.rush_closed")
                )
                return
            summary = await self.donations.get_summary(
                guild=self.guild,
                channel_id=channel_id,
                cycle=configuration.current_cycle,
            )
            if summary is None:
                await _send_temporary_response(
                    interaction, t(interaction, "donation.error.save")
                )
                return
            rush_prices = rush_donation_prices(
                started_at=configuration.rush_start_at,
                now=now,
                accelerated_hours=summary.time_reduction_hours,
            )
            if not rush_prices:
                await _send_temporary_response(
                    interaction, t(interaction, "donation.error.rush_closed")
                )
                return
            if time_reduction is None:
                await interaction.response.send_message(
                    t(interaction, "donation.setup.hours_donation_prompt"),
                    view=DonationTimeReductionView(
                        self, channel_id, donation_type, rush_prices
                    ),
                    ephemeral=True,
                )
                return
            if time_reduction not in {f"{hours}h" for hours in rush_prices}:
                await _send_temporary_response(
                    interaction, t(interaction, "donation.error.choose_time")
                )
                return
            hours = int(time_reduction.removesuffix("h"))
            cost = rush_prices[hours]
            response_content = t(
                interaction,
                "donation.rush.confirm",
                hours=hours,
                cost=format(cost, "f"),
            )
            confirmation_view = DonationRushConfirmationView(
                self,
                channel_id,
                donation_type,
                hours,
                cost,
                configuration.current_cycle,
                configuration.rush_start_at,
                now,
                interaction.user.id,
            )
            if replace_prompt:
                await interaction.response.edit_message(
                    content=response_content, view=confirmation_view
                )
                confirmation_view.message = interaction.message
            else:
                await interaction.response.send_message(
                    response_content,
                    view=confirmation_view,
                    ephemeral=True,
                )
                confirmation_view.message = await interaction.original_response()
            return
        elif time_reduction is not None:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_type")
            )
            return
        if (
            donation_type.input_mode == "choice"
            and donation_type.choices
            and len(donation_type.choices) <= MAX_DONATION_BUTTONS
        ):
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
        async with self._cycle_lock(channel_id):
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
        ):
            return False, False
        summary = await self.donations.get_summary(
            guild=self.guild,
            channel_id=channel_id,
            cycle=configuration.current_cycle,
        )
        now = discord.utils.utcnow()
        if (
            summary is None
            or duration_hours
            not in available_rush_durations(
                started_at=expected_start_at,
                now=quoted_at,
                accelerated_hours=summary.time_reduction_hours,
            )
            or duration_hours
            not in available_rush_durations(
                started_at=expected_start_at,
                now=now,
                accelerated_hours=summary.time_reduction_hours,
            )
            or amount
            != rush_donation_cost(
                started_at=expected_start_at,
                now=quoted_at,
                duration_hours=duration_hours,
                accelerated_hours=summary.time_reduction_hours,
            )
        ):
            return False, False
        async with self._cycle_lock(channel_id):
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
    ) -> tuple[bool, bool, bool]:
        """Export and reset the current cycle before refreshing public messages."""
        async with self._cycle_lock(channel_id):
            if not await self.export_current_cycle(channel_id):
                return False, False, True
            if not await self.donations.reset_cycle(
                guild=self.guild,
                channel_id=channel_id,
                rush_start_at=rush_start_at,
            ):
                return False, False, False
        return True, await self.compose_overview(channel_id), False

    async def export_current_cycle(self, channel_id: int) -> bool:
        """Export every donation in the current cycle when a destination is set."""
        configuration = await self.donations.get_channel(
            guild=self.guild, channel_id=channel_id
        )
        if configuration is None:
            return False
        destination_channel_id = configuration.export_channel_id
        if destination_channel_id is None:
            return True

        records = await self.donations.get_donations_for_export(
            guild=self.guild,
            channel_id=channel_id,
            cycle=configuration.current_cycle,
        )
        summary = await self.donations.get_summary(
            guild=self.guild,
            channel_id=channel_id,
            cycle=configuration.current_cycle,
        )
        if records is None or summary is None or len(records) != summary.donation_count:
            _logger.error(
                "%s Cannot export all donations for channel %s, cycle %s.",
                self.guild.name,
                channel_id,
                configuration.current_cycle,
            )
            return False

        name = configuration.title
        if not name:
            channel = self.guild.get_channel_or_thread(channel_id)
            name = channel.name if channel is not None else str(channel_id)
        donations: list[dict[str, int | str]] = []
        for record in records:
            donation: dict[str, int | str] = {
                "member_id": record.member_id,
                "member_name": record.member_name,
                "amount": format(record.amount, "f"),
                "unit": record.unit,
                "created_at": record.created_at,
            }
            if record.time_reduction is not None:
                donation["time_reduction"] = record.time_reduction
            donations.append(donation)

        snapshot = Snapshot(
            destination_channel_id=destination_channel_id,
            filename=f"donation-{channel_id}-cycle-{configuration.current_cycle}.json",
            payload={
                "type": "cycle-reset",
                "name": name,
                "channel-id": channel_id,
                "cycle": configuration.current_cycle,
                "donations": donations,
            },
        )
        exported = await self._snapshot_exporter.export(snapshot)
        if not exported:
            _logger.error(
                "%s Failed to export donation cycle %s from channel %s.",
                self.guild.name,
                configuration.current_cycle,
                channel_id,
            )
        return exported

    def _cycle_lock(self, channel_id: int) -> asyncio.Lock:
        """Return the lock protecting donation writes and cycle resets."""
        return self._cycle_locks.setdefault(channel_id, asyncio.Lock())

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
            limit=None,
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
        now = discord.utils.utcnow()
        rush_prices = (
            rush_donation_prices(
                started_at=configuration.rush_start_at,
                now=now,
                accelerated_hours=summary.time_reduction_hours,
            )
            if configuration.rush_start_at is not None
            else {}
        )
        rush_open = configuration.donations_enabled and bool(rush_prices)
        overview_embed = DonationOverview.create_embed(
            self.guild,
            configuration,
            rush_start_at=(
                configuration.rush_start_at
                if donation_type.kind == "time_reduction"
                else None
            ),
            timezone_name=configuration.timezone_name,
            accelerated_hours=(
                summary.time_reduction_hours
                if donation_type.kind == "time_reduction"
                else 0
            ),
            donations_enabled=configuration.donations_enabled,
        )
        view = self._views.get(channel_id)
        if (
            view is None
            or view.donation_type != donation_type
            or view.rush_open != rush_open
            or view.rush_prices != rush_prices
            or view.donations_enabled != configuration.donations_enabled
        ):
            if view is not None and configuration.overview_message_id is not None:
                self._registered_message_ids.discard(configuration.overview_message_id)
            view = DonationOverviewView(
                self,
                channel_id,
                donation_type,
                rush_open=rush_open,
                rush_prices=rush_prices,
                donations_enabled=configuration.donations_enabled,
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
        if configuration.show_donations:
            history_embed = DonationOverview.create_history_embed(
                self.guild,
                donation_type,
                donations,
                summary,
            )
            history_ok = await self._sync_message(
                channel=channel,
                channel_id=channel_id,
                message_id=configuration.history_message_id,
                embed=history_embed,
                history=True,
            )
        else:
            history_ok = await self._clear_history_message(
                channel_id, configuration.history_message_id
            )
        if overview_ok and donation_type.kind == "time_reduction":
            self._rush_view_states[channel_id] = (
                rush_open,
                configuration.donations_enabled,
                tuple(rush_prices.get(hours) for hours in RUSH_BUTTON_DURATIONS_HOURS),
            )
        elif overview_ok:
            self._rush_view_states.pop(channel_id, None)
        return overview_ok and ranking_ok and history_ok

    def _ensure_maintenance_task(self) -> None:
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def _maintenance_loop(self) -> None:
        while True:
            try:
                now = discord.utils.utcnow()
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
                    summary = await self.donations.get_summary(
                        guild=self.guild,
                        channel_id=channel_id,
                        cycle=configuration.current_cycle,
                    )
                    if summary is None:
                        continue
                    rush_prices = (
                        rush_donation_prices(
                            started_at=configuration.rush_start_at,
                            now=now,
                            accelerated_hours=summary.time_reduction_hours,
                        )
                        if configuration.rush_start_at is not None
                        else {}
                    )
                    rush_open = configuration.donations_enabled and bool(rush_prices)
                    rush_state = (
                        rush_open,
                        configuration.donations_enabled,
                        tuple(
                            rush_prices.get(hours)
                            for hours in RUSH_BUTTON_DURATIONS_HOURS
                        ),
                    )
                    if self._rush_view_states.get(channel_id) != rush_state:
                        if not await self.compose_overview(channel_id):
                            _logger.error(
                                "%s Failed to refresh Rush overview in channel %s "
                                "after a price or availability change.",
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
        history: bool = False,
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
                    history=history,
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
                    history=history,
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
        """Recreate a public donation message when Discord reports its deletion."""
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
        if payload.message_id == configuration.history_message_id:
            return await self.donations.set_message(
                guild=self.guild,
                channel_id=payload.channel_id,
                message_id=None,
                history=True,
            ) and await self.compose_overview(payload.channel_id)
        return True

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Recreate public donation messages that were bulk deleted."""
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
        if configuration.history_message_id in deleted:
            if not await self.donations.set_message(
                guild=self.guild,
                channel_id=payload.channel_id,
                message_id=None,
                history=True,
            ):
                return False
        if (
            configuration.overview_message_id in deleted
            or configuration.ranking_message_id in deleted
            or configuration.history_message_id in deleted
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

    async def _clear_history_message(
        self, channel_id: int, message_id: int | None
    ) -> bool:
        """Delete and forget the optional public donation history message."""
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
                    "%s Failed to hide donation history in channel %s.",
                    self.guild.name,
                    channel_id,
                )
                return False
        return await self.donations.set_message(
            guild=self.guild,
            channel_id=channel_id,
            message_id=None,
            history=True,
        )
