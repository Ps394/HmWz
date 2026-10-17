import logging

from discord import Attachment, Interaction, app_commands

from hmwz.i18n import CommandLocalizations, t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


@app_commands.checks.has_permissions(moderate_members=True, manage_messages=True)
@app_commands.command(
    name="message",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup.message", "-"
        ),
        key="wz.setup.message.description",
    ),
)
@app_commands.describe(
    title=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.message.title", "-"
        ),
        key="wz.setup.message.title.description",
    ),
    message=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.message.message", "-"
        ),
        key="wz.setup.message.message.description",
    ),
    message_upload=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.message.message_upload", "-"
        ),
        key="wz.setup.message.message_upload.description",
    ),
)
async def message(
    interaction: Interaction,
    title: str | None = None,
    message: str | None = None,
    message_upload: Attachment | None = None,
):
    await interaction.response.defer(ephemeral=True)
    try:
        if not interaction.guild:
            await interaction.followup.send(
                t(interaction, "wz.setup.message.error"), ephemeral=True
            )
            return

        if not title and not message and not message_upload:
            await interaction.followup.send(
                t(interaction, "wz.setup.message.no_input"), ephemeral=True
            )
            return
        if message and message_upload:
            await interaction.followup.send(
                t(interaction, "wz.setup.message.two_messages"), ephemeral=True
            )
            return

        decoded_message = message
        if message_upload is not None:
            if not message_upload.filename.lower().endswith(".txt"):
                await interaction.followup.send(
                    t(interaction, "wz.setup.message.error_file_type"), ephemeral=True
                )
                return
            decoded_message = (await message_upload.read()).decode(
                "utf-8", errors="replace"
            )

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.message.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            interaction.guild, WzRegistrationModule
        )
        ok = await module.registration.upsert(
            guild=interaction.guild,
            title=title,
            description=(decoded_message[:4095] if decoded_message else None),
        )
        if not ok:
            await interaction.followup.send(
                t(interaction, "wz.setup.message.error"), ephemeral=True
            )
            return

        await module.compose_registration_overview(force=True)
        await interaction.followup.send(
            t(interaction, "wz.setup.message.success"), ephemeral=True
        )
    except Exception as e:
        logger.exception(f"WZ setup message failed: {e}")
        await interaction.followup.send(
            t(interaction, "wz.setup.message.error"), ephemeral=True
        )
