import logging
from typing import Optional
from discord import app_commands, Interaction, Role, HTTPException, Forbidden, NotFound
from discord.app_commands import checks
from ......emojis import Emojis
from ......services import Services
from .....overviews import Manager

from ......i18n import CommandLocalizations, t
from ...... import configuration

logger = logging.getLogger(__name__)

@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.command(name="role-add",     description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.roles.add.description", "-"),
        key="wz.setup.roles.add.description",
    ),
)
@app_commands.describe(
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.roles.add.role.description", "-"),
        key="wz.setup.roles.add.role.description",
    ),
    permanent=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.roles.add.permanent.description", "-"),
        key="wz.setup.roles.add.permanent.description",
    ),
)
async def add(interaction: Interaction, role: Role, permanent: Optional[bool] = False):
    MAX_ROLES = configuration.WzRegistration.MAX_REGISTRATION_ROLES.value
    LOG_CONTEXT = f"{interaction.guild.name}({interaction.guild.id}) - {interaction.user} - WZ Setup Role Add : "
    LOGS = {
        "EXCEPTION": f"{LOG_CONTEXT}",
        "NO_SERVICES_OR_OVERVIEW": f"{LOG_CONTEXT} Required services or overview manager not found on client.",
        "ROLE_HIERARCHY": f"{LOG_CONTEXT} Rolle {role.name} ist höher als Bot-Rolle.",
        "MAX_ROLES": f"{LOG_CONTEXT} versuchte, mehr als {MAX_ROLES} Rollen zur WZ-Registrierung hinzuzufügen.",
        "ROLE_ADDED": f"{LOG_CONTEXT} hat die Rolle {role.name} zur WZ-Registrierung hinzugefügt.",
        "ROLE_ADD_FAILED": f"{LOG_CONTEXT} konnte die Rolle {role.name} nicht zur WZ-Registrierung hinzufügen."
    }
    await interaction.response.defer(ephemeral=True)
    try:
        services: Services = getattr(interaction.client, "services")
        overview_manager: Manager = getattr(interaction.client, "overview_manager", None)
        if not services or not overview_manager:
            raise TypeError(LOGS["NO_SERVICES_OR_OVERVIEW"])
        
        if role >= interaction.guild.me.top_role:
            await interaction.followup.send(t(interaction, "wz.setup.roles.add.error.role_hierarchy"), ephemeral=True)
            logger.error(LOGS["ROLE_HIERARCHY"])
            return

        if await services.wz.roles.count(guild=interaction.guild) >= MAX_ROLES:
            await interaction.followup.send(t(interaction, "wz.setup.roles.add.max_roles", max_roles=MAX_ROLES), ephemeral=True)
            logger.warning(LOGS["MAX_ROLES"])
            return
 
        if await services.wz.roles.add(guild=interaction.guild, role=role.id, permanent=permanent):
            await overview_manager.sync(guild=interaction.guild, sync_config=True, sync_discord=True)
            await overview_manager.ensure(guild=interaction.guild)
            await interaction.followup.send(t(interaction, "wz.setup.roles.add.success", role_name=role.name), ephemeral=True)
            logger.debug(LOGS["ROLE_ADDED"])
        else:
            await interaction.followup.send(t(interaction, "wz.setup.roles.add.error"), ephemeral=True)
            logger.error(LOGS["ROLE_ADD_FAILED"])
    except (ValueError, Exception, HTTPException, Forbidden, NotFound) as e:
        await interaction.followup.send(t(interaction, "wz.setup.roles.add.error"), ephemeral=True)
        logger.exception(f"{LOGS['EXCEPTION']} {e}")
