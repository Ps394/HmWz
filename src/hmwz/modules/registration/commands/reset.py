"""Reset registration data for the current channel."""

import asyncio
import logging

import discord
from discord import HTTPException, Interaction, app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.messages import send_temporary_followup
from hmwz.utils.loaders import fetch_channel, fetch_member
from hmwz.utils.interactions import log_interaction

from hmwz.modules.registration.module import RegistrationModule

logger = logging.getLogger(__name__)


async def _remove_registration_roles(
    guild: discord.Guild, roles_to_remove: set[tuple[int, int]]
) -> None:
    for member_id, role_id in roles_to_remove:
        member = await fetch_member(guild, member_id)
        role = guild.get_role(role_id)
        if member is None or role is None:
            continue
        try:
            await member.remove_roles(role, reason="WZ Registration Reset")
            await asyncio.sleep(0.05)
        except HTTPException as error:
            logger.warning(
                "Failed to remove role %s (%s) from member %s / %s (%s) "
                "in guild %s (%s): %s",
                role.name,
                role.id,
                member.name,
                member.display_name,
                member.id,
                guild.name,
                guild.id,
                error,
            )


async def _purge_configured_channels(
    guild: discord.Guild,
    channel_ids: set[int],
) -> None:
    for channel_id in sorted(channel_ids):
        channel = await fetch_channel(guild, channel_id)
        if channel is None:
            continue
        try:
            await channel.purge(
                limit=500,
                check=lambda message: not message.pinned and not message.author.bot,
                reason="WZ Registration Reset",
            )
        except HTTPException as error:
            logger.warning(
                "Failed to purge WZ channel %s (%s) in guild %s (%s): %s",
                channel.name,
                channel.id,
                guild.name,
                guild.id,
                error,
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
@app_commands.checks.has_permissions(manage_messages=True, manage_roles=True)
@app_commands.default_permissions(manage_messages=True, manage_roles=True)
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
    """Reset registrations configured for the current channel.

    Args:
        interaction: The interaction that invoked the command.
        ephemeral: Whether to show the result only to the invoking user.
        purge: Whether to also remove registration messages.
    """
    await interaction.response.defer(ephemeral=ephemeral)
    try:
        guild = interaction.guild
        if guild is None:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.reset.error"),
                ephemeral=True,
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.reset.error"),
                ephemeral=True,
            )
            return

        module: RegistrationModule = await manager.get_module(guild, RegistrationModule)
        channel_id = interaction.channel_id
        if channel_id is None:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.reset.error"),
                ephemeral=True,
            )
            return
        registration_config = await module.registration.get(
            guild=guild, channel_id=channel_id
        )
        configured_roles = await module.roles.get(guild=guild, channel_id=channel_id)

        if (
            not registration_config
            or not registration_config.channel
            or not configured_roles
        ):
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.error.not_configured"),
                ephemeral=True,
            )
            return

        non_permanent_roles = [r.role for r in configured_roles if not r.permanent]

        registrations = await module.registrations.get(
            guild=guild, channel_id=channel_id
        )
        if not registrations:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.csv.no_registrations"),
                ephemeral=True,
            )
            return

        non_permanent_registrations = [
            reg for reg in registrations if reg.role in non_permanent_roles
        ]
        if len(non_permanent_registrations) > 0:
            all_member_registrations = await module.registrations.get(guild=guild)
            roles_to_remove = {
                (reg.member, reg.role)
                for reg in non_permanent_registrations
                if reg.member is not None
                and reg.role is not None
                and not any(
                    other.member == reg.member
                    and other.role == reg.role
                    and other.channel_id != channel_id
                    for other in all_member_registrations or ()
                )
            }
            await _remove_registration_roles(guild, roles_to_remove)

            success = await module.registrations.remove(
                guild=guild,
                roles=non_permanent_roles,
                channel_id=channel_id,
            )
            if not success:
                await send_temporary_followup(
                    interaction,
                    t(interaction, "wz.registration.reset.error"),
                    ephemeral=True,
                )
                return
            await module.export_registration_snapshot(channel_id, "sync")

        if purge:
            await _purge_configured_channels(guild, {channel_id})

        await module.compose_registration_overview(force=True, channel_id=channel_id)
        timestamp = discord.utils.format_dt(discord.utils.utcnow(), style="F")
        await send_temporary_followup(
            interaction,
            t(interaction, "wz.registration.reset.success", timestamp=timestamp),
            ephemeral=ephemeral,
        )
    except Exception as e:
        logger.exception(
            "%s WZ registration reset failed: %s",
            log_interaction(interaction),
            e,
        )
        await send_temporary_followup(
            interaction, t(interaction, "wz.registration.reset.error"), ephemeral=True
        )
