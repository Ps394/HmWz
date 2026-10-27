from __future__ import annotations

import discord

from hmwz.ui.messages import send_temporary_response as send_response

_TEMPORARY_RESPONSE_DELAY_SECONDS = 5


async def send_temporary_response(
    interaction: discord.Interaction, message: str
) -> None:
    """Send a private donation response using the module's five-second lifetime."""
    await send_response(
        interaction,
        message,
        delay=_TEMPORARY_RESPONSE_DELAY_SECONDS,
    )
