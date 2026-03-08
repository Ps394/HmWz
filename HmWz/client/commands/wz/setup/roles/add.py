import logging
from typing import Optional
from discord import app_commands, Interaction, Role, HTTPException, Forbidden, NotFound
from discord.app_commands import checks
from ......emojis import Emojis
from ......services import Services
from .....overviews import Manager

logger = logging.getLogger(__name__)

MAX_ROLES = 4

@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.default_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.command(name="role-add", description="Anmeldungsrolle hinzufügen (maximal 4 Rollen möglich)")
@app_commands.describe(role="Registrierungsrolle", permanent="Permanent machen (optional, Standard: false)")
async def add(interaction: Interaction, role: Role, permanent: Optional[bool] = False):
    MAX_ROLES = 4
    MESSAGES = {
        "ERROR": f"{Emojis.ERROR.value} Fehler beim Hinzufügen der Rolle zur WZ-Registrierung.",
        "MAX_ROLES": f"{Emojis.WARNING.value} Es können maximal {MAX_ROLES} Rollen für die WZ-Registrierung festgelegt werden.",
        "SUCCESS": f"{Emojis.SUCCESS.value} Rolle {{role_name}} wurde zur WZ-Registrierung hinzugefügt."
    }
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
            await interaction.followup.send(f"{Emojis.ERROR} Die angegebene Rolle ist höher als die Bot-Rolle.", ephemeral=True)
            logger.error(LOGS["ROLE_HIERARCHY"])
            return

        if await services.wz.roles.count(guild=interaction.guild) >= MAX_ROLES:
            await interaction.followup.send(MESSAGES["MAX_ROLES"], ephemeral=True)
            logger.warning(LOGS["MAX_ROLES"])
            return
 
        if await services.wz.roles.add(guild=interaction.guild, role=role.id, permanent=permanent):
            await overview_manager.sync(guild=interaction.guild, sync_config=True)
            await overview_manager.ensure(guild=interaction.guild)
            await interaction.followup.send(MESSAGES["SUCCESS"].format(role_name=role.name), ephemeral=True)
            logger.debug(LOGS["ROLE_ADDED"])
        else:
            await interaction.followup.send(MESSAGES["ERROR"], ephemeral=True)
            logger.error(LOGS["ROLE_ADD_FAILED"])
    except (ValueError, Exception, HTTPException, Forbidden, NotFound) as e:
        await interaction.followup.send(MESSAGES["ERROR"], ephemeral=True)
        logger.exception(f"{LOGS['EXCEPTION']} {e}")
