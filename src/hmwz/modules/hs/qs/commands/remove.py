"""Moderator command for removing the Qs tool from a channel."""

from __future__ import annotations

import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import t
from hmwz.ui.messages import send_interaction_response

from ..module import QsModule
from .common import get_module
from .maintenance import QsMaintenanceConfirmation


@app_commands.command(
    name="remove",
    description=app_commands.locale_str(
        "Remove the Qs tool, its threads and data", key="qs.admin.remove"
    ),
)
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, manage_threads=True)
async def remove(interaction: discord.Interaction) -> None:
    """Show a removal preview before deleting any Qs resources."""
    module = await get_module(interaction)
    if module is None or interaction.channel_id is None:
        return
    if await module.qs.get(module.guild.id, interaction.channel_id) is None:
        await send_interaction_response(
            interaction, t(interaction, "qs.event.not_configured")
        )
        return
    view = QsMaintenanceConfirmation(
        module, interaction.channel_id, interaction.user.id, action="remove"
    )
    view.message = await send_interaction_response(
        interaction,
        t(interaction, "qs.admin.remove_warning"),
        view=view,
    )
