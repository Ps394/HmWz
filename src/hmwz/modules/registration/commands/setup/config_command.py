from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.interactions import log_interaction
from hmwz.modules.hs.wz.module import WzRegistrationModule

from ...responses import send_temporary_followup
from .config import RegistrationConfigView
from .configuration_message import configuration_message

logger = logging.getLogger(__name__)


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.checks.has_permissions(
    manage_roles=True, manage_messages=True, manage_channels=True
)
@app_commands.default_permissions(
    manage_roles=True, manage_messages=True, manage_channels=True
)
@app_commands.command(
    name="setup",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.setup", "-"
        ),
        key="wz.registration.setup.description",
    ),
)
async def setup(interaction: discord.Interaction) -> None:
    """Open the guided setup panel for the current channel."""
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.response.send_message(
            t(interaction, "wz.setup.config.error"),
            ephemeral=True,
            delete_after=5,
        )
        return

    try:
        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        settings = await module.registration.get(guild=guild, channel_id=channel_id)
        if settings is None:
            if not await module.registration.create(guild=guild, channel_id=channel_id):
                settings = await module.registration.get(
                    guild=guild, channel_id=channel_id
                )
                if settings is None:
                    await interaction.response.send_message(
                        t(interaction, "wz.setup.config.error"),
                        ephemeral=True,
                        delete_after=5,
                    )
                    return
            elif not await module.purge_channels.remove(
                guild=guild, channel_id=channel_id
            ):
                await module.registration.remove(guild=guild, channel_id=channel_id)
                await interaction.response.send_message(
                    t(interaction, "wz.setup.config.error"),
                    ephemeral=True,
                    delete_after=5,
                )
                return

        await interaction.response.send_message(
            await configuration_message(module, interaction, channel_id),
            view=RegistrationConfigView(module, channel_id, interaction.user.id),
            ephemeral=True,
        )
    except Exception:
        logger.exception("%s WZ setup config failed.", log_interaction(interaction))
        if not interaction.response.is_done():
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.error"),
                ephemeral=True,
                delete_after=5,
            )
        else:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.setup.config.error"),
                ephemeral=True,
            )
