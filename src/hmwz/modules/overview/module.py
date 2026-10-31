"""Reusable service for publishing and maintaining guild overview messages."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

import discord

from hmwz import events
from hmwz.modules.module import Module
from hmwz.modules.overview.models import Overview, OverviewButton
from hmwz.modules.overview.protocols import OverviewButtonHandler
from hmwz.modules.overview.repositories import OverviewRepository
from hmwz.modules.overview.views import OverviewView
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import delete_message, edit_message, send_message
from hmwz.utils.loaders import fetch_message

if TYPE_CHECKING:
    from hmwz.client import Client

_logger = logging.getLogger(__name__)
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class OverviewModule(Module):
    """Composable overview service owned directly by another guild module."""

    def __init__(self, guild: discord.Guild, client: Client) -> None:
        super().__init__(guild, client)
        if self.database is None:
            raise RuntimeError("Overview module requires a database.")
        self.overviews = OverviewRepository(self.database)
        self._handlers: dict[tuple[str, str], OverviewButtonHandler] = {}

    @property
    def client_color(self) -> discord.Color:
        """Return the bot member's highest role color or Discord's default blurple."""
        member = (
            self.guild.get_member(self.client.user.id)
            if self.client.user is not None
            else None
        )
        if member and member.roles:
            return max(member.roles, key=lambda role: role.position).color
        return discord.Color.blurple()

    @property
    def client_avatar(self) -> discord.Asset | None:
        """Return the guild icon or bot avatar for overview embeds."""
        guild_icon = self.guild.icon
        if isinstance(guild_icon, discord.Asset):
            return guild_icon
        user_avatar = self.client.user.avatar if self.client.user is not None else None
        return user_avatar if isinstance(user_avatar, discord.Asset) else None

    async def sync(self, startup: bool = False) -> bool:
        """Ensure the overview repository schema exists."""
        del startup
        return await self.overviews.ensure_schema()

    async def ensure(self) -> bool:
        """Restore all persisted overview messages and their persistent views."""
        records = await self.overviews.get_all(guild=self.guild)
        results = [await self._sync_overview(record) for record in records]
        return all(results)

    def register_handler(
        self,
        *,
        overview_id: str,
        button_id: str,
        handler: OverviewButtonHandler,
    ) -> None:
        """Register or replace the callback used by one overview button."""
        self._validate_id(overview_id, "overview_id")
        self._validate_id(button_id, "button_id")
        self._handlers[(overview_id, button_id)] = handler

    def unregister_handler(self, *, overview_id: str, button_id: str) -> None:
        """Remove a previously registered overview button callback."""
        self._handlers.pop((overview_id, button_id), None)

    async def publish(
        self,
        *,
        overview_id: str,
        channel_id: int,
        title: str,
        description: str,
        buttons: Sequence[OverviewButton] = (),
    ) -> bool:
        """Create or update an overview and synchronize its Discord message."""
        self._validate_id(overview_id, "overview_id")
        if channel_id <= 0:
            raise ValueError("channel_id must be a positive Discord ID.")
        self._validate_content(overview_id, title, description, buttons)
        previous = await self.overviews.get(guild=self.guild, overview_id=overview_id)
        moving = previous is not None and previous.channel_id != channel_id
        if previous is not None and moving and not await self._delete_message(previous):
            return False
        overview = Overview(
            guild_id=self.guild.id,
            overview_id=overview_id,
            channel_id=channel_id,
            message_id=(
                previous.message_id if previous is not None and not moving else None
            ),
            title=title,
            description=description,
            buttons=tuple(buttons),
        )
        if not await self.overviews.save(overview):
            _logger.error(
                "%s Failed to save overview %s.",
                self.guild.name,
                overview_id,
            )
            return False
        configured_button_ids = {button.button_id for button in overview.buttons}
        for key in tuple(self._handlers):
            if key[0] == overview_id and key[1] not in configured_button_ids:
                self._handlers.pop(key)
        return await self._sync_overview(overview)

    async def delete(self, *, overview_id: str) -> bool:
        """Delete a managed overview message and its stored configuration."""
        self._validate_id(overview_id, "overview_id")
        overview = await self.overviews.get(guild=self.guild, overview_id=overview_id)
        if overview is None:
            return True
        if not await self._delete_message(overview):
            return False
        if not await self.overviews.remove(guild=self.guild, overview_id=overview_id):
            _logger.error(
                "%s Failed to remove overview %s from storage.",
                self.guild.name,
                overview_id,
            )
            return False
        for button in overview.buttons:
            self.unregister_handler(overview_id=overview_id, button_id=button.button_id)
        return True

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Delete all managed overview messages when the bot leaves a guild."""
        records = await self.overviews.get_all(guild=guild)
        status = True
        for record in records:
            status = await self._delete_message(record) and status
        if not await self.overviews.remove_guild(guild=guild):
            _logger.error(
                "%s Failed to remove overview records after leaving the guild.",
                guild.name,
            )
            status = False
        self._handlers.clear()
        return status

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        """Restore persisted overview messages when the bot joins a guild."""
        return await self.sync() and await self.ensure()

    async def on_message_create(self, message: discord.Message) -> bool:
        """Ignore newly created messages not owned by this module."""
        return True

    async def on_message_update(
        self, before: discord.Message, after: discord.Message
    ) -> bool:
        """Ignore message edits; overview content is managed explicitly."""
        return True

    async def on_message_delete(self, message: discord.Message) -> bool:
        """Forget the stored message ID when a managed message is deleted."""
        if message.guild is not None:
            return await self._forget_message(message.guild.id, message.id)
        return True

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Forget a managed message even when it is not present in the cache."""
        return await self._forget_message(payload.guild_id, payload.message_id)

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Forget managed messages removed as part of a bulk deletion."""
        status = True
        for message_id in payload.message_ids:
            status = await self._forget_message(payload.guild_id, message_id) and status
        return status

    async def _forget_message(self, guild_id: int | None, message_id: int) -> bool:
        if guild_id != self.guild.id:
            return True
        records = await self.overviews.get_all(guild=self.guild)
        for record in records:
            if record.message_id == message_id:
                return await self.overviews.set_message(
                    guild=self.guild,
                    overview_id=record.overview_id,
                    message_id=None,
                )
        return True

    async def _sync_overview(self, overview: Overview) -> bool:
        channel = self.guild.get_channel_or_thread(overview.channel_id)
        if channel is None:
            try:
                channel = await self.guild.fetch_channel(overview.channel_id)
            except discord.NotFound:
                _logger.warning(
                    "%s Overview %s channel %s was not found.",
                    self.guild.name,
                    overview.overview_id,
                    overview.channel_id,
                )
                return False
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to fetch channel %s for overview %s.",
                    self.guild.name,
                    overview.channel_id,
                    overview.overview_id,
                )
                return False
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            _logger.warning(
                "%s Overview %s channel %s cannot contain messages.",
                self.guild.name,
                overview.overview_id,
                overview.channel_id,
            )
            return False

        message: discord.Message | None = None
        if overview.message_id is not None:
            try:
                message = await fetch_message(
                    channel, overview.message_id, raise_on_error=True
                )
            except discord.NotFound:
                if not await self.overviews.set_message(
                    guild=self.guild,
                    overview_id=overview.overview_id,
                    message_id=None,
                ):
                    return False
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to fetch message %s for overview %s.",
                    self.guild.name,
                    overview.message_id,
                    overview.overview_id,
                )
                return False

        view = (
            OverviewView(overview, self._dispatch_button) if overview.buttons else None
        )
        embed = create_embed(title=overview.title, description=overview.description)
        if message is None:
            message = await send_message(channel, embed=embed, view=view)
            if message is None:
                return False
            if not await self.overviews.set_message(
                guild=self.guild,
                overview_id=overview.overview_id,
                message_id=message.id,
            ):
                await delete_message(message)
                return False
        elif await edit_message(message, embed=embed, view=view) is None:
            return False

        if view is not None:
            self.client.add_view(view, message_id=message.id)
        return True

    async def _delete_message(self, overview: Overview) -> bool:
        if overview.message_id is None:
            return True
        channel = self.guild.get_channel_or_thread(overview.channel_id)
        if channel is None:
            try:
                channel = await self.guild.fetch_channel(overview.channel_id)
            except discord.NotFound:
                return True
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to fetch channel %s while deleting overview %s.",
                    self.guild.name,
                    overview.channel_id,
                    overview.overview_id,
                )
                return False
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return False
        try:
            message = await fetch_message(
                channel, overview.message_id, raise_on_error=True
            )
        except discord.NotFound:
            return True
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to fetch message %s while deleting overview %s.",
                self.guild.name,
                overview.message_id,
                overview.overview_id,
            )
            return False
        return await delete_message(message)

    async def _dispatch_button(
        self,
        interaction: discord.Interaction,
        overview_id: str,
        button_id: str,
    ) -> None:
        handler = self._handlers.get((overview_id, button_id))
        if handler is None:
            _logger.warning(
                "%s No handler registered for overview button %s/%s.",
                self.guild.name,
                overview_id,
                button_id,
            )
            await interaction.response.send_message(
                "Diese Interaktion ist derzeit nicht verfügbar.", ephemeral=True
            )
            return
        await handler(interaction)

    @staticmethod
    def _validate_id(value: str, name: str) -> None:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError(
                f"{name} must contain only ASCII letters, numbers, underscores, "
                "or hyphens."
            )

    @classmethod
    def _validate_content(
        cls,
        overview_id: str,
        title: str,
        description: str,
        buttons: Sequence[OverviewButton],
    ) -> None:
        if not title.strip() or len(title) > 256:
            raise ValueError("Overview title must contain 1 to 256 characters.")
        if len(description) > 4096:
            raise ValueError("Overview description cannot exceed 4096 characters.")
        if len(buttons) > 25:
            raise ValueError("An overview cannot contain more than 25 buttons.")
        button_ids: set[str] = set()
        for button in buttons:
            cls._validate_id(button.button_id, "button_id")
            if button.button_id in button_ids:
                raise ValueError(f"Duplicate overview button ID: {button.button_id}")
            button_ids.add(button.button_id)
            if not button.label or len(button.label) > 80:
                raise ValueError(
                    "Overview button labels must contain 1 to 80 characters."
                )
            if button.row is not None and not 0 <= button.row <= 4:
                raise ValueError("Overview button rows must be between 0 and 4.")
            if (
                button.row is not None
                and sum(item.row == button.row for item in buttons) > 5
            ):
                raise ValueError("An overview row cannot contain more than 5 buttons.")
            if button.style not in (
                discord.ButtonStyle.primary,
                discord.ButtonStyle.secondary,
                discord.ButtonStyle.success,
                discord.ButtonStyle.danger,
            ):
                raise ValueError(
                    "Overview buttons must use an interactive button style."
                )
            custom_id = f"overview:{overview_id}:{button.button_id}"
            if len(custom_id) > 100:
                raise ValueError(
                    "Overview button custom IDs cannot exceed 100 characters."
                )
