"""Shared command context resolution for Qs slash commands."""

from __future__ import annotations

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_interaction_response

from ..module import QsModule


async def get_module(interaction: discord.Interaction) -> QsModule | None:
    """Resolve the independent module in a guild text channel."""
    manager = getattr(interaction.client, "module_manager", None)
    if (
        interaction.guild is None
        or manager is None
        or not isinstance(interaction.channel, discord.TextChannel)
    ):
        await send_interaction_response(
            interaction, t(interaction, "qs.event.not_configured")
        )
        return None
    return await manager.get_module(interaction.guild, QsModule)
