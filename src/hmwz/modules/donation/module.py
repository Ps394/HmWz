from __future__ import annotations

import asyncio
import logging

import discord

from hmwz import events, sqlite_db
from hmwz.i18n import t
from hmwz.modules.basic_module import BasicModule
from hmwz.modules.registry import register

from .overview import DonationOverview
from .repository import DonationRepository
from .views import DonationOverviewView, DonationTypeSelectView

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

    async def sync(self, startup: bool = False) -> bool:
        """Ensure the donation schema exists."""
        return await self.donations.ensure_schema()

    async def ensure(self) -> bool:
        """Refresh the configured channel overviews and register persistent views."""
        channels = await self.donations.get_channels(guild=self.guild)
        if not channels:
            return True
        results = await asyncio.gather(
            *(self.compose_overview(channel_id) for channel_id in channels)
        )
        return all(results)

    async def configure_channel(self, channel_id: int) -> bool:
        """Enable donation tracking in a channel and publish its overview."""
        if not await self.donations.add_channel(
            guild=self.guild, channel_id=channel_id
        ):
            return False
        return await self.compose_overview(channel_id)

    async def remove_channel(self, channel_id: int) -> bool:
        """Disable a channel and remove its overview without deleting its history."""
        if channel_id not in await self.donations.get_channels(guild=self.guild):
            return False
        message_id = await self.donations.get_channel(
            guild=self.guild, channel_id=channel_id
        )
        channel = self.guild.get_channel(channel_id)
        if message_id is not None and isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(message_id)
                await message.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to remove donation overview in channel %s.",
                    self.guild.name,
                    channel_id,
                )
                return False
        if not await self.donations.remove_channel(
            guild=self.guild, channel_id=channel_id
        ):
            return False
        self._views.pop(channel_id, None)
        if message_id is not None:
            self._registered_message_ids.discard(message_id)
        return True

    async def show_donation_type_selection(
        self, interaction: discord.Interaction, channel_id: int
    ) -> None:
        """Show the available donation types to a user."""
        if channel_id not in await self.donations.get_channels(guild=self.guild):
            await interaction.response.send_message(
                t(interaction, "donation.error.not_configured"),
                ephemeral=True,
            )
            return
        donation_types = await self.donations.get_types(guild=self.guild)
        if not donation_types:
            await interaction.response.send_message(
                t(interaction, "donation.error.configure_type_first"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            t(interaction, "donation.ui.select_prompt"),
            view=DonationTypeSelectView(self, channel_id, donation_types),
            ephemeral=True,
        )

    async def compose_overview(self, channel_id: int) -> bool:
        """Create or update the overview message for a configured channel."""
        message_id = await self.donations.get_channel(
            guild=self.guild, channel_id=channel_id
        )
        if message_id is None and channel_id not in await self.donations.get_channels(
            guild=self.guild
        ):
            return False

        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            _logger.error(
                "%s Donation channel %s is unavailable or is not a text channel.",
                self.guild.name,
                channel_id,
            )
            return False

        types = await self.donations.get_types(guild=self.guild)
        records = await self.donations.get_donations(
            guild=self.guild, channel_id=channel_id
        )
        embed = DonationOverview.create_embed(self.guild, types, records)
        view = self._views.get(channel_id)
        if view is None:
            view = DonationOverviewView(self, channel_id)
            self._views[channel_id] = view

        try:
            message = (
                await channel.fetch_message(message_id)
                if message_id is not None
                else None
            )
            if message is None:
                message = await channel.send(embed=embed, view=view)
                if not await self.donations.set_overview_message(
                    guild=self.guild,
                    channel_id=channel_id,
                    message_id=message.id,
                ):
                    _logger.error(
                        "%s Failed to persist donation overview message %s.",
                        self.guild.name,
                        message.id,
                    )
                    return False
            else:
                await message.edit(embed=embed, view=view)

            if message.id not in self._registered_message_ids:
                self.client.add_view(view, message_id=message.id)
                self._registered_message_ids.add(message.id)
            return True
        except discord.NotFound:
            self._views.pop(channel_id, None)
            if message_id is not None:
                if not await self.donations.clear_overview_message(
                    guild=self.guild, channel_id=channel_id
                ):
                    return False
                return await self.compose_overview(channel_id)
            raise
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to publish donation overview in channel %s.",
                self.guild.name,
                channel_id,
            )
            return False

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Remove donation data when the bot leaves this guild."""
        if guild.id != self.guild.id:
            return False
        return await self.donations.remove_guild(guild=guild)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Remove the channel setup when its Discord channel is deleted."""
        if channel.guild.id != self.guild.id:
            return False
        message_id = await self.donations.get_channel(
            guild=self.guild, channel_id=channel.id
        )
        self._views.pop(channel.id, None)
        if message_id is not None:
            self._registered_message_ids.discard(message_id)
        return await self.donations.remove_channel(
            guild=self.guild, channel_id=channel.id
        )

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Recreate an overview if its message is deleted."""
        if payload.guild_id != self.guild.id or payload.channel_id is None:
            return False
        message_id = await self.donations.get_channel(
            guild=self.guild, channel_id=payload.channel_id
        )
        if message_id != payload.message_id:
            return True
        if not await self.donations.clear_overview_message(
            guild=self.guild, channel_id=payload.channel_id
        ):
            return False
        return await self.compose_overview(payload.channel_id)

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Recreate an overview removed by bulk deletion."""
        if payload.guild_id != self.guild.id:
            return False
        message_id = await self.donations.get_channel(
            guild=self.guild, channel_id=payload.channel_id
        )
        if message_id not in payload.message_ids:
            return True
        if not await self.donations.clear_overview_message(
            guild=self.guild, channel_id=payload.channel_id
        ):
            return False
        return await self.compose_overview(payload.channel_id)
