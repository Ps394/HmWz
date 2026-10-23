import logging

import discord
from discord import Interaction, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.registration.base import RegistrationModuleBase

logger = logging.getLogger(__name__)


@app_commands.command(
    name="event-log",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup.event_log",
            "Configure the channel for registration event snapshots",
        ),
        key="wz.setup.event_log.description",
    ),
)
@app_commands.describe(
    channel=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.event_log.channel",
            "Channel for registration JSON files; omit to disable",
        ),
        key="wz.setup.event_log.channel.description",
    ),
)
async def event_log(
    interaction: Interaction, channel: discord.TextChannel | None = None
) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.event_log.error"), ephemeral=True
            )
            return

        module: RegistrationModuleBase = await manager.get_module(
            guild, RegistrationModuleBase
        )
        if channel is None:
            if not await module.registration_event_channel.remove(guild=guild):
                await interaction.followup.send(
                    t(interaction, "wz.setup.event_log.error"), ephemeral=True
                )
                return
            await interaction.followup.send(
                t(interaction, "wz.setup.event_log.disabled"), ephemeral=True
            )
            return

        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.event_log.error"), ephemeral=True
            )
            return
        permissions = channel.permissions_for(bot_member)
        if not permissions.send_messages or not permissions.attach_files:
            await interaction.followup.send(
                t(interaction, "wz.setup.event_log.missing_permissions"),
                ephemeral=True,
            )
            return

        if not await module.registration_event_channel.set(
            guild=guild, channel_id=channel.id
        ):
            await interaction.followup.send(
                t(interaction, "wz.setup.event_log.error"), ephemeral=True
            )
            return

        await interaction.followup.send(
            t(
                interaction,
                "wz.setup.event_log.success",
                channel_name=channel.mention,
            ),
            ephemeral=True,
        )
    except Exception as error:
        logger.exception(
            "%s WZ registration event channel setup failed: %s",
            utils.log_interaction(interaction),
            error,
        )
        await interaction.followup.send(
            t(interaction, "wz.setup.event_log.error"), ephemeral=True
        )
