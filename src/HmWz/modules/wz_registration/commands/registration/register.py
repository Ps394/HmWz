import asyncio
import logging

import discord
from discord import Forbidden, HTTPException, Interaction, NotFound, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


async def roles_autocomplete(interaction: Interaction, current: str):
    if not interaction.guild:
        return []

    manager = getattr(interaction.client, "module_manager", None)
    if manager is None:
        return []

    try:
        module: WzRegistrationModule = await manager.get_module(
            interaction.guild, WzRegistrationModule
        )
        configured_roles = await module.roles.get(guild=interaction.guild)
        if not configured_roles:
            return []

        out: list[app_commands.Choice[str]] = []
        for configured in configured_roles:
            role = interaction.guild.get_role(configured.role)
            if role is None:
                continue
            if current.lower() in role.name.lower():
                out.append(app_commands.Choice(name=role.name, value=str(role.id)))
        return out[:25]
    except Exception:
        return []


@app_commands.checks.has_permissions(moderate_members=True, manage_messages=True)
@app_commands.command(
    name="register",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.register", "Sign up for a WZ event"
        ),
        key="wz.registration.register.description",
    ),
)
@app_commands.describe(
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.registration.register.role", "-"
        ),
        key="wz.registration.register.role.description",
    )
)
@app_commands.checks.cooldown(1, 300, key=lambda i: i.guild_id)
async def register(interaction: Interaction, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    try:
        if not interaction.guild:
            await interaction.followup.send(
                t(interaction, "wz.registration.register.error"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.register.error"), ephemeral=True
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
        if not non_permanent_roles:
            await interaction.followup.send(
                t(interaction, "wz.registration.csv.no_registrations"), ephemeral=True
            )
            return

        registrations = await module.registrations.get(
            guild=interaction.guild, roles=non_permanent_roles
        )
        if not registrations:
            await interaction.followup.send(
                t(interaction, "wz.registration.csv.no_registrations"), ephemeral=True
            )
            return

        for reg in registrations:
            if reg.member is None or reg.role is None:
                continue
            member = await utils.fetch_member(interaction.guild, reg.member)
            registered_role = interaction.guild.get_role(reg.role)
            if member is None or registered_role is None:
                continue
            try:
                await member.remove_roles(
                    registered_role, reason="WZ Registration Reset"
                )
                await asyncio.sleep(0.05)
            except (HTTPException, Forbidden, NotFound) as e:
                logger.warning(
                    f"Failed to remove role {reg.role} from member {reg.member}: {e}"
                )

        success = await module.registrations.remove(
            guild=interaction.guild, roles=non_permanent_roles
        )
        if not success:
            await interaction.followup.send(
                t(interaction, "wz.registration.reset.error"), ephemeral=True
            )
            return

        if registration_config.channel is not None:
            channel = await utils.fetch_channel(
                interaction.guild, registration_config.channel
            )
            if channel is not None:
                await channel.purge(
                    limit=500,
                    check=lambda m: not m.pinned and not m.author.bot,
                    reason="WZ Registration Reset",
                )

        await module.compose_registration_overview(force=True)
        timestamp = discord.utils.format_dt(discord.utils.utcnow(), style="F")
        await interaction.followup.send(
            t(interaction, "wz.registration.reset.success", timestamp=timestamp),
            ephemeral=True,
        )
    except Exception as e:
        logger.exception(f"WZ registration reset failed: {e}")
        await interaction.followup.send(
            t(interaction, "wz.registration.reset.error"), ephemeral=True
        )
