"""Moderator command for configuring a Qs eruption."""

from __future__ import annotations

import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import t
from hmwz.ui.messages import send_interaction_response

from ..setup import setup_view
from .common import get_module


@app_commands.command(
    name="setup",
    description=app_commands.locale_str(
        "Configure a Qs eruption and its five phases", key="qs.event.setup"
    ),
)
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
async def setup(interaction: discord.Interaction) -> None:
    """Open a private setup draft with explicit role and phase-time selection."""
    module = await get_module(interaction)
    if module is None or interaction.channel_id is None:
        return
    if not await module.sync():
        await send_interaction_response(
            interaction, t(interaction, "qs.event.setup_failed")
        )
        return
    view = await setup_view(module, interaction.channel_id, interaction.user.id)
    view.message = await send_interaction_response(
        interaction, embed=view.embed(), view=view
    )
