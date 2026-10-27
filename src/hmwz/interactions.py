from __future__ import annotations

import asyncio
import logging
from typing import Any, cast, Callable

import discord

_logger = logging.getLogger(__name__)
_delete_tasks: set[asyncio.Task[None]] = set()


def _retain_task(task: asyncio.Task[None]) -> None:
    _delete_tasks.add(task)
    task.add_done_callback(_delete_tasks.discard)


def interaction_response_done(interaction: discord.Interaction) -> bool:
    """Return whether an interaction has already received its initial response."""
    is_done = getattr(interaction.response, "is_done", None)
    return bool(is_done()) if callable(is_done) else False


async def defer_interaction(
    interaction: discord.Interaction,
    *,
    ephemeral: bool = False,
    thinking: bool = False,
) -> bool:
    """Acknowledge an interaction once, ignoring stale/duplicate acknowledgements."""
    if interaction_response_done(interaction):
        return True
    try:
        await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
    except discord.InteractionResponded:
        return True
    except (discord.NotFound, discord.HTTPException):
        _logger.exception("Failed to defer an interaction response.")
        return False
    return True


async def respond(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    ephemeral: bool = False,
    **kwargs: Any,
) -> discord.Message | None:
    """Send an initial response or a follow-up when the interaction is acknowledged."""
    if interaction_response_done(interaction):
        return await safe_followup(interaction, content, ephemeral=ephemeral, **kwargs)

    try:
        await interaction.response.send_message(content, ephemeral=ephemeral, **kwargs)
    except discord.InteractionResponded:
        return await safe_followup(interaction, content, ephemeral=ephemeral, **kwargs)
    except (discord.NotFound, discord.HTTPException):
        _logger.exception("Failed to send an interaction response.")
        return None

    try:
        return await interaction.original_response()
    except (discord.NotFound, discord.HTTPException):
        _logger.exception("Unable to retrieve the interaction response message.")
        return None


async def safe_followup(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    ephemeral: bool = False,
    **kwargs: Any,
) -> discord.Message | None:
    """Send a follow-up and return its message when Discord provides one."""
    try:
        send = cast(Any, interaction.followup.send)
        message = await send(content, ephemeral=ephemeral, wait=True, **kwargs)
    except (discord.NotFound, discord.HTTPException):
        _logger.exception("Failed to send an interaction follow-up.")
        return None
    return message


async def safe_edit_message(
    message: discord.Message | None, **kwargs: Any
) -> discord.Message | None:
    """Edit a message only while it remains available."""
    if message is None:
        return None
    try:
        return await message.edit(**kwargs)
    except discord.NotFound:
        _logger.debug("Skipped editing a deleted message.")
    except discord.HTTPException:
        _logger.exception("Failed to edit a message.")
    return None


async def safe_edit_original_response(
    interaction: discord.Interaction, **kwargs: Any
) -> discord.Message | None:
    """Edit an interaction response while tolerating expired response tokens."""
    try:
        return await interaction.edit_original_response(**kwargs)
    except discord.NotFound:
        _logger.debug("Skipped editing a deleted interaction response.")
    except discord.HTTPException:
        _logger.exception("Failed to edit an interaction response.")
    return None


async def safe_delete_message(
    message: discord.Message | None, *, delay: float | None = None
) -> bool:
    """Delete a message, treating an already-deleted message as a successful no-op."""
    if message is None:
        return True
    delete : Callable | None = getattr(message, "delete", None)
    if not callable(delete):
        _logger.debug("Skipped deletion for an unavailable message object.")
        return False
    try:
        if delay is None:
            await delete()
        else:
            await delete(delay=delay)
    except discord.NotFound:
        return True
    except discord.HTTPException:
        _logger.exception("Failed to delete a message.")
        return False
    return True


async def safe_delete_original_response(
    interaction: discord.Interaction,
) -> bool:
    """Delete an interaction response without failing if Discord has removed it."""
    try:
        await interaction.delete_original_response()
    except discord.NotFound:
        return True
    except discord.HTTPException:
        _logger.exception("Failed to delete an interaction response.")
        return False
    return True


async def send_temporary_response(
    interaction: discord.Interaction,
    content: str,
    *,
    delay: float = 5,
    ephemeral: bool = True,
    **kwargs: Any,
) -> None:
    """Send a short-lived response, using follow-up delivery after prior acknowledgement."""
    message = await respond(interaction, content, ephemeral=ephemeral, **kwargs)
    if message is not None:
        await safe_delete_message(message, delay=delay)


async def send_temporary_followup(
    interaction: discord.Interaction,
    content: str,
    *,
    ephemeral: bool = True,
    delay: float = 5,
    schedule: bool = False,
    file: discord.File | None = None,
) -> None:
    """Send a short-lived follow-up, optionally with an attachment."""
    kwargs = {"file": file} if file is not None else {}
    message = await safe_followup(interaction, content, ephemeral=ephemeral, **kwargs)
    if message is not None and schedule:
        schedule_temporary_delete(message, delay)
    elif message is not None:
        await safe_delete_message(message, delay=delay)


async def delete_temporary_message(message: discord.Message | None) -> None:
    """Delete a temporary message while tolerating expired/deleted message states."""
    await safe_delete_message(message)


async def _delete_after(message: discord.Message, delay: float) -> None:
    await asyncio.sleep(delay)
    await safe_delete_message(message)


def schedule_temporary_delete(message: discord.Message, delay: float) -> None:
    """Schedule best-effort deletion without blocking an interaction callback."""
    task = asyncio.create_task(_delete_after(message, delay))
    _retain_task(task)


__all__ = [
    "defer_interaction",
    "delete_temporary_message",
    "interaction_response_done",
    "respond",
    "safe_delete_message",
    "safe_delete_original_response",
    "safe_edit_message",
    "safe_edit_original_response",
    "safe_followup",
    "schedule_temporary_delete",
    "send_temporary_followup",
    "send_temporary_response",
]
