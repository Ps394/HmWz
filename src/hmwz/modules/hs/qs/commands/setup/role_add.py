import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.utils import log_interaction

from .common import add_registration_role, get_setup_context

_logger = logging.getLogger(__name__)


@app_commands.command(
    name="role-add",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.qs.setup.role_add", "Add a QS registration role"
        ),
        key="qs.setup.role_add.description",
    ),
)
@app_commands.describe(
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.qs.setup.role_add.role", "Registration role"
        ),
        key="qs.setup.role_add.role.description",
    )
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
async def role_add(interaction: discord.Interaction, role: discord.Role) -> None:
    """Add a non-permanent QS registration role to the current channel."""
    await interaction.response.defer(ephemeral=True)
    try:
        context = await get_setup_context(interaction)
        if context is None:
            return
        if not await add_registration_role(interaction, context, role):
            return
        await interaction.followup.send(
            t(interaction, "qs.setup.role_added", role_name=role.name),
            ephemeral=True,
        )
    except Exception:
        _logger.exception("%s QS role setup failed.", log_interaction(interaction))
        await interaction.followup.send(
            t(interaction, "qs.setup.error"), ephemeral=True
        )
