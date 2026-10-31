"""Explicit export of the current channel's registrations."""

import logging

from discord import Interaction, app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.messages import send_temporary_followup
from hmwz.utils.interactions import log_interaction

from hmwz.modules.registration.module import RegistrationModule

logger = logging.getLogger(__name__)


@app_commands.command(
    name="snapshot",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.snapshot",
            "Export a JSON snapshot of this channel's registrations",
        ),
        key="wz.registration.snapshot.description",
    ),
)
@app_commands.checks.has_permissions(manage_messages=True, manage_roles=True)
@app_commands.default_permissions(manage_messages=True, manage_roles=True)
@app_commands.checks.cooldown(1, 60, key=lambda i: i.guild_id)
async def snapshot(interaction: Interaction) -> None:
    """Export the current registrations without changing any of them.

    Args:
        interaction: The interaction that invoked the command.
    """
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        channel_id = interaction.channel_id
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or channel_id is None or manager is None:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.snapshot.error"),
                ephemeral=True,
            )
            return

        module: RegistrationModule = await manager.get_module(guild, RegistrationModule)
        configuration = await module.registration.get(
            guild=guild, channel_id=channel_id
        )
        if configuration is None or configuration.channel is None:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.error.not_configured"),
                ephemeral=True,
            )
            return

        destination = await module.registration_event_channel.get(guild=guild)
        if destination is None:
            result_key = "wz.registration.snapshot.destination"
        elif await module.export_registration_snapshot(channel_id, "registration"):
            result_key = "wz.registration.snapshot.success"
        else:
            result_key = "wz.registration.snapshot.error"
        await send_temporary_followup(
            interaction, t(interaction, result_key), ephemeral=True
        )
    except Exception as e:
        logger.exception(
            "%s WZ registration snapshot failed: %s",
            log_interaction(interaction),
            e,
        )
        await send_temporary_followup(
            interaction,
            t(interaction, "wz.registration.snapshot.error"),
            ephemeral=True,
        )
