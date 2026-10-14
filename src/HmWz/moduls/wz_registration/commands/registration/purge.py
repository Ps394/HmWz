import logging

import discord
import hmUtils
from discord import HTTPException, Interaction, app_commands
from i18n import CommandLocalizations, t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


@app_commands.command(
    name="purge",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.purge", "-"
        ),
        key="wz.registration.purge.description",
    ),
)
@app_commands.checks.bot_has_permissions(moderate_members=True, manage_messages=True)
@app_commands.describe(
    ephemeral=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("parameter.description.ephemeral", "-"),
        key="ephemeral.description",
    )
)
@app_commands.checks.cooldown(1, 30, key=lambda interaction: interaction.guild_id)
async def purge(interaction: Interaction, ephemeral: bool = True) -> None:
    await interaction.response.defer(ephemeral=ephemeral)
    try:
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.purge.error"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.purge.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        configured_channels = await module.purge_channels.get(guild=guild)
        if not configured_channels:
            await interaction.followup.send(
                t(interaction, "wz.registration.purge.no_channels"),
                ephemeral=ephemeral,
            )
            return

        deleted_count = 0
        failed_channels: list[int] = []
        for configured in configured_channels:
            channel = await hmUtils.fetch_channel(guild, configured.channel_id)
            if channel is None:
                failed_channels.append(configured.channel_id)
                continue
            try:
                deleted = await channel.purge(
                    limit=500,
                    check=lambda message: not message.pinned
                    and not message.author.bot,
                    reason="WZ Registration Purge",
                )
                deleted_count += len(deleted)
            except HTTPException:
                logger.exception(
                    "Failed to purge WZ channel %s in guild %s.",
                    configured.channel_id,
                    guild.id,
                )
                failed_channels.append(configured.channel_id)

        await interaction.followup.send(
            t(
                interaction,
                "wz.registration.purge.success",
                deleted_count=deleted_count,
                failed_count=len(failed_channels),
            ),
            ephemeral=ephemeral,
        )
        if failed_channels:
            logger.warning(
                "WZ purge completed with inaccessible/failed channels in guild %s: %s",
                guild.id,
                ", ".join(map(str, failed_channels)),
            )
    except Exception:
        logger.exception("WZ configured-channel purge failed.")
        await interaction.followup.send(
            t(interaction, "wz.registration.purge.error"), ephemeral=True
        )
