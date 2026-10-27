from __future__ import annotations

import logging
from typing import Any

import discord

logger = logging.getLogger(__name__)


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
    except discord.HTTPException:
        logger.exception("Discord failed to delete a message.")
        return False
    return True
