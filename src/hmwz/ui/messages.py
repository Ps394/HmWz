"""Shared Discord message operations with consistent error handling."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord

from hmwz.emojis import emojis

logger = logging.getLogger(__name__)
_delete_tasks: set[asyncio.Task[None]] = set()


async def defer_interaction(
    interaction: discord.Interaction, *, ephemeral: bool = True, thinking: bool = False
) -> None:
    """Acknowledge an interaction, propagating failures to the caller.

    Args:
        interaction: Interaction that has not yet been acknowledged.
        ephemeral: Whether a deferred response should be private.
        thinking: Whether to defer a new response instead of a component update.

    Raises:
        discord.InteractionResponded: If already acknowledged.
        discord.HTTPException: If Discord rejects the acknowledgement.
    """
    await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)


async def send_modal(interaction: discord.Interaction, modal: discord.ui.Modal) -> None:
    """Open a modal as the initial response, propagating failures.

    Args:
        interaction: Interaction that has not yet been acknowledged.
        modal: Modal to open.

    Raises:
        discord.InteractionResponded: If already acknowledged.
        discord.HTTPException: If Discord rejects the modal.
    """
    await interaction.response.send_modal(modal)


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
        if delay > 0:
            await delete_message(message, delay=delay)
        else:
            await delete_message(message)


async def dismiss_dialog(interaction: discord.Interaction) -> None:
    """Close a component dialog through Discord's interaction endpoint.

    A component-update acknowledgement keeps the original response pointing to
    the clicked dialog, including ephemeral messages.

    Args:
        interaction: Component interaction for the dialog being closed.

    Raises:
        discord.HTTPException: If acknowledgement or deletion fails.
        discord.RateLimited: If Discord cannot handle the rate limit.
        ValueError: If the interaction is not an unacknowledged component click.
    """
    if (
        interaction.type != discord.InteractionType.component
        or interaction.response.is_done()
    ):
        logger.error(
            "Dialog dismissal requires an unacknowledged component interaction."
        )
        raise ValueError(
            "Dialog dismissal requires an unacknowledged component interaction."
        )
    await defer_interaction(interaction, thinking=False)
    try:
        await interaction.delete_original_response()
    except discord.NotFound:
        return
    except (discord.HTTPException, discord.RateLimited):
        logger.exception("Discord failed to dismiss an interaction dialog.")
        raise


async def send_interaction_response(
    interaction: discord.Interaction, content: str | None = None, **kwargs: Any
) -> discord.InteractionMessage:
    """Send a private initial response; propagate failures to the caller."""
    kwargs.setdefault("ephemeral", True)
    await interaction.response.send_message(
        emojis.render(content, interaction) if content is not None else None,
        **kwargs,
    )
    return await interaction.original_response()


async def send_followup(
    interaction: discord.Interaction, content: str | None = None, **kwargs: Any
) -> discord.WebhookMessage:
    """Send a private followup with a message handle; propagate Discord failures."""
    kwargs.setdefault("ephemeral", True)
    kwargs["wait"] = True
    if content is None:
        return await interaction.followup.send(**kwargs)
    return await interaction.followup.send(
        emojis.render(content, interaction),
        **kwargs,
    )


async def send_interaction_message(
    interaction: discord.Interaction, content: str | None = None, **kwargs: Any
) -> discord.InteractionMessage | discord.WebhookMessage:
    """Send a private initial response or followup according to response state.

    Args:
        interaction: Interaction that may already have been acknowledged.
        content: Optional message text.
        **kwargs: Message options forwarded to the appropriate response helper.

    Returns:
        The sent response or followup.
    """
    if interaction.response.is_done():
        return await send_followup(interaction, content, **kwargs)
    return await send_interaction_response(interaction, content, **kwargs)


async def edit_interaction_response(
    interaction: discord.Interaction, **kwargs: Any
) -> None:
    """Update a component's dialog, rendering content and propagating failures."""
    if kwargs.get("content") is not None:
        kwargs["content"] = emojis.render(kwargs["content"], interaction)
    await interaction.response.edit_message(**kwargs)


async def edit_original_response(
    interaction: discord.Interaction, **kwargs: Any
) -> discord.InteractionMessage:
    """Update an acknowledged dialog, rendering content and propagating failures."""
    if kwargs.get("content") is not None:
        kwargs["content"] = emojis.render(kwargs["content"], interaction)
    return await interaction.edit_original_response(**kwargs)


async def send_temporary_followup(
    interaction: discord.Interaction,
    content: str,
    *,
    ephemeral: bool = True,
    file: discord.File | None = None,
    delay: float | None = 5,
) -> discord.Message | None:
    """Send a followup and optionally schedule its deletion after the given delay."""
    kwargs: dict[str, Any] = {"ephemeral": ephemeral, "wait": True}
    if file is not None:
        kwargs["file"] = file
    message = await send_followup(interaction, content, **kwargs)
    if message is None:
        logger.warning("Discord did not return a message for a temporary followup.")
    elif delay is not None:
        task = asyncio.create_task(_delete_after(message, delay))
        retain_delete_task(task)
    return message


async def send_temporary_response(
    interaction: discord.Interaction, content: str, *, delay: float = 5
) -> None:
    """Send an ephemeral interaction response and remove it after the given delay."""
    await interaction.response.send_message(
        emojis.render(content, interaction), ephemeral=True
    )
    message = await interaction.original_response()
    await delete_message(message, delay=delay)


def retain_delete_task(task: asyncio.Task[None]) -> None:
    """Keep a scheduled message-deletion task alive until it completes."""
    _delete_tasks.add(task)
    task.add_done_callback(_delete_tasks.discard)


async def _delete_after(message: discord.Message, delay: float) -> None:
    await asyncio.sleep(delay)
    await delete_temporary_message(message)
