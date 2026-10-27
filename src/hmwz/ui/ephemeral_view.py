from __future__ import annotations

import discord

from hmwz.interactions import (
    defer_interaction,
    delete_temporary_message,
    respond,
    safe_delete_original_response,
    schedule_temporary_delete,
    send_temporary_followup as _send_temporary_followup,
)


async def send_temporary_followup(
    interaction: discord.Interaction, content: str, *, delay: float = 10
) -> None:
    """Schedule cleanup of a private follow-up without blocking the callback."""
    await _send_temporary_followup(interaction, content, delay=delay, schedule=True)


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
            await defer_interaction(interaction, ephemeral=True, thinking=True)

        message = getattr(interaction, "message", None) or self.message
        if message is not None:
            await delete_temporary_message(message)
        if message is None or response_pending:
            await safe_delete_original_response(interaction)
        await send_temporary_followup(interaction, content, delay=delay)

    async def send_temporary_response(
        self, interaction: discord.Interaction, content: str, *, delay: float = 10
    ) -> None:
        """Send a private response and remove it after a short delay."""
        message = await respond(interaction, content, ephemeral=True)
        if message is not None:
            schedule_temporary_delete(message, delay)


__all__ = [
    "EphemeralView",
    "delete_temporary_message",
    "send_temporary_followup",
]
