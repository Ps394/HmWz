"""Destructive Qs operations, restricted to the configured event resources."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz.ui.messages import delete_message
from hmwz.utils.interactions import log_guild
from hmwz.utils.loaders import fetch_message, fetch_thread
from hmwz.ui.threads import delete_thread, edit_thread, purge_messages

from .models import Configuration, Phase

if TYPE_CHECKING:
    from .module import QsModule

_logger = logging.getLogger(__name__)


async def existing_thread(
    module: QsModule, channel_id: int, phase: Phase
) -> discord.Thread | None:
    """Resolve only a saved Qs thread; never create a replacement during cleanup."""
    if phase.thread_id is None:
        return None
    thread = await fetch_thread(module.guild, phase.thread_id)
    if thread is None:
        return None
    if thread.parent_id != channel_id:
        raise RuntimeError("Qs thread belongs to a different parent channel.")
    return thread


def stop_views(
    module: QsModule, configuration: Configuration, phases: tuple[Phase, ...]
) -> None:
    """Disable all controls for an event before deleting its Discord resources."""
    module.notifications.pending = {
        key
        for key in module.notifications.pending
        if key[0] != configuration.channel_id
    }
    ids = {configuration.message_id}
    ids.update(phase.message_id for phase in phases)
    for message_id in ids:
        if message_id is not None:
            view = module._views.pop(message_id, None)
            if view is not None:
                view.stop()


async def remove_event(module: QsModule, channel_id: int) -> bool:
    """Delete managed threads, overview messages and data, preserving the main channel."""
    async with module._lock(channel_id):
        configuration = await module.qs.get(module.guild.id, channel_id)
        if configuration is None:
            return True
        phases = await module.qs.phases(module.guild.id, channel_id)
        if not await module.qs.set_state(module.guild.id, channel_id, "removing"):
            return False
        stop_views(module, configuration, phases)
        try:
            for phase in phases:
                thread = await existing_thread(module, channel_id, phase)
                if thread is not None:
                    await delete_thread(thread, reason="Qs tool removal")
            channel = module.guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                for message_id in (
                    configuration.message_id,
                    configuration.bases_message_id,
                ):
                    if message_id is None:
                        continue
                    try:
                        message = await fetch_message(
                            channel, message_id, raise_on_error=True
                        )
                    except discord.NotFound:
                        continue
                    if not await delete_message(message):
                        return False
            elif channel is not None:
                raise RuntimeError("Qs main channel is not a text channel.")
            return await module.qs.remove(module.guild.id, channel_id)
        except (discord.HTTPException, aiosqlite.Error, RuntimeError):
            _logger.exception(
                "%s Qs removal failed; retry removal to finish.",
                log_guild(module.guild),
            )
            return False


async def reset_event(
    module: QsModule,
    channel_id: int,
    *,
    date: str,
    timezone: str,
    starts: tuple[int, ...],
    eruption_start: int,
    durations: tuple[int, ...],
) -> bool:
    """Purge all event-channel messages and atomically start a fresh cycle."""
    async with module._lock(channel_id):
        configuration = await module.qs.get(module.guild.id, channel_id)
        channel = module.guild.get_channel(channel_id)
        if (
            configuration is None
            or configuration.state == "removing"
            or not isinstance(channel, discord.TextChannel)
        ):
            _logger.warning(
                "%s Qs reset requires a configured text channel.",
                log_guild(module.guild),
            )
            return False
        phases = await module.qs.phases(module.guild.id, channel_id)
        if not await module.qs.set_state(module.guild.id, channel_id, "resetting"):
            return False
        stop_views(module, configuration, phases)
        try:
            for phase in phases:
                thread = await existing_thread(module, channel_id, phase)
                if thread is None:
                    continue
                if phase.index > len(starts):
                    await delete_thread(thread, reason="Qs phase removed on reset")
                    continue
                if thread.archived or thread.locked:
                    await edit_thread(thread, archived=False, locked=False)
                await purge_messages(thread, limit=None, reason="Qs cycle reset")
            await purge_messages(channel, limit=None, reason="Qs cycle reset")
            await module.qs.configure(
                module.guild.id,
                channel_id,
                configuration.role_id,
                date,
                timezone,
                starts,
                eruption_start=eruption_start,
                durations=durations,
                reset=True,
            )
            return await module._refresh(channel_id)
        except (discord.HTTPException, aiosqlite.Error, RuntimeError):
            _logger.exception(
                "%s Qs reset failed; retry reset to finish.", log_guild(module.guild)
            )
            return False
