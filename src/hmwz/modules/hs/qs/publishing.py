"""Serialized publishing of the Qs overview, base listing and phase messages."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz.ui.messages import delete_message, edit_message, send_message
from hmwz.utils.interactions import log_guild
from hmwz.utils.loaders import fetch_message

from .models import Phase
from .overview import OverviewView, bases_embeds, overview_embed
from .phases.embeds import phase_title
from .phases.publishing import publish_phase

if TYPE_CHECKING:
    from .module import QsModule

_logger = logging.getLogger(__name__)


class QsPublisher:
    """Own per-channel locks, persistent views and the batched message refresh."""

    def __init__(self, module: QsModule) -> None:
        self.module = module
        self.locks: dict[int, asyncio.Lock] = {}
        self.views: dict[int, discord.ui.View] = {}
        self.pending_updates: dict[
            int, tuple[set[int], set[int], asyncio.Task[bool]]
        ] = {}
        self.update_tasks: set[asyncio.Task[bool]] = set()

    def lock(self, channel_id: int) -> asyncio.Lock:
        return self.locks.setdefault(channel_id, asyncio.Lock())

    def stop_view(self, message_id: int | None) -> None:
        """Stop and forget the persistent view registered for a message."""
        if message_id is None:
            return
        view = self.views.pop(message_id, None)
        if view is not None:
            view.stop()

    def stop_all_views(self) -> None:
        for view in self.views.values():
            view.stop()
        self.views.clear()

    def queue_update(
        self, channel_id: int, phase_index: int, *, bases: bool = False
    ) -> asyncio.Task[bool]:
        """Merge mutations into a bounded 250 ms channel update window."""
        pending = self.pending_updates.get(channel_id)
        if pending is None:
            signups: set[int] = set()
            reports: set[int] = set()
            task = asyncio.create_task(self._flush_update(channel_id, signups, reports))
            self.update_tasks.add(task)
            task.add_done_callback(self.update_tasks.discard)
            pending = (signups, reports, task)
            self.pending_updates[channel_id] = pending
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
        async with self.lock(channel_id):
            self.pending_updates.pop(channel_id, None)
            return await self.refresh(
                channel_id, signup_phases=signups, base_phases=reports
            )

    async def message(
        self,
        target: discord.TextChannel | discord.Thread,
        message_id: int | None,
        *,
        embeds: list[discord.Embed],
        view: discord.ui.View | None = None,
    ) -> discord.Message:
        """Edit the saved message, or send a replacement when it was deleted."""
        message = None
        if message_id is not None:
            try:
                message = await fetch_message(target, message_id, raise_on_error=True)
            except discord.NotFound:
                self.stop_view(message_id)
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
            self.stop_view(result.id)
            self.module.client.add_view(view, message_id=result.id)
            self.views[result.id] = view
        return result

    async def refresh(
        self,
        channel_id: int,
        *,
        signup_phases: set[int] | None = None,
        base_phases: set[int] | None = None,
    ) -> bool:
        """Restore everything or patch only messages affected by a mutation batch."""
        module = self.module
        guild = module.guild
        full = signup_phases is None and base_phases is None
        try:
            configuration = await module.qs.get(guild.id, channel_id)
            channel = guild.get_channel(channel_id)
            if (
                configuration is None
                or configuration.state != "active"
                or not isinstance(channel, discord.TextChannel)
            ):
                _logger.warning(
                    "%s Cannot restore Qs channel %s.", log_guild(guild), channel_id
                )
                return False
            timezone = await module.client.get_guild_timezone(guild.id)
            phases = await module.qs.phases(guild.id, channel_id)
            reports = await module.qs.reports(guild.id, channel_id)
            signups = {
                phase.index: await module.qs.member_signups(
                    guild.id, channel_id, phase.index
                )
                for phase in phases
            }
            members = {
                phase.index: tuple(signup.member_id for signup in signups[phase.index])
                for phase in phases
            }
            for phase in phases:
                signup_changed = full or phase.index in (signup_phases or set())
                bases_changed = full or phase.index in (base_phases or set())
                if not signup_changed and not bases_changed:
                    continue
                if not await publish_phase(
                    module,
                    channel,
                    phase,
                    timezone,
                    reports=reports,
                    signups=signups,
                    signup_changed=signup_changed,
                    bases_changed=bases_changed,
                ):
                    return False
            phases = await module.qs.phases(guild.id, channel_id)
            message = await self.message(
                channel,
                configuration.message_id,
                embeds=[
                    overview_embed(guild, configuration, phases, members, len(reports))
                ],
                view=OverviewView(module, channel_id, phases),
            )
            # Persist each successful Discord operation before starting the next.
            if not await module.qs.database.execute(
                "UPDATE HsQsEvents SET Message=? WHERE Guild=? AND Channel=?",
                (message.id, guild.id, channel_id),
            ):
                return False
            if not full and not base_phases:
                return await self._delete_thread_creation_messages(
                    channel, phases, timezone
                )
            listing = await self.message(
                channel,
                configuration.bases_message_id,
                embeds=bases_embeds(guild, reports),
            )
            saved = await module.qs.save_messages(
                guild.id, channel_id, message.id, listing.id
            )
            return saved and await self._delete_thread_creation_messages(
                channel, phases, timezone
            )
        except (discord.HTTPException, aiosqlite.Error, RuntimeError):
            _logger.exception(
                "%s Failed to restore Qs channel %s.", log_guild(guild), channel_id
            )
            return False

    async def _delete_thread_creation_messages(
        self,
        channel: discord.TextChannel,
        phases: tuple[Phase, ...],
        timezone: str,
    ) -> bool:
        """Delete recent bot-generated notices for the configured Qs threads."""
        module = self.module
        bot_user = module.client.user
        if bot_user is None:
            _logger.warning(
                "%s Cannot identify Qs thread creation notices without the bot user.",
                log_guild(module.guild),
            )
            return False
        titles = {phase_title(module.guild, phase, timezone) for phase in phases}
        try:
            async for message in channel.history(limit=100):
                if (
                    message.type == discord.MessageType.thread_created
                    and message.author.id == bot_user.id
                    and message.content in titles
                    and not await delete_message(message)
                ):
                    return False
        except (discord.HTTPException, discord.RateLimited):
            _logger.exception(
                "%s Failed to inspect Qs thread creation notices.",
                log_guild(module.guild),
            )
            return False
        return True

    async def restore_deleted(self, message_ids: set[int]) -> bool:
        """Recreate managed messages that were deleted from Discord."""
        module = self.module
        success = True
        for configuration in await module.qs.all(module.guild.id):
            if configuration.state != "active":
                continue
            phases = await module.qs.phases(module.guild.id, configuration.channel_id)
            managed = {configuration.message_id, configuration.bases_message_id}
            managed.update(phase.message_id for phase in phases)
            managed.update(phase.members_message_id for phase in phases)
            if managed & message_ids:
                for message_id in message_ids:
                    self.stop_view(message_id)
                async with self.lock(configuration.channel_id):
                    if not await self.refresh(configuration.channel_id):
                        success = False
        return success
