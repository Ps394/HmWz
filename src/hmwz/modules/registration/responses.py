from __future__ import annotations

import discord

from hmwz.ui.messages import (
    delete_temporary_message,
    send_temporary_followup as send_followup,
)

CONFIRMATION_MESSAGE_LIFETIME_SECONDS = 5


async def send_temporary_followup(
    interaction: discord.Interaction,
    content: str,
    *,
    ephemeral: bool = True,
    file: discord.File | None = None,
) -> None:
    """Send a follow-up notification and delete it after five seconds."""
    message = await send_followup(
        interaction,
        content,
        ephemeral=ephemeral,
        file=file,
    )
    await delete_temporary_message(message, delay=CONFIRMATION_MESSAGE_LIFETIME_SECONDS)
