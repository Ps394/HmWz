import logging
from typing import Optional
from discord import app_commands, Interaction, TextChannel, Role, HTTPException, Forbidden, NotFound
from discord.app_commands import checks
from .....emojis import Emojis
from .....services import Services
from ....overviews import Manager
from .....i18n import CommandLocalizations, t

logger = logging.getLogger(__name__)        

@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.command(
    name="configure",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.configure.description", "-"),
        key="wz.setup.configure.description",
    ),
)
@app_commands.describe(
    channel=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.configure.channel.description", "-"),
        key="wz.setup.configure.channel.description",
    ),
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.configure.role.description", "-"),
        key="wz.setup.configure.role.description",
    ),
)
async def configure(interaction: Interaction, channel: TextChannel, role: Optional[Role]=None):
    LOG_CONTEXT = f"{interaction.guild.name}({interaction.guild.id}) - {interaction.user} - WZ Setup Registration Configure : "
    LOGS = {
        "EXCEPTION": f"{LOG_CONTEXT}",
        "NO_SERVICES_OR_OVERVIEW": f"{LOG_CONTEXT} Required services or overview manager not found on client.",
        "ROLE_HIERARCHY": f"{LOG_CONTEXT} Rolle {role.name if role else 'None'} ist höher als Bot-Rolle.",
        "NO_CONFIGURED_ROLE": f"{LOG_CONTEXT} Es muss mindestens eine Rolle für die WZ-Registrierung festgelegt sein, wenn kein Kanal konfiguriert ist.",
        "CONFIGURED": f"{LOG_CONTEXT} hat die WZ-Registrierung mit Kanal {channel.name} und Rolle {role.name if role else 'None'} eingerichtet.",
        "CONFIGURE_FAILED": f"{LOG_CONTEXT} konnte die WZ-Registrierung nicht einrichten."
    }
    await interaction.response.defer(ephemeral=True)
    try:
        services: Services = getattr(interaction.client, "services")
        overview_manager: Manager = getattr(interaction.client, "overview_manager", None)
        if not services or not overview_manager:
            raise RuntimeError(LOGS["NO_SERVICES_OR_OVERVIEW"])
        
        success_channel = await services.wz.registration.setup_channel(guild=interaction.guild, channel=channel.id)

        if role is None and await services.wz.roles.count(guild=interaction.guild) == 0:
            logger.error(LOGS["NO_CONFIGURED_ROLE"])
            await interaction.followup.send(t(interaction, "wz.setup.configure.error_no_configured_role"), ephemeral=True)
            return
        success_role = None
        if role:
            if role >= interaction.guild.me.top_role:
                await interaction.followup.send(t(interaction, "wz.setup.configure.error_role_hierarchy"), ephemeral=True)
                logger.error(LOGS["ROLE_HIERARCHY"])
                return
            success_role = await services.wz.roles.add(guild=interaction.guild, role=role.id, permanent=False, score=1)

        if success_channel or success_role:
           
            await overview_manager.sync(guild=interaction.guild, sync_config=True, sync_discord=True)
            await overview_manager.ensure(guild=interaction.guild)
            await interaction.followup.send(t(interaction, "wz.setup.configure.success", channel_name=channel.name), ephemeral=True)
        else:
            await interaction.followup.send(t(interaction, "wz.setup.configure.error"), ephemeral=True)
    except (ValueError, RuntimeError, HTTPException, Forbidden, NotFound, Exception) as e:
        await interaction.followup.send(t(interaction, "wz.setup.configure.error"), ephemeral=True)
        logger.exception(f"{LOGS['EXCEPTION']} {e}")
    


