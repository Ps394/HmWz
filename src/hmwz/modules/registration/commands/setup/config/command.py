"""Slash command for opening the registration setup panel."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.ui.messages import send_initial_response
from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.messages import send_temporary_followup
from hmwz.utils.interactions import log_interaction
from hmwz.modules.registration.module import RegistrationModule

from . import RegistrationConfigView
from .configuration_message import configuration_message
from .draft import RegistrationSetupDraft

logger = logging.getLogger(__name__)


@app_commands.command(
    name="setup",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.setup", "-"
        ),
        key="wz.registration.setup.description",
    ),
)
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
async def setup(interaction: discord.Interaction) -> None:
    """Open the guided setup panel for the current channel."""
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await send_initial_response(
            interaction,
            t(interaction, "registration.setup.config.error"),
            ephemeral=True,
            delete_after=5,
        )
        return

    try:
        module: RegistrationModule = await manager.get_module(guild, RegistrationModule)
        draft = await RegistrationSetupDraft.load(
            module, channel_id, interaction.user.id
        )

        await send_initial_response(
            interaction,
            embed=await configuration_message(module, interaction, channel_id, draft),
            view=RegistrationConfigView(draft),
            ephemeral=True,
        )
    except Exception:
        logger.exception("%s WZ setup config failed.", log_interaction(interaction))
        if not interaction.response.is_done():
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.error"),
                ephemeral=True,
                delete_after=5,
            )
        else:
            await send_temporary_followup(
                interaction,
                t(interaction, "registration.setup.config.error"),
                ephemeral=True,
            )
