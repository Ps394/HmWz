import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.loaders import fetch_member
from hmwz.utils.interactions import log_interaction

from .common import get_setup_context

_logger = logging.getLogger(__name__)


@app_commands.command(
    name="role-remove",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.qs.setup.role_remove",
            "Remove a QS registration role",
        ),
        key="qs.setup.role_remove.description",
    ),
)
@app_commands.describe(
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.qs.setup.role_remove.role", "Registration role"
        ),
        key="qs.setup.role_remove.role.description",
    )
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
async def role_remove(interaction: discord.Interaction, role: discord.Role) -> None:
    """Remove a QS role and its registrations from the current channel."""
    await interaction.response.defer(ephemeral=True)
    try:
        context = await get_setup_context(interaction)
        if context is None:
            return

        configured = await context.module.roles.get(
            guild=context.guild, channel_id=context.channel_id
        )
        if not any(item.role == role.id for item in configured or ()):
            await interaction.followup.send(
                t(interaction, "qs.setup.role_unknown"), ephemeral=True
            )
            return
        if len(configured or ()) <= 1:
            await interaction.followup.send(
                t(interaction, "qs.setup.min_roles"), ephemeral=True
            )
            return

        registrations = await context.module.registrations.get(
            guild=context.guild, channel_id=context.channel_id
        )
        for registration in registrations or ():
            if registration.role != role.id or registration.member is None:
                continue
            member = await fetch_member(context.guild, registration.member)
            if member is None or role not in member.roles:
                continue
            try:
                await member.remove_roles(role, reason="QS Registration Role Removal")
            except discord.HTTPException:
                _logger.exception(
                    "Failed to remove QS role %s from member %s in guild %s.",
                    role.id,
                    member.id,
                    context.guild.id,
                )

        if not await context.module.roles.remove(
            guild=context.guild, role=role.id, channel_id=context.channel_id
        ):
            await interaction.followup.send(
                t(interaction, "qs.setup.error"), ephemeral=True
            )
            return
        if not await context.module.registrations.remove(
            guild=context.guild, role=role.id, channel_id=context.channel_id
        ):
            await interaction.followup.send(
                t(interaction, "qs.setup.error"), ephemeral=True
            )
            return
        if not await context.module.compose_registration_overview(
            force=True, channel_id=context.channel_id
        ):
            await interaction.followup.send(
                t(interaction, "qs.setup.error"), ephemeral=True
            )
            return
        await interaction.followup.send(
            t(interaction, "qs.setup.role_removed", role_name=role.name),
            ephemeral=True,
        )
    except Exception:
        _logger.exception("%s QS role removal failed.", log_interaction(interaction))
        await interaction.followup.send(
            t(interaction, "qs.setup.error"), ephemeral=True
        )
