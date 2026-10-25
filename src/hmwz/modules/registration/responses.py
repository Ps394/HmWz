from __future__ import annotations

import discord

CONFIRMATION_MESSAGE_LIFETIME_SECONDS = 5


async def send_temporary_followup(
    interaction: discord.Interaction,
    content: str,
    *,
    ephemeral: bool = True,
    file: discord.File | None = None,
) -> None:
    """Send a follow-up notification and delete it after five seconds."""
    if file is None:
        message = await interaction.followup.send(
            content,
            ephemeral=ephemeral,
            wait=True,
        )
    else:
        message = await interaction.followup.send(
            content,
            file=file,
            ephemeral=ephemeral,
            wait=True,
        )
    await message.delete(delay=CONFIRMATION_MESSAGE_LIFETIME_SECONDS)
