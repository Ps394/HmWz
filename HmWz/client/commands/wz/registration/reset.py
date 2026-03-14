import asyncio
import logging
from discord import app_commands, Interaction, HTTPException, Forbidden, NotFound, InteractionResponded
from .....emojis import Emojis
from .....services import Services
from ....overviews import Manager
from ....overviews.registration import RegistrationOverview, Configuration, Data
from .....i18n import CommandLocalizations, t

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
    LOG_CONTEXT = f"{interaction.guild.name}({interaction.guild.id}) - {interaction.user} - WZ Registration Reset : "
    LOGS = {
        "EXCEPTION": f"{LOG_CONTEXT}",
        "NO_SERVICES_OR_OVERVIEW": f"{LOG_CONTEXT} Required services or overview manager not found on client.",
        "NOT_CONFIGURED": f"{LOG_CONTEXT} No registration channel configured.",
        "NO_REGISTRATIONS": f"{LOG_CONTEXT} No removable registrations found."
    }
    try:
        await interaction.response.defer(ephemeral=ephemeral)
        services: Services = getattr(interaction.client, "services")
        overview_manager: Manager = getattr(interaction.client, "overview_manager", None)
        overview_instance: RegistrationOverview = await overview_manager.get_instance(interaction.guild, RegistrationOverview) if overview_manager else None
        configuration: Configuration = overview_instance.configuration if overview_instance else None
        data: Data = overview_instance.data if overview_instance else None
        if not services or not overview_manager or not overview_instance or not configuration or not data:
            raise TypeError(LOGS["NO_SERVICES_OR_OVERVIEW"])
        
        if not configuration.is_valid:
            await interaction.followup.send(t(interaction, "wz.registration.error.not_configured"), ephemeral=True)
            raise ValueError(LOGS["NOT_CONFIGURED"])

        if len(data.members) == 0:
            await interaction.followup.send(t(interaction, "wz.registration.csv.no_registrations"), ephemeral=True)
            logger.warning(LOGS["NO_REGISTRATIONS"])
            return
        
        for member in data.members:
            try: 
                if member.member and member.role and not member.role.permanent:
                    await member.member.remove_roles(member.role.role, reason="WZ Registration Reset")
                    await asyncio.sleep(0.05)
            except (HTTPException, Forbidden, NotFound) as e:
                logger.warning(f"{LOG_CONTEXT} Failed to remove role {member.role.role.id} from member {member.member.id} during WZ reset: {e}")
        
        success = await services.wz.registrations.remove(guild=interaction.guild, roles=configuration.non_permanent_roles_ids)
        if success:
            await overview_instance.clean()
            await overview_instance.sync(sync_config=True, sync_data=True)
            await overview_instance.ensure()
            await interaction.followup.send(t(interaction, "wz.registration.reset.success"), ephemeral=ephemeral)
        else:
            await interaction.followup.send(t(interaction, "wz.registration.reset.error"), ephemeral=ephemeral)
    except (ValueError, HTTPException, Forbidden, NotFound, InteractionResponded, Exception) as e:
        await interaction.followup.send(t(interaction, "wz.registration.reset.error"), ephemeral=ephemeral)
        logger.exception(f"{LOGS['EXCEPTION']} {e}")
        return