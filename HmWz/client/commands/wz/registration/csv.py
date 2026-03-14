import logging
import io
from discord import app_commands, Interaction, File
from ....overviews import Manager
from ....overviews.registration import RegistrationOverview, Data, Configuration
from .....services import Services
from .....i18n import CommandLocalizations, t

logger = logging.getLogger(__name__)

@app_commands.checks.bot_has_permissions(attach_files=True)
@app_commands.command(
    name="csv",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.registration.csv.description", "-"),
        key="wz.registration.csv.description",
    ),
)
@app_commands.describe(
    ephemeral=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("ephemeral.description", "-"),
        key="ephemeral.description",
    )
)
@app_commands.checks.cooldown(1, 120, key=lambda i: (i.guild_id))
async def csv(interaction: Interaction, ephemeral: bool = True):
    LOG_CONTEXT = f"{interaction.guild.name}({interaction.guild.id}) - {interaction.user} - WZ Registration CSV : "
    LOGS = {
        "EXCEPTION": f"{LOG_CONTEXT}",
        "NO_SERVICES_OR_OVERVIEW": f"{LOG_CONTEXT} Required services or overview manager not found on client.",
        "NO_REGISTRATIONS": f"{LOG_CONTEXT} No registrations found to export."
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
        
        if configuration.is_valid == False:
            await interaction.followup.send(t(interaction, "wz.registration.error.not_configured"), ephemeral=True)
            return
        
        if len(data.members) == 0:
            await interaction.followup.send(t(interaction, "wz.registration.csv.no_registrations"), ephemeral=True)
            logger.warning(LOGS["NO_REGISTRATIONS"])
            return
        
        csv_content = "NR; Discord_Name; Guild_Name; Role; Timestamp; Score; Comment\n"
        for idx, member in enumerate(data.members, start=1):
            user_name = member.member.name if member.member and member.member.name else "null"
            member_name = member.member.display_name if member.member and member.member.display_name else "null"
            role_name = member.role.role.name if member.role else "Unknown Role"
            score = member.score if member.score is not None else 0
            comment = ""
            timestamp = member.timestamp if member.timestamp else "Unknown Timestamp"
            csv_content += f"{idx}; {user_name}; {member_name}; {role_name}; {timestamp}; {score}; {comment}\n"
        try:
            bio = io.BytesIO(csv_content.encode('utf-8-sig'))
            bio.seek(0)
            csv_file = File(fp=bio, filename=f"wz_registrations_{interaction.guild.id}.csv")
            await interaction.followup.send(content=t(interaction, "wz.registration.csv.success"), file=csv_file, ephemeral=True)
        finally:
            try:
                bio.close()
            except Exception:
                pass
    except Exception as e:
        await interaction.followup.send(t(interaction, "wz.registration.csv.error"), ephemeral=True)
        logger.exception(f"{LOGS['EXCEPTION']} {e}")
