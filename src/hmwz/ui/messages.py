from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord

logger = logging.getLogger(__name__)
_delete_tasks: set[asyncio.Task[None]] = set()


async def send_message(
    target: discord.abc.Messageable, **kwargs: Any
) -> discord.Message | None:
    """Send a message, logging Discord failures and returning None on failure."""
    try:
        return await target.send(**kwargs)
    except discord.NotFound:
        logger.info("Discord message target was not found while sending.")
    except discord.Forbidden:
        logger.warning("Discord denied sending a message.")
    except discord.RateLimited:
        logger.warning("Discord rate-limited sending a message.")
    except discord.HTTPException:
        logger.exception("Discord failed to send a message.")
    return None


async def edit_message(
    message: discord.Message, **kwargs: Any
) -> discord.Message | None:
    """Edit a message, logging Discord failures and returning None on failure."""
    try:
        return await message.edit(**kwargs)
    except discord.NotFound:
        logger.info("Discord message was not found while editing.")
    except discord.Forbidden:
        logger.warning("Discord denied editing a message.")
    except discord.RateLimited:
        logger.warning("Discord rate-limited editing a message.")
    except discord.HTTPException:
        logger.exception("Discord failed to edit a message.")
    return None


async def delete_message(message: discord.Message, **kwargs: Any) -> bool:
    """Delete a message; treat an already-missing message as successfully deleted."""
    try:
        await message.delete(**kwargs)
    except discord.NotFound:
        return True
    except discord.Forbidden:
        logger.warning("Discord denied deleting a message.")
        return False
    except discord.RateLimited:
        logger.warning("Discord rate-limited deleting a message.")
        return False
    except discord.HTTPException:
        logger.exception("Discord failed to delete a message.")
        return False
    return True


async def delete_temporary_message(
    message: discord.Message | None, *, delay: float = 0
) -> None:
    """Delete an optional temporary message, ignoring Discord operation failures."""
    if message is not None:
        await delete_message(message, delay=delay)


async def send_temporary_followup(
    interaction: discord.Interaction,
    content: str,
    *,
    ephemeral: bool = True,
    file: discord.File | None = None,
    delay: float | None = None,
) -> discord.Message | None:
    """Send a followup and optionally schedule its deletion after the given delay."""
    kwargs: dict[str, Any] = {"ephemeral": ephemeral, "wait": True}
    if file is not None:
        kwargs["file"] = file
    message = await interaction.followup.send(content, **kwargs)
    if message is None:
        logger.warning("Discord did not return a message for a temporary followup.")
    elif delay is not None:
        task = asyncio.create_task(_delete_after(message, delay))
        retain_delete_task(task)
    return message


async def send_temporary_response(
    interaction: discord.Interaction, content: str, *, delay: float
) -> None:
    """Send an ephemeral interaction response and remove it after the given delay."""
    await interaction.response.send_message(content, ephemeral=True)
    message = await interaction.original_response()
    await delete_message(message, delay=delay)


def retain_delete_task(task: asyncio.Task[None]) -> None:
    """Keep a scheduled message-deletion task alive until it completes."""
    _delete_tasks.add(task)
    task.add_done_callback(_delete_tasks.discard)


async def _delete_after(message: discord.Message, delay: float) -> None:
    await asyncio.sleep(delay)
    await delete_temporary_message(message)
