import logging
from discord import app_commands, Interaction, HTTPException, Forbidden, NotFound
from ......emojis import Emojis
from ......services import Services
from ...... import utils
from .....overviews import Manager
from .....overviews.registration import RegistrationOverview, Configuration, Data
from discord.app_commands import checks

from ......i18n import CommandLocalizations, t
from ...... import configuration

logger = logging.getLogger(__name__)

async def remove_autocomplete(interaction: Interaction, current: str) -> tuple[app_commands.Choice[str]]:
    manager: Manager = getattr(interaction.client, "overview_manager", None)
    instance: RegistrationOverview = await manager.get_instance(interaction.guild, RegistrationOverview) if manager else None
    overview_config: Configuration = instance.configuration if instance else None
    
    if not overview_config or overview_config.has_roles == False:
        return []

    
    return [
        app_commands.Choice(name=configured.role.name, value=str(configured.role.id))
        for configured in overview_config.roles
        if current.lower() in configured.role.name.lower()
    ][:25] 

@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.command(
    name="role-remove",     
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.roles.remove.description", "-"),
        key="wz.setup.roles.remove.description",
    ),
)
@app_commands.describe(
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.roles.remove.role.description", "-"),
        key="wz.setup.roles.remove.role.description",
    )
)
@app_commands.autocomplete(role=remove_autocomplete)
async def remove(interaction: Interaction, role: str):
    MIN_ROLES = configuration.WzRegistration.MIN_REGISTRATION_ROLES.value
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
        manager: Manager = getattr(interaction.client, "overview_manager", None)
        instance: RegistrationOverview = await manager.get_instance(interaction.guild, RegistrationOverview) if manager else None
        overview_config: Configuration = instance.configuration if instance else None
        data: Data = instance.data if instance else None

        if not services or not overview_config or not data:
            raise ValueError(LOGS["NO_SERVICES_OR_OVERVIEW"])
        
        role_to_remove = await utils.fetch_role(interaction.guild, int(role))
        
        if role_to_remove is None or not any(configured.role.id == role_to_remove.id for configured in overview_config.roles):
            await interaction.followup.send(t(interaction, "wz.setup.roles.remove.unknown_role"), ephemeral=True)
            logger.warning(LOGS["UNKNOWN_ROLE"].format(role=role_to_remove.name if role_to_remove else "None"))
            return 
        
        if await services.wz.roles.count(guild=interaction.guild) <= MIN_ROLES:
            await interaction.followup.send(t(interaction, "wz.setup.roles.remove.min_roles"), ephemeral=True)
            logger.warning(LOGS["MIN_ROLES"])
            return
        
        for member in interaction.guild.members:
            if member.bot:
                continue
            if role_to_remove in member.roles:
                try:
                    await member.remove_roles(role_to_remove, reason="WZ Registration Role Removal")
                except (HTTPException, Forbidden) as e:
                    logger.exception(f"{log_context} Failed to remove role {role_to_remove.name} from member {member}: {e}")
        
        if await services.wz.roles.remove(guild=interaction.guild, role=role_to_remove.id):
            await interaction.followup.send(t(interaction, "wz.setup.roles.remove.success", role_name=role_to_remove.name), ephemeral=True)
            await manager.sync(guild=interaction.guild, sync_config=True, sync_data=True)
            await manager.ensure(guild=interaction.guild)
            logger.debug(LOGS["ROLE_REMOVED"].format(role_name=role_to_remove.name))
        else:
            await interaction.followup.send(t(interaction, "wz.setup.roles.remove.error"), ephemeral=True)
            logger.error(LOGS["ROLE_REMOVE_FAILED"].format(role_name=role_to_remove.name))
    except (ValueError, Exception, HTTPException, Forbidden, NotFound) as e:
        await interaction.followup.send(t(interaction, "wz.setup.roles.remove.unexpected"), ephemeral=True)
        logger.exception(f"{log_context} {e}")
