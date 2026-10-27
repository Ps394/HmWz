import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.interactions import log_interaction

from .common import add_registration_role, get_setup_context

_logger = logging.getLogger(__name__)


@app_commands.command(
    name="configure",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.qs.setup.configure", "Configure QS registration"
        ),
        key="qs.setup.configure.description",
    ),
)
@app_commands.describe(
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.qs.setup.configure.role",
            "QS registration role",
        ),
        key="qs.setup.configure.role.description",
    )
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
async def configure(interaction: discord.Interaction, role: discord.Role) -> None:
    """Configure the current channel as a QS registration channel."""
    await interaction.response.defer(ephemeral=True)
    try:
        context = await get_setup_context(interaction)
        if context is None:
            return
        if not await add_registration_role(interaction, context, role):
            return
        await interaction.followup.send(
            t(
                interaction,
                "qs.setup.configure.success",
                channel_name=f"<#{context.channel_id}>",
            ),
            ephemeral=True,
        )
    except Exception:
        _logger.exception(
            "%s QS registration configuration failed.", log_interaction(interaction)
        )
        await interaction.followup.send(
            t(interaction, "qs.setup.error"), ephemeral=True
        )
