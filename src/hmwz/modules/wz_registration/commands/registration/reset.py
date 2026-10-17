import asyncio
import logging

import discord
from discord import HTTPException, Interaction, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


@app_commands.checks.has_permissions(moderate_members=True, manage_messages=True)
@app_commands.checks.has_permissions(
    manage_roles=True, manage_messages=True, manage_channels=True
)
@app_commands.command(
    name="reset",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.reset", "-"
        ),
        key="wz.registration.reset.description",
    ),
)
@app_commands.describe(
    ephemeral=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("parameter.description.ephemeral", "-"),
        key="wz.registration.reset.ephemeral.description",
    ),
    purge=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.registration.reset.purge", "-"
        ),
        key="wz.registration.reset.purge.description",
    ),
)
@app_commands.checks.cooldown(1, 300, key=lambda i: i.guild_id)
async def reset(
    interaction: Interaction, ephemeral: bool = False, purge: bool = False
) -> None:
    await interaction.response.defer(ephemeral=ephemeral)
    try:
        if not interaction.guild:
            await interaction.followup.send(
                t(interaction, "wz.registration.reset.error"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.reset.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            interaction.guild, WzRegistrationModule
        )
        registration_config = await module.registration.get(guild=interaction.guild)
        configured_roles = await module.roles.get(guild=interaction.guild)

        if (
            not registration_config
            or not registration_config.channel
            or not configured_roles
        ):
            await interaction.followup.send(
                t(interaction, "wz.registration.error.not_configured"), ephemeral=True
            )
            return

        non_permanent_roles = [r.role for r in configured_roles if not r.permanent]

        registrations = await module.registrations.get(guild=interaction.guild)
        if not registrations:
            await interaction.followup.send(
                t(interaction, "wz.registration.csv.no_registrations"), ephemeral=True
            )
            return

        non_permanent_registrations = [
            reg for reg in registrations if reg.role in non_permanent_roles
        ]
        if len(non_permanent_registrations) > 0:
            roles_to_remove = {
                (reg.member, reg.role)
                for reg in non_permanent_registrations
                if reg.member is not None and reg.role is not None
            }
            for member_id, role_id in roles_to_remove:
                member = await utils.fetch_member(interaction.guild, member_id)
                role = interaction.guild.get_role(role_id)
                if member is None or role is None:
                    continue
                try:
                    await member.remove_roles(role, reason="WZ Registration Reset")
                    await asyncio.sleep(0.05)
                except HTTPException as e:
                    logger.warning(
                        "Failed to remove role %s (%s) from member %s / %s (%s) "
                        "in guild %s (%s): %s",
                        role.name,
                        role.id,
                        member.name,
                        member.display_name,
                        member.id,
                        interaction.guild.name,
                        interaction.guild.id,
                        e,
                    )

            success = await module.registrations.remove(
                guild=interaction.guild, roles=non_permanent_roles
            )
            if not success:
                await interaction.followup.send(
                    t(interaction, "wz.registration.reset.error"), ephemeral=True
                )
                return

        if purge:
            channels_to_purge = await module.purge_channels.get(guild=interaction.guild)
            channel_ids = {
                configured.channel_id for configured in channels_to_purge or ()
            }
            if registration_config.channel is not None:
                channel_ids.add(registration_config.channel)

            for channel_id in sorted(channel_ids):
                channel = await utils.fetch_channel(interaction.guild, channel_id)
                if channel is None:
                    continue
                try:
                    await channel.purge(
                        limit=500,
                        check=lambda m: not m.pinned and not m.author.bot,
                        reason="WZ Registration Reset",
                    )
                except HTTPException as e:
                    logger.warning(
                        "Failed to purge WZ channel %s (%s) in guild %s (%s): %s",
                        channel.name,
                        channel.id,
                        interaction.guild.name,
                        interaction.guild.id,
                        e,
                    )

        await module.compose_registration_overview(force=True)
        timestamp = discord.utils.format_dt(discord.utils.utcnow(), style="F")
        await interaction.followup.send(
            t(interaction, "wz.registration.reset.success", timestamp=timestamp),
            ephemeral=ephemeral,
        )
    except Exception as e:
        logger.exception(
            "%s WZ registration reset failed: %s",
            utils.log_interaction(interaction),
            e,
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.reset.error"), ephemeral=True
        )
