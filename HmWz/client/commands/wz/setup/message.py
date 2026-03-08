import logging
from typing import Optional
from discord import app_commands, Interaction, Attachment, HTTPException, Forbidden, NotFound, InteractionResponded
from discord.app_commands import checks
from .....emojis import Emojis
from .....services import Services
from ....overviews import Manager
from ....overviews.registration import RegistrationOverview

logger = logging.getLogger(__name__)

@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.default_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.command(name="message", description="Nachricht für die WZ-Registrierung festlegen")
@app_commands.describe(message_upload="Textdatei mit der Nachricht (max. 4096 Zeichen)", title="Titel für die Nachricht (max. 256 Zeichen)", message="Text für die Nachricht (max. 4096 Zeichen)")
async def message(interaction: Interaction, title: Optional[str] = None, message: Optional[str] = None, message_upload: Optional[Attachment] = None): 
    MESSAGES = {
        "SUCCESS": f"{Emojis.SUCCESS.value} Nachricht für die WZ-Registrierung wurde erfolgreich festgelegt.",
        "NO_INPUT": f"{Emojis.ERROR.value} Übergebe zumindest eine der Optionen: title, message oder message_upload.",
        "TWO_MESSAGES": f"{Emojis.ERROR.value} Bitte übergebe nur eine der Optionen: message oder message_upload. title kann optional mit einer der beiden übergeben werden.",
        "ERROR": f"{Emojis.ERROR.value} Fehler beim Festlegen der Nachricht für die WZ-Registrierung.",
        "ERROR_FILE_TYPE": f"{Emojis.ERROR.value} Ungültiger Dateityp. Bitte lade eine Textdatei (.txt) hoch."
    }
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
            await interaction.followup.send(MESSAGES["NO_INPUT"], ephemeral=True)
            return
        
        if message_upload is not None and message is not None:
            await interaction.followup.send(MESSAGES["TWO_MESSAGES"], ephemeral=True)
            return

        if message_upload is not None and not message_upload.filename.lower().endswith((".txt")):
            await interaction.followup.send(MESSAGES["ERROR_FILE_TYPE"], ephemeral=True)
            return
        elif message_upload is not None:
            try:
                message_upload_content : bytes = await message_upload.read()
                decoded_message = message_upload_content.decode("utf-8", errors="replace")   
                        
            except Exception as e:
                logger.exception(f"{LOG_CONTEXT} Failed to read or decode uploaded file for WZ registration message: {e}")
                await interaction.followup.send(MESSAGES["ERROR"], ephemeral=True)
                return
        elif message is not None:
            decoded_message = message

        
        services: Services = getattr(interaction.client, "services")
        overview: Manager = getattr(interaction.client, "overview_manager", None)
        if not services or not overview:
            raise TypeError(LOGS["NO_SERVICES_OR_OVERVIEW"])
        
        if await services.wz.registration.setup_message(guild=interaction.guild,title=title, description=decoded_message[:4095] if decoded_message else None):
            await interaction.followup.send(MESSAGES["SUCCESS"], ephemeral=True)

            await overview.sync(guild=interaction.guild, sync_config=True)
            await overview.ensure(guild=interaction.guild)
            logger.debug(LOGS["MESSAGE_SET"])
        else:
            await interaction.followup.send(MESSAGES["ERROR"], ephemeral=True)
            logger.warning(LOGS["MESSAGE_SET_FAILED"])
    except (ValueError, HTTPException, Forbidden, NotFound, Exception, InteractionResponded) as e:
        await interaction.followup.send(MESSAGES["ERROR"], ephemeral=True)
        logger.exception(f"{LOG_CONTEXT} {e}")
    
