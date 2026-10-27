import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.interactions import log_interaction

from .common import get_setup_context

_logger = logging.getLogger(__name__)


@app_commands.command(
    name="message",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.qs.setup.message",
            "Set the QS registration overview text",
        ),
        key="qs.setup.message.description",
    ),
)
@app_commands.describe(
    title=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.qs.setup.message.title", "Overview title"
        ),
        key="qs.setup.message.title.description",
    ),
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.qs.setup.message.description",
            "Overview description",
        ),
        key="qs.setup.message.description.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
async def message(
    interaction: discord.Interaction,
    title: str | None = None,
    description: str | None = None,
) -> None:
    """Update the QS overview title and/or description for the current channel."""
    await interaction.response.defer(ephemeral=True)
    try:
        if title is None and description is None:
            await interaction.followup.send(
                t(interaction, "qs.setup.error"), ephemeral=True
            )
            return
        context = await get_setup_context(interaction)
        if context is None:
            return

        if not await context.module.registration.upsert(
            guild=context.guild,
            channel_id=context.channel_id,
            title=title,
            description=description,
        ):
            await interaction.followup.send(
                t(interaction, "qs.setup.error"), ephemeral=True
            )
            return

        overview_updated = await context.module.compose_registration_overview(
            force=True, channel_id=context.channel_id
        )
        await interaction.followup.send(
            t(
                interaction,
                "qs.setup.message_saved"
                if overview_updated
                else "qs.setup.message_saved_overview_failed",
            ),
            ephemeral=True,
        )
    except Exception:
        _logger.exception(
            "%s QS registration message setup failed.",
            log_interaction(interaction),
        )
        await interaction.followup.send(
            t(interaction, "qs.setup.error"), ephemeral=True
        )
