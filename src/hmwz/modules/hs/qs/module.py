"""Guild-scoped Qs scheduling, signups and Discord message restoration."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from datetime import datetime
from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz import events, sqlite_db
from hmwz.i18n import t
from hmwz.modules.module import Module
from hmwz.modules.registry import register
from hmwz.ui.messages import (
    defer_interaction,
    edit_message,
    send_followup,
    send_interaction_message,
    send_message,
)
from hmwz.utils.interactions import log_guild
from hmwz.utils.loaders import fetch_message, fetch_thread
from hmwz.ui.threads import create_thread, edit_thread, delete_thread
from hmwz.ui.components.timestamp_input import resolve_timezone

from .models import Configuration, Phase, phase_starts, validate_schedule
from .maintenance import existing_thread, remove_event, reset_event
from .notifications import QsNotifications
from .overview import (
    bases_embeds,
    overview_embed,
    phase_embed,
    phase_title,
    participants_embed,
)
from .repositories import QsRepository
from .repositories.bases import BaseLimitReached, DuplicateBaseReport
from .views import OverviewView, PhaseView

if TYPE_CHECKING:
    from hmwz.client import Client

_logger = logging.getLogger(__name__)


@register
class QsModule(Module):
    """Manage Qs events without depending on registration or queue modules."""

    module_key = "qs"

    def __init__(self, guild: discord.Guild, client: Client) -> None:
        super().__init__(guild, client)
        if not isinstance(self.database, sqlite_db.Database):
            raise RuntimeError("Qs module requires a database.")
        self.qs = QsRepository(self.database)
        self._locks: dict[int, asyncio.Lock] = {}
        self._views: dict[int, discord.ui.View] = {}
        self._pending_updates: dict[
            int, tuple[set[int], set[int], asyncio.Task[bool]]
        ] = {}
        self._update_tasks: set[asyncio.Task[bool]] = set()
        self.notifications = QsNotifications(self)

    def _lock(self, channel_id: int) -> asyncio.Lock:
        return self._locks.setdefault(channel_id, asyncio.Lock())

    def _queue_update(
        self, channel_id: int, phase_index: int, *, bases: bool = False
    ) -> asyncio.Task[bool]:
        """Merge mutations into a bounded 250 ms channel update window."""
        pending = self._pending_updates.get(channel_id)
        if pending is None:
            signups: set[int] = set()
            reports: set[int] = set()
            task = asyncio.create_task(self._flush_update(channel_id, signups, reports))
            self._update_tasks.add(task)
            task.add_done_callback(self._update_tasks.discard)
            pending = (signups, reports, task)
            self._pending_updates[channel_id] = pending
        if bases:
            pending[1].add(phase_index)
        else:
            pending[0].add(phase_index)
        return pending[2]

    async def _flush_update(
        self, channel_id: int, signups: set[int], reports: set[int]
    ) -> bool:
        """Publish a batch under the channel lock using current persisted data."""
        await asyncio.sleep(0.25)
        async with self._lock(channel_id):
            self._pending_updates.pop(channel_id, None)
            return await self._refresh(
                channel_id, signup_phases=signups, base_phases=reports
            )

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
        eruption_start: int | None = None,
        durations: tuple[int, ...] | None = None,
    ) -> bool:
        """Configure one event, preserving existing signups and base reports."""
        timezone = await self.client.get_guild_timezone(self.guild.id)
        starts = phase_starts(date, hours, timezone, eruption_start=eruption_start)
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
        async with self._lock(channel_id):
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
                phases = await self.qs.phases(self.guild.id, channel_id)
                for phase in phases:
                    if phase.index <= len(starts):
                        continue
                    if await self.qs.members(
                        self.guild.id, channel_id, phase.index
                    ) or any(
                        report.phase_index == phase.index
                        for report in await self.qs.reports(self.guild.id, channel_id)
                    ):
                        _logger.warning(
                            "%s Reset required before removing a populated phase.",
                            log_guild(self.guild),
                        )
                        return False
                    thread = await existing_thread(self, channel_id, phase)
                    if thread is not None:
                        await delete_thread(thread, reason="Qs phase configuration")
                    if phase.message_id is not None:
                        view = self._views.pop(phase.message_id, None)
                        if view is not None:
                            view.stop()
                await self.qs.configure(
                    self.guild.id,
                    channel_id,
                    role_id,
                    date,
                    timezone,
                    starts,
                    eruption_start=eruption_start,
                    durations=durations,
                )
            except (aiosqlite.Error, discord.HTTPException, RuntimeError):
                _logger.exception(
                    "%s Failed to save Qs configuration.", log_guild(self.guild)
                )
                return False
            return await self._refresh(channel_id)

    async def authorize(
        self, interaction: discord.Interaction, channel_id: int
    ) -> Configuration | None:
        """Require the event's role on a member from this guild."""
        configuration = await self.qs.get(self.guild.id, channel_id)
        if (
            configuration is None
            or configuration.state != "active"
            or interaction.guild_id != self.guild.id
            or not isinstance(interaction.user, discord.Member)
            or not any(
                role.id == configuration.role_id for role in interaction.user.roles
            )
        ):
            await send_interaction_message(
                interaction, t(interaction, "qs.event.role_required")
            )
            return None
        return configuration

    async def toggle_phase(
        self, interaction: discord.Interaction, channel_id: int, phase_index: int
    ) -> None:
        """Toggle one phase without affecting the member's other phase signups."""
        await defer_interaction(interaction, thinking=True)
        async with self._lock(channel_id):
            if await self.authorize(interaction, channel_id) is None:
                return
            phases = await self.qs.phases(self.guild.id, channel_id)
            if not any(phase.index == phase_index for phase in phases):
                await send_interaction_message(
                    interaction, t(interaction, "qs.event.not_configured")
                )
                return
            try:
                joined = await self.qs.toggle(
                    self.guild.id, channel_id, phase_index, interaction.user.id
                )
            except aiosqlite.Error:
                _logger.exception("%s Failed to save Qs signup.", log_guild(self.guild))
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            update = self._queue_update(channel_id, phase_index)
        refreshed = await asyncio.shield(update)
        await send_followup(
            interaction,
            t(interaction, "qs.event.joined" if joined else "qs.event.left")
            + ("" if refreshed else "\n" + t(interaction, "qs.event.refresh_failed")),
        )

    async def report_base(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        phase_index: int,
        *,
        member: discord.Member | None = None,
    ) -> None:
        """Record one destroyed base per role holder across all five phases."""
        await defer_interaction(interaction, thinking=True)
        async with self._lock(channel_id):
            if member is None:
                if await self.authorize(interaction, channel_id) is None:
                    return
                reporter = interaction.user
            else:
                if not await self.authorize_moderation(interaction, channel_id):
                    return
                if member.guild.id != self.guild.id:
                    await send_interaction_message(
                        interaction, t(interaction, "qs.event.withdraw_denied")
                    )
                    return
                reporter = member
            if not any(
                phase.index == phase_index
                for phase in await self.qs.phases(self.guild.id, channel_id)
            ):
                await send_interaction_message(
                    interaction, t(interaction, "qs.event.not_configured")
                )
                return
            try:
                await self.qs.report(
                    self.guild.id,
                    channel_id,
                    phase_index,
                    reporter.id,
                    reporter.display_name,
                    int(time.time()),
                )
            except BaseLimitReached:
                await send_followup(interaction, t(interaction, "qs.event.base_limit"))
                return
            except DuplicateBaseReport:
                _logger.info(
                    "%s Duplicate Qs base report rejected.", log_guild(self.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.duplicate_report")
                )
                return
            except aiosqlite.IntegrityError as error:
                if error.sqlite_errorcode in (
                    sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
                    sqlite3.SQLITE_CONSTRAINT_UNIQUE,
                ):
                    _logger.info(
                        "%s Duplicate Qs base report rejected.", log_guild(self.guild)
                    )
                    await send_followup(
                        interaction, t(interaction, "qs.event.duplicate_report")
                    )
                    return
                _logger.exception(
                    "%s Failed to save Qs base report.", log_guild(self.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to save Qs base report.", log_guild(self.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            notified = await self.notifications.goals(channel_id)
            update = self._queue_update(channel_id, phase_index, bases=True)
        refreshed = await asyncio.shield(update)
        await send_followup(
            interaction,
            t(interaction, "qs.event.reported")
            + ("" if refreshed else "\n" + t(interaction, "qs.event.refresh_failed"))
            + (
                ""
                if notified
                else "\n" + t(interaction, "qs.admin.notification_failed")
            ),
        )

    async def authorize_moderation(
        self, interaction: discord.Interaction, channel_id: int
    ) -> bool:
        """Recheck moderator privileges and active event ownership."""
        from .setup import can_manage

        configuration = await self.qs.get(self.guild.id, channel_id)
        if (
            interaction.guild_id == self.guild.id
            and can_manage(interaction.user)
            and configuration is not None
            and configuration.state == "active"
        ):
            return True
        await send_interaction_message(
            interaction, t(interaction, "qs.event.withdraw_denied")
        )
        return False

    async def authorize_withdrawal(
        self, interaction: discord.Interaction, channel_id: int, member_id: int
    ) -> Configuration | None:
        """Allow role holders to retract their own report and moderators any report."""
        from .setup import can_manage

        configuration = await self.qs.get(self.guild.id, channel_id)
        member = interaction.user
        if (
            configuration is not None
            and configuration.state == "active"
            and interaction.guild_id == self.guild.id
            and isinstance(member, discord.Member)
            and (
                can_manage(member)
                or (
                    member.id == member_id
                    and any(role.id == configuration.role_id for role in member.roles)
                )
            )
        ):
            return configuration
        await send_interaction_message(
            interaction, t(interaction, "qs.event.withdraw_denied")
        )
        return None

    async def withdraw_base(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        phase_index: int,
        member_id: int,
    ) -> None:
        """Retract a report, refresh counters and preserve once-per-phase ping markers."""
        await defer_interaction(interaction, thinking=True)
        async with self._lock(channel_id):
            if (
                await self.authorize_withdrawal(interaction, channel_id, member_id)
                is None
            ):
                return
            try:
                removed = await self.qs.withdraw_report(
                    self.guild.id, channel_id, phase_index, member_id
                )
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to withdraw Qs report.", log_guild(self.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            if not removed:
                await send_followup(
                    interaction, t(interaction, "qs.event.withdraw_missing")
                )
                return
            update = self._queue_update(channel_id, phase_index, bases=True)
        refreshed = await asyncio.shield(update)
        await send_followup(
            interaction,
            t(interaction, "qs.event.withdrawn")
            + ("" if refreshed else "\n" + t(interaction, "qs.event.refresh_failed")),
        )

    async def ping_participants(self, channel_id: int, phase: Phase) -> bool:
        """Mention only enrolled players in their phase thread at phase start."""
        members = await self.qs.members(self.guild.id, channel_id, phase.index)
        if not members:
            return True
        thread = await existing_thread(self, channel_id, phase)
        if thread is None:
            _logger.warning(
                "%s Missing phase thread for participant notification.",
                log_guild(self.guild),
            )
            return False
        if thread.archived:
            thread = await edit_thread(thread, archived=False)
        for offset in range(0, len(members), 100):
            batch = members[offset : offset + 100]
            if (
                await send_message(
                    thread,
                    content=t(
                        self.guild,
                        "qs.admin.ping_phase_start",
                        phase=phase.index,
                        members=" ".join(f"<@{member}>" for member in batch),
                    ),
                    allowed_mentions=discord.AllowedMentions(
                        users=[discord.Object(id=member) for member in batch],
                        roles=False,
                        everyone=False,
                    ),
                )
                is None
            ):
                return False
        return True

    async def ping(
        self, channel_id: int, *, event: str = "manual", phase_index: int | None = None
    ) -> bool:
        """Send an intentional ping restricted to this channel's configured role."""
        configuration = await self.qs.get(self.guild.id, channel_id)
        channel = self.guild.get_channel(channel_id)
        if (
            configuration is None
            or configuration.state != "active"
            or not isinstance(channel, discord.TextChannel)
        ):
            _logger.warning(
                "%s Qs ping has no configured text channel.", log_guild(self.guild)
            )
            return False
        role = self.guild.get_role(configuration.role_id)
        if role is None:
            _logger.warning("%s Qs ping role no longer exists.", log_guild(self.guild))
            return False
        if not role.mentionable and (
            self.guild.me is None
            or not channel.permissions_for(self.guild.me).mention_everyone
        ):
            _logger.warning(
                "%s Bot cannot mention the configured Qs role.", log_guild(self.guild)
            )
            return False
        return (
            await send_message(
                channel,
                content=t(
                    self.guild,
                    "qs.event.ping" if event == "manual" else f"qs.admin.ping_{event}",
                    role=role.mention,
                    phase=phase_index,
                ),
                allowed_mentions=discord.AllowedMentions(
                    roles=[role], users=False, everyone=False
                ),
            )
            is not None
        )

    async def _thread(
        self, channel: discord.TextChannel, phase: Phase, timezone: str
    ) -> discord.Thread:
        title = phase_title(self.guild, phase, timezone)
        if phase.thread_id is not None:
            candidate = await fetch_thread(self.guild, phase.thread_id)
            if (
                isinstance(candidate, discord.Thread)
                and candidate.parent_id == channel.id
            ):
                if candidate.archived or candidate.name != title:
                    candidate = await edit_thread(candidate, name=title, archived=False)
                return candidate
        thread = await create_thread(
            channel,
            name=title,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=10080,
        )
        if not await self.qs.save_thread(
            self.guild.id, channel.id, phase.index, thread.id, None
        ):
            raise RuntimeError("Failed to save Qs thread.")
        return thread

    async def _message(
        self,
        target: discord.TextChannel | discord.Thread,
        message_id: int | None,
        *,
        embeds: list[discord.Embed],
        view: discord.ui.View | None = None,
    ) -> discord.Message:
        message = None
        if message_id is not None:
            try:
                message = await fetch_message(target, message_id, raise_on_error=True)
            except discord.NotFound:
                previous = self._views.pop(message_id, None)
                if previous is not None:
                    previous.stop()
        kwargs = {
            "embeds": embeds,
            "view": view,
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        result = (
            await edit_message(message, **kwargs)
            if message is not None
            else await send_message(target, **kwargs)
        )
        if result is None:
            raise RuntimeError("Failed to publish Qs message.")
        if view is not None:
            previous = self._views.pop(result.id, None)
            if previous is not None:
                previous.stop()
            self.client.add_view(view, message_id=result.id)
            self._views[result.id] = view
        return result

    async def _refresh(
        self,
        channel_id: int,
        *,
        signup_phases: set[int] | None = None,
        base_phases: set[int] | None = None,
    ) -> bool:
        """Restore everything or patch only messages affected by a mutation batch."""
        full = signup_phases is None and base_phases is None
        try:
            configuration = await self.qs.get(self.guild.id, channel_id)
            channel = self.guild.get_channel(channel_id)
            if (
                configuration is None
                or configuration.state != "active"
                or not isinstance(channel, discord.TextChannel)
            ):
                _logger.warning(
                    "%s Cannot restore Qs channel %s.",
                    log_guild(self.guild),
                    channel_id,
                )
                return False
            timezone = await self.client.get_guild_timezone(self.guild.id)
            phases = await self.qs.phases(self.guild.id, channel_id)
            reports = await self.qs.reports(self.guild.id, channel_id)
            members = {
                phase.index: await self.qs.members(
                    self.guild.id, channel_id, phase.index
                )
                for phase in phases
            }
            for phase in phases:
                signup_changed = full or phase.index in (signup_phases or set())
                bases_changed = full or phase.index in (base_phases or set())
                if not signup_changed and not bases_changed:
                    continue
                thread = await self._thread(channel, phase, timezone)
                recreated = phase.thread_id != thread.id
                if bases_changed or recreated:
                    message = await self._message(
                        thread,
                        phase.message_id,
                        embeds=[phase_embed(self.guild, phase, reports)],
                        view=PhaseView(self, channel_id, phase),
                    )
                    if not await self.qs.save_thread(
                        self.guild.id, channel_id, phase.index, thread.id, message.id
                    ):
                        return False
                if signup_changed or recreated:
                    participants = await self._message(
                        thread,
                        phase.members_message_id
                        if phase.thread_id == thread.id
                        else None,
                        embeds=[
                            participants_embed(self.guild, phase, members[phase.index])
                        ],
                    )
                    if not await self.qs.save_members_message(
                        self.guild.id, channel_id, phase.index, participants.id
                    ):
                        return False
            phases = await self.qs.phases(self.guild.id, channel_id)
            message = await self._message(
                channel,
                configuration.message_id,
                embeds=[
                    overview_embed(
                        self.guild, configuration, phases, members, len(reports)
                    )
                ],
                view=OverviewView(self, channel_id, phases, timezone),
            )
            # Persist each successful Discord operation before starting the next.
            if not await self.qs.database.execute(
                "UPDATE HsQsEvents SET Message=? WHERE Guild=? AND Channel=?",
                (message.id, self.guild.id, channel_id),
            ):
                return False
            if not full and not base_phases:
                return True
            listing = await self._message(
                channel,
                configuration.bases_message_id,
                embeds=bases_embeds(self.guild, reports),
            )
            return await self.qs.save_messages(
                self.guild.id, channel_id, message.id, listing.id
            )
        except (discord.HTTPException, aiosqlite.Error, RuntimeError):
            _logger.exception(
                "%s Failed to restore Qs channel %s.", log_guild(self.guild), channel_id
            )
            return False

    async def ensure(self) -> bool:
        """Restore all messages and register persistent buttons after restart."""
        success = True
        for configuration in await self.qs.all(self.guild.id):
            if configuration.state != "active":
                continue
            async with self._lock(configuration.channel_id):
                if not await self._refresh(configuration.channel_id):
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
        if self._update_tasks:
            await asyncio.gather(*tuple(self._update_tasks))

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
        eruption_start: int,
        durations: tuple[int, ...],
    ) -> bool:
        """Validate the replacement schedule before any destructive cleanup."""
        timezone = await self.client.get_guild_timezone(self.guild.id)
        starts = phase_starts(date, hours, timezone, eruption_start=eruption_start)
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
        for view in self._views.values():
            view.stop()
        self._views.clear()
        return await self.qs.remove(self.guild.id)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Cascade data deletion only for a deleted Qs overview channel."""
        if channel.guild.id != self.guild.id:
            return False
        async with self._lock(channel.id):
            configuration = await self.qs.get(self.guild.id, channel.id)
            phases = await self.qs.phases(self.guild.id, channel.id)
            if not await self.qs.remove(self.guild.id, channel.id):
                return False
            if configuration is not None:
                message_ids = {configuration.message_id}
                message_ids.update(phase.message_id for phase in phases)
                for message_id in message_ids:
                    if message_id is not None:
                        view = self._views.pop(message_id, None)
                        if view is not None:
                            view.stop()
            return True

    async def _remove_signups(self, channel_id: int, member_id: int) -> bool:
        """Remove signups and enqueue only phase lists that contained the member."""
        async with self._lock(channel_id):
            affected = [
                phase.index
                for phase in await self.qs.phases(self.guild.id, channel_id)
                if member_id
                in await self.qs.members(self.guild.id, channel_id, phase.index)
            ]
            if not await self.qs.remove_member(self.guild.id, member_id, channel_id):
                return False
            updates = [self._queue_update(channel_id, index) for index in affected]
        return all(await asyncio.gather(*(asyncio.shield(task) for task in updates)))

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
            if not await self._remove_signups(configuration.channel_id, after.id):
                success = False
        return success

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool:
        """Remove a departed member's signups without changing destroyed-base counts."""
        if payload.guild_id != self.guild.id:
            return False
        success = True
        for configuration in await self.qs.all(self.guild.id):
            if not await self._remove_signups(
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
                async with self._lock(configuration.channel_id):
                    if phase.message_id is not None:
                        view = self._views.pop(phase.message_id, None)
                        if view is not None:
                            view.stop()
                    if not await self.qs.database.execute(
                        "UPDATE HsQsPhases SET Thread=NULL, Message=NULL "
                        "WHERE Guild=? AND Channel=? AND Phase=?",
                        (self.guild.id, configuration.channel_id, phase.index),
                    ):
                        return False
                    return await self._refresh(configuration.channel_id)
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
        return await self._restore_deleted({message.id})

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Restore managed messages even when absent from the message cache."""
        if payload.guild_id != self.guild.id:
            return False
        return await self._restore_deleted({payload.message_id})

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Restore a batch of managed messages once per affected channel."""
        if payload.guild_id != self.guild.id:
            return False
        return await self._restore_deleted(set(payload.message_ids))

    async def _restore_deleted(self, message_ids: set[int]) -> bool:
        success = True
        for configuration in await self.qs.all(self.guild.id):
            if configuration.state != "active":
                continue
            phases = await self.qs.phases(self.guild.id, configuration.channel_id)
            managed = {configuration.message_id, configuration.bases_message_id}
            managed.update(phase.message_id for phase in phases)
            managed.update(phase.members_message_id for phase in phases)
            if managed & message_ids:
                for message_id in message_ids:
                    view = self._views.pop(message_id, None)
                    if view is not None:
                        view.stop()
                async with self._lock(configuration.channel_id):
                    if not await self._refresh(configuration.channel_id):
                        success = False
        return success
