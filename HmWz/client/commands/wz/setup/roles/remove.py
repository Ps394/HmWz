import logging
from discord import app_commands, Interaction, HTTPException, Forbidden, NotFound
from ......emojis import Emojis
from ......services import Services
from .....overviews import Manager
from discord.app_commands import checks

logger = logging.getLogger(__name__)

async def remove_autocomplete(interaction: Interaction, current: str) -> tuple[app_commands.Choice[str]]:
    services: Services = getattr(interaction.client, "services", None)
    if not services:
        return []
    
    configured_roles = await services.wz.roles.get(guild=interaction.guild)
    
    if not configured_roles:
        return []

    return [
        app_commands.Choice(name=role_record.role.name, value=str(role_record.role.id))
        for role_record in configured_roles
        if current.lower() in role_record.role.name.lower()
    ][:25] 

@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.default_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.command(name="role-remove", description="Wz-Registrierungsrolle entfernen")
@app_commands.describe(role="Rolle, die aus der WZ-Registrierung entfernt werden soll")
@app_commands.autocomplete(role=remove_autocomplete)
async def remove(interaction: Interaction, role: str):
    MIN_ROLES = 1
    MESSAGES = {
        "ERROR": f"{Emojis.ERROR.value} Fehler beim Entfernen der Rolle aus der WZ-Registrierung.",
        "UNKNOWN_ROLE": f"{Emojis.WARNING.value} Unbekannte Rolle. Bitte wähle eine Rolle aus der Autovervollständigung aus.",
        "MIN_ROLES": f"{Emojis.WARNING.value} Es muss mindestens eine Rolle für die WZ-Registrierung festgelegt sein.",
        "SUCCESS": f"{Emojis.SUCCESS.value} Rolle {{role_name}} wurde aus der WZ-Registrierung entfernt.",
        "UNEXPECTED": f"{Emojis.ERROR.value} Unerwarteter Fehler beim Entfernen der Rolle aus der WZ-Registrierung."
    }
    log_context = f"{interaction.guild.name}({interaction.guild.id}) - {interaction.user} - WZ Setup Role Remove : "
    LOGS = {
        "EXCEPTION": f"{log_context}",
        "NO_SERVICES_OR_OVERVIEW": f"{log_context} Required services or overview manager not found on client.",
        "UNKNOWN_ROLE": f"{log_context} Unbekannte Rolle {role}.",
        "MIN_ROLES": f"{log_context} versuchte, die letzte Rolle aus der WZ-Registrierung zu entfernen.",
        "ROLE_REMOVED": f"{log_context} hat die Rolle {{role_name}} aus der WZ-Registrierung entfernt.",
        "ROLE_REMOVE_FAILED": f"{log_context} konnte die Rolle {{role_name}} nicht aus der WZ-Registrierung entfernen."
    }
    await interaction.response.defer(ephemeral=True)
    try:
        services: Services = getattr(interaction.client, "services")
        overview_manager: Manager = getattr(interaction.client, "overview_manager", None)
        if not services or not overview_manager:
            raise ValueError(LOGS["NO_SERVICES_OR_OVERVIEW"])
        
        role_obj = interaction.guild.get_role(int(role))
        if not role_obj:
            await interaction.followup.send(MESSAGES["UNKNOWN_ROLE"], ephemeral=True)
            return 
        
        if await services.wz.roles.count(guild=interaction.guild) <= MIN_ROLES:
            await interaction.followup.send(MESSAGES["MIN_ROLES"], ephemeral=True)
            logger.warning(LOGS["MIN_ROLES"])
            return
        
        role_to_removed = services.wz.roles.get(guild=interaction.guild, role=role_obj.id)  
        for member in interaction.guild.members:
            if role_obj in member.roles:
                try:
                    await member.remove_roles(role_obj, reason="WZ Registration Role Removal")
                    logger.debug(f"{log_context} Removed role {role_obj.name} from member {member}.")
                except (HTTPException, Forbidden) as e:
                    logger.exception(f"{log_context} Failed to remove role {role_obj.name} from member {member}: {e}")

        if await services.wz.roles.remove(guild=interaction.guild, role=role_obj.id):
            await interaction.followup.send(MESSAGES["SUCCESS"].format(role_name=role_obj.name), ephemeral=True)
            await overview_manager.sync(guild=interaction.guild, sync_config=True, sync_data=True)
            await overview_manager.ensure(guild=interaction.guild)
            logger.debug(LOGS["ROLE_REMOVED"].format(role_name=role_obj.name))
        else:
            await interaction.followup.send(MESSAGES["ERROR"], ephemeral=True)
            logger.error(LOGS["ROLE_REMOVE_FAILED"].format(role_name=role_obj.name))
    except (ValueError, Exception, HTTPException, Forbidden, NotFound) as e:
        await interaction.followup.send(MESSAGES["UNEXPECTED"], ephemeral=True)
        logger.exception(f"{log_context} {e}")
