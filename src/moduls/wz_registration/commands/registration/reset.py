import asyncio
import logging

from discord import Forbidden, HTTPException, Interaction, NotFound, app_commands

import hmUtils
from i18n import CommandLocalizations, t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


@app_commands.checks.has_permissions(moderate_members=True, manage_messages=True)
@app_commands.command(
    name="reset",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.registration.reset.description", "-"),
        key="wz.registration.reset.description",
    ),
)
@app_commands.describe(
    ephemeral=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("ephemeral.description", "-"),
        key="ephemeral.description",
    )
)
@app_commands.checks.cooldown(1, 300, key=lambda i: (i.guild_id))
async def reset(interaction: Interaction, ephemeral: bool = True):
    await interaction.response.defer(ephemeral=ephemeral)
    try:
        if not interaction.guild:
            await interaction.followup.send(t(interaction, "wz.registration.reset.error"), ephemeral=True)
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(t(interaction, "wz.registration.reset.error"), ephemeral=True)
            return

        module: WzRegistrationModule = await manager.get_module(interaction.guild, WzRegistrationModule)
        registration_config = await module.registration.get(guild=interaction.guild)
        configured_roles = await module.roles.get(guild=interaction.guild)

        if not registration_config or not registration_config.channel or not configured_roles:
            await interaction.followup.send(t(interaction, "wz.registration.error.not_configured"), ephemeral=True)
            return

        non_permanent_roles = [r.role for r in configured_roles if not r.permanent]
        if not non_permanent_roles:
            await interaction.followup.send(t(interaction, "wz.registration.csv.no_registrations"), ephemeral=True)
            return

        registrations = await module.registrations.get(guild=interaction.guild, roles=non_permanent_roles)
        if not registrations:
            await interaction.followup.send(t(interaction, "wz.registration.csv.no_registrations"), ephemeral=True)
            return

        for reg in registrations:
            if reg.member is None or reg.role is None:
                continue
            member = await hmUtils.fetch_member(interaction.guild, reg.member)
            role = await hmUtils.fetch_role(interaction.guild, reg.role)
            if member is None or role is None:
                continue
            try:
                await member.remove_roles(role, reason="WZ Registration Reset")
                await asyncio.sleep(0.05)
            except (HTTPException, Forbidden, NotFound) as e:
                logger.warning(f"Failed to remove role {reg.role} from member {reg.member}: {e}")

        success = await module.registrations.remove(guild=interaction.guild, roles=non_permanent_roles)
        if not success:
            await interaction.followup.send(t(interaction, "wz.registration.reset.error"), ephemeral=True)
            return

        await module.compose_registration_overview(force=True)
        await interaction.followup.send(t(interaction, "wz.registration.reset.success"), ephemeral=ephemeral)
    except Exception as e:
        logger.exception(f"WZ registration reset failed: {e}")
        await interaction.followup.send(t(interaction, "wz.registration.reset.error"), ephemeral=True)
