"""Shared thread operations that log failures without hiding them."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal, TypedDict, Unpack

import discord

logger = logging.getLogger(__name__)
ArchiveDuration = Literal[60, 1440, 4320, 10080]


class ThreadEditOptions(TypedDict, total=False):
    """Supported thread metadata changes, forwarded unchanged to Discord."""

    name: str
    archived: bool
    locked: bool
    auto_archive_duration: ArchiveDuration
    reason: str


class _PurgeOptions(TypedDict, total=False):
    """Optional message-selection predicate for Discord purge calls."""

    check: Callable[[discord.Message], bool]


async def create_thread(
    channel: discord.TextChannel,
    *,
    name: str,
    type: discord.ChannelType = discord.ChannelType.public_thread,
    auto_archive_duration: ArchiveDuration = 10080,
    reason: str | None = None,
) -> discord.Thread:
    """Create a thread, propagating Discord failures after logging them.

    Args:
        channel: Parent text channel.
        name: Thread title.
        type: Public or private thread type.
        auto_archive_duration: Inactivity duration in minutes.
        reason: Optional audit-log reason.

    Returns:
        The created thread.

    Raises:
        discord.HTTPException: If Discord rejects creation.
        discord.RateLimited: If Discord's rate limit cannot be handled.
    """
    try:
        return await channel.create_thread(
            name=name,
            type=type,
            auto_archive_duration=auto_archive_duration,
            reason=reason,
        )
    except (discord.HTTPException, discord.RateLimited):
        logger.exception("Discord failed to create a thread in channel %s.", channel.id)
        raise


async def edit_thread(
    thread: discord.Thread, **kwargs: Unpack[ThreadEditOptions]
) -> discord.Thread:
    """Update thread metadata, logging and propagating Discord failures.

    Args:
        thread: Thread to update.
        **kwargs: Metadata changes and optional audit-log reason.

    Returns:
        The updated thread returned by Discord.

    Raises:
        discord.HTTPException: If Discord rejects the update.
        discord.RateLimited: If Discord's rate limit cannot be handled.
    """
    try:
        return await thread.edit(**kwargs)
    except (discord.HTTPException, discord.RateLimited):
        logger.exception("Discord failed to edit thread %s.", thread.id)
        raise


async def delete_thread(thread: discord.Thread, *, reason: str | None = None) -> None:
    """Delete a thread, treating an already missing thread as deleted.

    Args:
        thread: Thread to delete.
        reason: Optional audit-log reason.

    Raises:
        discord.HTTPException: If deletion fails for reasons other than absence.
        discord.RateLimited: If Discord's rate limit cannot be handled.
    """
    try:
        await thread.delete(reason=reason)
    except discord.NotFound:
        return
    except (discord.HTTPException, discord.RateLimited):
        logger.exception("Discord failed to delete thread %s.", thread.id)
        raise


async def purge_messages(
    channel: discord.TextChannel | discord.Thread,
    *,
    limit: int | None = 100,
    check: Callable[[discord.Message], bool] | None = None,
    bulk: bool = True,
    reason: str | None = None,
) -> list[discord.Message]:
    """Purge messages, automatically disabling bulk deletion in threads.

    Args:
        channel: Text channel or thread to clean.
        limit: Messages to inspect, or None for all messages.
        check: Optional predicate selecting messages to delete.
        bulk: Whether to bulk-delete in text channels; ignored for threads.
        reason: Optional audit-log reason.

    Returns:
        The deleted messages.

    Raises:
        discord.HTTPException: If fetching or deleting messages fails.
        discord.RateLimited: If Discord's rate limit cannot be handled.
    """
    options: _PurgeOptions = {}
    if check is not None:
        options["check"] = check
    try:
        if isinstance(channel, discord.Thread):
            return await channel.purge(
                limit=limit, bulk=False, reason=reason, **options
            )
        return await channel.purge(limit=limit, bulk=bulk, reason=reason, **options)
    except (discord.HTTPException, discord.RateLimited):
        logger.exception("Discord failed to purge channel %s.", channel.id)
        raise
