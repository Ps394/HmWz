"""Components for short-lived private interaction views and responses."""

from __future__ import annotations

import asyncio
import logging

import discord

from hmwz.ui.messages import (
    defer_interaction,
    dismiss_dialog,
    delete_temporary_message,
    retain_delete_task,
    send_initial_response,
    send_temporary_followup,
)

logger = logging.getLogger(__name__)


class EphemeralView(discord.ui.View):
    """View base that removes temporary interaction messages after timeout."""

    def __init__(self, *, timeout: float = 180) -> None:
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        """Delete the associated message when the view expires."""
        await delete_temporary_message(self.message)

    async def dismiss(self, interaction: discord.Interaction) -> None:
        """Delete a cancelled component dialog before stopping its view.

        Args:
            interaction: Unacknowledged component click on this dialog.
        """
        await dismiss_dialog(interaction)
        self.stop()

    async def finish(
        self, interaction: discord.Interaction, content: str, *, delay: float = 10
    ) -> None:
        """Replace a completed dialog with a short-lived private result."""
        self.stop()
        response_state = getattr(interaction.response, "is_done", None)
        response_pending = response_state is not None and not response_state()
        if response_pending:
            await defer_interaction(interaction, thinking=True)
        message = self.message or getattr(interaction, "message", None)
        if message is not None:
            await delete_temporary_message(message)
        if message is None or response_pending:
            await interaction.delete_original_response()
        await send_temporary_followup(interaction, content, delay=delay)

    async def send_temporary_response(
        self, interaction: discord.Interaction, content: str, *, delay: float = 10
    ) -> None:
        """Send a private response and remove it after a short delay."""
        await send_initial_response(interaction, content)
        task = asyncio.create_task(self._delete_original_after(interaction, delay))
        retain_delete_task(task)

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
