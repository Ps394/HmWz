"""Moderator command for starting a new Qs eruption cycle."""

from __future__ import annotations

import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import t
from hmwz.ui.messages import send_interaction_response

from ..module import QsModule
from ..setup import setup_view
from .common import get_module
from .maintenance import QsMaintenanceConfirmation


@app_commands.command(
    name="reset",
    description=app_commands.locale_str(
        "Clean Qs channels and configure a new eruption schedule",
        key="qs.admin.reset",
    ),
)
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, manage_threads=True)
async def reset(interaction: discord.Interaction) -> None:
    """Choose new timestamps and phase durations before confirming the reset."""
    module = await get_module(interaction)
    if module is None or interaction.channel_id is None:
        return
    configuration = await module.qs.get(module.guild.id, interaction.channel_id)
    if configuration is None or configuration.state == "removing":
        await send_interaction_response(
            interaction, t(interaction, "qs.event.not_configured")
        )
        return
    view = await setup_view(
        module, interaction.channel_id, interaction.user.id, reset_mode=True
    )
    view.message = await send_interaction_response(
        interaction,
        embed=view.embed(),
        view=view,
    )
