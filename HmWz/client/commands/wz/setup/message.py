import logging
from typing import Optional
from discord import app_commands, Interaction, Attachment, HTTPException, Forbidden, NotFound, InteractionResponded
from discord.app_commands import checks
from .....services import Services
from ....overviews import Manager
from ....overviews.registration import RegistrationOverview
        
from .....i18n import CommandLocalizations, t

logger = logging.getLogger(__name__)

@app_commands.checks.has_permissions(moderate_members=True, manage_messages=True)
@app_commands.command(
    name="message",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.message.description", "-"),
        key="wz.setup.message.description",
    ),
)
@app_commands.describe(
    title=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.message.title.description", "-"),
        key="wz.setup.message.title.description",
    ),
    message=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.message.message.description", "-"),
        key="wz.setup.message.message.description",
    ),
    message_upload=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.message.message_upload.description", "-"),
        key="wz.setup.message.message_upload.description",
    ),
)
async def message(interaction: Interaction, title: Optional[str] = None, message: Optional[str] = None, message_upload: Optional[Attachment] = None): 
    LOG_CONTEXT = f"{interaction.guild.name}({interaction.guild.id}) - {interaction.user} - WZ Setup Message : "
    LOGS = {
        "NO_SERVICES_OR_OVERVIEW": f"{LOG_CONTEXT} Required services or overview manager not found on client.",
        "MESSAGE_SET": f"{LOG_CONTEXT} hat die Nachricht für die WZ-Registrierung festgelegt.",
        "MESSAGE_SET_FAILED": f"{LOG_CONTEXT} konnte die Nachricht für die WZ-Registrierung nicht festlegen.",
        "FILE_TYPE": f"{LOG_CONTEXT} Ungültiger Dateityp {message_upload.filename if message_upload else 'None'} für WZ-Registrierungsnachricht. Nur .txt-Dateien sind erlaubt."
}
    try:
        await interaction.response.defer(ephemeral=True) 
        decoded_message = None
        if not title and not message and not message_upload:
            await interaction.followup.send(t(interaction, "wz.setup.message.no_input"), ephemeral=True)
            return
        
        if message_upload is not None and message is not None:
            await interaction.followup.send(t(interaction, "wz.setup.message.two_messages"), ephemeral=True)
            return

        if message_upload is not None and not message_upload.filename.lower().endswith((".txt")):
            await interaction.followup.send(t(interaction, "wz.setup.message.error_file_type"), ephemeral=True)
            return
        elif message_upload is not None:
            try:
                message_upload_content : bytes = await message_upload.read()
                decoded_message = message_upload_content.decode("utf-8", errors="replace")   
                        
            except Exception as e:
                logger.exception(f"{LOG_CONTEXT} Failed to read or decode uploaded file for WZ registration message: {e}")
                await interaction.followup.send(t(interaction, "wz.setup.message.error"), ephemeral=True)
                return
        elif message is not None:
            decoded_message = message

        
        services: Services = getattr(interaction.client, "services")
        overview: Manager = getattr(interaction.client, "overview_manager", None)
        if not services or not overview:
            raise TypeError(LOGS["NO_SERVICES_OR_OVERVIEW"])
        
        if await services.wz.registration.setup_message(guild=interaction.guild,title=title, description=decoded_message[:4095] if decoded_message else None):
            await interaction.followup.send(t(interaction, "wz.setup.message.success"), ephemeral=True)

            await overview.sync(guild=interaction.guild, sync_config=True)
            await overview.ensure(guild=interaction.guild)
            logger.debug(LOGS["MESSAGE_SET"])
        else:
            await interaction.followup.send(t(interaction, "wz.setup.message.error"), ephemeral=True)
            logger.warning(LOGS["MESSAGE_SET_FAILED"])
    except (ValueError, HTTPException, Forbidden, NotFound, Exception, InteractionResponded) as e:
        await interaction.followup.send(t(interaction, "wz.setup.message.error"), ephemeral=True)
        logger.exception(f"{LOG_CONTEXT} {e}")
    
