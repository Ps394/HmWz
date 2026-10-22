import logging

import discord
from discord import app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.hs.wz.module import WzRegistrationModule

logger = logging.getLogger(__name__)


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.command(
    name="clean-channels",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.clean_channels", "-"
        ),
        key="wz.clean_channels.description",
    ),
)
@app_commands.describe(
    ignore_pinned=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.clean_channels.ignore_pinned", "-"
        ),
        key="wz.clean_channels.ignore_pinned.description",
    )
)
@app_commands.checks.bot_has_permissions(manage_messages=True)
async def clean_channels(
    interaction: discord.Interaction, ignore_pinned: bool = True
) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await interaction.followup.send(
                t(interaction, "wz.clean_channels.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        configured_channels = await module.purge_channels.get(guild=guild)
        if not configured_channels:
            await interaction.followup.send(
                t(interaction, "wz.clean_channels.no_channels"), ephemeral=True
            )
            return

        deleted_count = 0
        failed_channels: list[str] = []
        for record in configured_channels:
            channel = await utils.fetch_channel(guild, record.channel_id)
            if channel is None:
                logger.warning(
                    "Configured WZ clean channel %s is missing or is not a text channel in guild %s.",
                    record.channel_id,
                    guild.id,
                )
                failed_channels.append(f"<#{record.channel_id}>")
                continue
            try:
                deleted = await channel.purge(
                    limit=500,
                    check=lambda message: not ignore_pinned or not message.pinned,
                    reason=f"WZ clean-channels by {interaction.user}",
                )
                deleted_count += len(deleted)
            except discord.HTTPException:
                failed_channels.append(channel.mention)
                logger.exception(
                    "Failed to clean WZ channel %s (%s) in guild %s.",
                    channel.name,
                    channel.id,
                    guild.id,
                )

        await interaction.followup.send(
            t(
                interaction,
                "wz.clean_channels.partial_failure"
                if failed_channels
                else "wz.clean_channels.success",
                deleted_count=deleted_count,
                channel_names=", ".join(failed_channels),
            ),
            ephemeral=True,
        )
    except Exception as error:
        logger.exception(
            "%s WZ clean-channels failed: %s",
            utils.log_interaction(interaction),
            error,
        )
        await interaction.followup.send(
            t(interaction, "wz.clean_channels.error"), ephemeral=True
        )
