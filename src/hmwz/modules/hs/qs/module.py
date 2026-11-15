"""Guild-scoped Qs module wiring, lifecycle and Discord event handlers."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz import events, sqlite_db
from hmwz.modules.hs.account.repositories import MemberGameAccountRepository
from hmwz.modules.module import Module
from hmwz.modules.registry import register
from hmwz.ui.components.timestamp_input import resolve_timezone
from hmwz.utils.interactions import log_guild

from .access import QsAccess
from .maintenance import remove_event, reset_event
from .models import PingSettings, phase_starts, validate_schedule
from .notifications import QsNotifications
from .phases.bases.service import BaseService
from .phases.pings import PhasePings
from .phases.signups.service import SignupService
from .pings import QsPings
from .publishing import QsPublisher
from .repositories import QsRepository

if TYPE_CHECKING:
    from hmwz.client import Client

_logger = logging.getLogger(__name__)


@register
class QsModule(Module):
    """Wire the Qs services together without depending on other modules."""

    module_key = "qs"

    def __init__(self, guild: discord.Guild, client: Client) -> None:
        super().__init__(guild, client)
        if not isinstance(self.database, sqlite_db.Database):
            raise RuntimeError("Qs module requires a database.")
        self.qs = QsRepository(self.database)
        self.game_accounts = MemberGameAccountRepository(self.database)
        self.access = QsAccess(self)
        self.publisher = QsPublisher(self)
        self.signups = SignupService(self)
        self.bases = BaseService(self)
        self.pings = QsPings(self)
        self.phase_pings = PhasePings(self)
        self.notifications = QsNotifications(self)

    async def sync(self, startup: bool = False) -> bool:
        """Create only the independent Qs schema."""
        return await self.qs.ensure_schema()

    async def configure(
        self,
        channel_id: int,
        role_id: int,
        date: str,
        hours: tuple[int, ...],
        *,
        minutes: tuple[int, ...] | None = None,
        eruption_start: int | None = None,
        durations: tuple[int, ...] | None = None,
        ping_settings: PingSettings | None = None,
    ) -> bool:
        """Configure one event, preserving existing signups and base reports."""
        timezone = await self.client.get_guild_timezone(self.guild.id)
        starts = phase_starts(
            date,
            hours,
            timezone,
            minutes=minutes,
            eruption_start=eruption_start,
        )
        durations = durations if durations is not None else (2,) * len(starts)
        eruption_start = eruption_start if eruption_start is not None else min(starts)
        date = (
            datetime.fromtimestamp(eruption_start, resolve_timezone(timezone))
            .date()
            .isoformat()
        )
        validate_schedule(eruption_start, starts, durations)
        channel = self.guild.get_channel(channel_id)
        role = self.guild.get_role(role_id)
        if (
            not isinstance(channel, discord.TextChannel)
            or role is None
            or role.is_default()
        ):
            _logger.warning("%s Invalid Qs channel or role.", log_guild(self.guild))
            return False
        async with self.publisher.lock(channel_id):
            if not await self.sync():
                return False
            try:
                existing = await self.qs.get(self.guild.id, channel_id)
                if existing is not None and existing.state != "active":
                    _logger.warning(
                        "%s Finish Qs maintenance before configuring.",
                        log_guild(self.guild),
                    )
                    return False
                await self.qs.configure(
                    self.guild.id,
                    channel_id,
                    role_id,
                    date,
                    timezone,
                    starts,
                    eruption_start=eruption_start,
                    durations=durations,
                    ping_settings=ping_settings,
                )
            except (aiosqlite.Error, discord.HTTPException, RuntimeError):
                _logger.exception(
                    "%s Failed to save Qs configuration.", log_guild(self.guild)
                )
                return False
            return await self.publisher.refresh(channel_id)

    async def ensure(self) -> bool:
        """Restore all messages and register persistent buttons after restart."""
        success = True
        for configuration in await self.qs.all(self.guild.id):
            if configuration.state != "active":
                continue
            async with self.publisher.lock(configuration.channel_id):
                if not await self.publisher.refresh(configuration.channel_id):
                    success = False
        self.notifications.start()
        return success

    async def on_guild_timezone_update(self) -> bool:
        """Refresh local-time labels after the guild timezone changes."""
        if not await self.sync():
            return False
        return await self.ensure()

    async def close(self) -> None:
        """Stop automatic pings when the client is closed."""
        self.notifications.stop()
        if self.publisher.update_tasks:
            await asyncio.gather(*tuple(self.publisher.update_tasks))

    async def on_disconnect(self) -> None:
        """Discard the notification window even for a short gateway disconnect."""
        self.notifications.last_tick = None
        self.notifications.pending.clear()

    async def remove_tool(self, channel_id: int) -> bool:
        """Remove only this channel's Qs tool, managed threads and event data."""
        return await remove_event(self, channel_id)

    async def reset_tool(
        self,
        channel_id: int,
        date: str,
        hours: tuple[int, ...],
        *,
        minutes: tuple[int, ...] | None = None,
        eruption_start: int,
        durations: tuple[int, ...],
    ) -> bool:
        """Validate the replacement schedule before any destructive cleanup."""
        timezone = await self.client.get_guild_timezone(self.guild.id)
        starts = phase_starts(
            date,
            hours,
            timezone,
            minutes=minutes,
            eruption_start=eruption_start,
        )
        date = (
            datetime.fromtimestamp(eruption_start, resolve_timezone(timezone))
            .date()
            .isoformat()
        )
        validate_schedule(eruption_start, starts, durations)
        return await reset_event(
            self,
            channel_id,
            date=date,
            timezone=timezone,
            starts=starts,
            eruption_start=eruption_start,
            durations=durations,
        )

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        """Initialize independent Qs storage on joining the guild."""
        return guild.id == self.guild.id and await self.sync()

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Remove this guild's Qs data when the bot leaves."""
        if guild.id != self.guild.id:
            return False
        await self.close()
        self.publisher.stop_all_views()
        return await self.qs.remove(self.guild.id)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Cascade data deletion only for a deleted Qs overview channel."""
        if channel.guild.id != self.guild.id:
            return False
        async with self.publisher.lock(channel.id):
            configuration = await self.qs.get(self.guild.id, channel.id)
            phases = await self.qs.phases(self.guild.id, channel.id)
            if not await self.qs.remove(self.guild.id, channel.id):
                return False
            if configuration is not None:
                message_ids = {configuration.message_id}
                message_ids.update(phase.message_id for phase in phases)
                for message_id in message_ids:
                    self.publisher.stop_view(message_id)
            return True

    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> bool:
        """Remove phase signups when the corresponding channel's Qs role is lost."""
        if after.guild.id != self.guild.id:
            return False
        removed_roles = {role.id for role in before.roles} - {
            role.id for role in after.roles
        }
        success = True
        for configuration in await self.qs.all(self.guild.id):
            if configuration.role_id not in removed_roles:
                continue
            if not await self.signups.remove_member(configuration.channel_id, after.id):
                success = False
        return success

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool:
        """Remove a departed member's signups without changing destroyed-base counts."""
        if payload.guild_id != self.guild.id:
            return False
        success = True
        for configuration in await self.qs.all(self.guild.id):
            if not await self.signups.remove_member(
                configuration.channel_id, payload.user.id
            ):
                success = False
        return success

    async def on_raw_thread_delete(self, payload: events.RawThreadDeleteEvent) -> bool:
        """Recreate a deleted phase thread while preserving its signups and reports."""
        if payload.guild_id != self.guild.id:
            return False
        for configuration in await self.qs.all(self.guild.id):
            if configuration.state != "active":
                continue
            phases = await self.qs.phases(self.guild.id, configuration.channel_id)
            for phase in phases:
                if phase.thread_id != payload.thread_id:
                    continue
                async with self.publisher.lock(configuration.channel_id):
                    self.publisher.stop_view(phase.message_id)
                    if not await self.qs.database.execute(
                        "UPDATE HsQsPhases SET Thread=NULL, Message=NULL "
                        "WHERE Guild=? AND Channel=? AND Phase=?",
                        (self.guild.id, configuration.channel_id, phase.index),
                    ):
                        return False
                    return await self.publisher.refresh(configuration.channel_id)
        return True

    async def on_message_create(self, message: discord.Message) -> bool:
        """Ignore ordinary messages; Qs reacts only to its own controls."""
        return True

    async def on_message_update(
        self, before: discord.Message, after: discord.Message
    ) -> bool:
        """Ignore message edits to avoid refresh loops."""
        return True

    async def on_message_delete(self, message: discord.Message) -> bool:
        """Restore a deleted managed message without altering event data."""
        return await self.publisher.restore_deleted({message.id})

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Restore managed messages even when absent from the message cache."""
        if payload.guild_id != self.guild.id:
            return False
        return await self.publisher.restore_deleted({payload.message_id})

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Restore a batch of managed messages once per affected channel."""
        if payload.guild_id != self.guild.id:
            return False
        return await self.publisher.restore_deleted(set(payload.message_ids))
