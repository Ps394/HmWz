from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.messages import send_followup, send_temporary_followup
from hmwz.utils.interactions import log_interaction
from hmwz.modules.hs.wz.module import WzModule

from .selection import SetupRoleSelection

_logger = logging.getLogger(__name__)


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.command(
    name="remove",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.role.remove", "-"
        ),
        key="wz.role.remove.description",
    ),
)
async def remove(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await send_temporary_followup(
                interaction, t(interaction, "wz.setup.role.error")
            )
            return

        module: WzModule = await manager.get_module(guild, WzModule)
        configured_roles = await module.roles.get(guild=guild)
        roles = [
            role
            for record in configured_roles or ()
            if (role := guild.get_role(record.role)) is not None
        ]
        if not roles:
            await send_temporary_followup(
                interaction, t(interaction, "wz.setup.role.no_configured_roles")
            )
            return
        roles.sort(key=lambda role: (role.name.casefold(), role.id))
        view = SetupRoleSelection(
            guild=guild,
            module=module,
            owner_id=interaction.user.id,
            action="remove",
            roles=roles,
            max_selected=min(len(roles), 25),
            context=interaction,
        )
        view.message = await send_followup(
            interaction,
            embed=view.selection_embed(interaction),
            view=view,
            ephemeral=True,
            wait=True,
        )
    except Exception as error:
        _logger.exception(
            "%s WZ setup role remove failed: %s",
            log_interaction(interaction),
            error,
        )
        await send_temporary_followup(
            interaction, t(interaction, "wz.setup.role.error")
        )
