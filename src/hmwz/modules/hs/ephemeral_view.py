from __future__ import annotations

import asyncio
import logging

import discord

from hmwz.ui.messages import delete_message

logger = logging.getLogger(__name__)
_delete_tasks: set[asyncio.Task[None]] = set()


def _retain_task(task: asyncio.Task[None]) -> None:
    _delete_tasks.add(task)
    task.add_done_callback(_delete_tasks.discard)


async def _delete_after(message: discord.Message, delay: float) -> None:
    await asyncio.sleep(delay)
    await delete_temporary_message(message)


async def delete_temporary_message(message: discord.Message | None) -> None:
    """Delete a temporary interaction message when it still exists."""
    if message is None:
        return
    await delete_message(message)


async def send_temporary_followup(
    interaction: discord.Interaction, content: str, *, delay: float = 10
) -> None:
    """Send an ephemeral followup and delete it after a short delay."""
    message = await interaction.followup.send(content, ephemeral=True, wait=True)
    if message is None:
        logger.warning("Discord did not return a message for a temporary followup.")
        return
    task = asyncio.create_task(_delete_after(message, delay))
    _retain_task(task)


class EphemeralView(discord.ui.View):
    """View base that removes temporary interaction messages after timeout."""

    def __init__(self, *, timeout: float = 180) -> None:
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        """Delete the associated message when the view expires."""
        await delete_temporary_message(self.message)

    async def finish(
        self, interaction: discord.Interaction, content: str, *, delay: float = 10
    ) -> None:
        """Replace a completed dialog with a short-lived private result."""
        self.stop()
        response_state = getattr(interaction.response, "is_done", None)
        response_pending = response_state is not None and not response_state()
        if response_pending:
            await interaction.response.defer(ephemeral=True, thinking=True)
        message = getattr(interaction, "message", None) or self.message
        if message is not None:
            await delete_temporary_message(message)
        if message is None or response_pending:
            await interaction.delete_original_response()
        await send_temporary_followup(interaction, content, delay=delay)

    async def send_temporary_response(
        self, interaction: discord.Interaction, content: str, *, delay: float = 10
    ) -> None:
        """Send a private response and remove it after a short delay."""
        await interaction.response.send_message(content, ephemeral=True)
        task = asyncio.create_task(self._delete_original_after(interaction, delay))
        _retain_task(task)

    @staticmethod
    async def _delete_original_after(
        interaction: discord.Interaction, delay: float
    ) -> None:
        await asyncio.sleep(delay)
        try:
            await interaction.delete_original_response()
        except discord.NotFound:
            pass
        except discord.HTTPException:
            logger.exception("Failed to delete a temporary interaction response.")
