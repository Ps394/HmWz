from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.messages import send_followup, send_temporary_followup
from hmwz.utils.interactions import log_interaction
from hmwz.modules.hs.wz.module import WzModule
from hmwz.modules.hs.wz.models import Role

from .selection import SetupRoleSelection

_logger = logging.getLogger(__name__)


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.command(
    name="add",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("command.description.wz.role.add", "-"),
        key="wz.role.add.description",
    ),
)
async def add(interaction: discord.Interaction) -> None:
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
        configured_ids = {record.role for record in configured_roles or ()}
        available_roles = [
            role
            for role in guild.roles
            if role.id not in configured_ids
            and not role.is_default()
            and not role.managed
            and (guild.me is None or role < guild.me.top_role)
        ]
        available_roles.sort(key=lambda role: (role.name.casefold(), role.id))
        slots = Role.MAX_PER_GUILD - len(configured_ids)
        if not available_roles or slots <= 0:
            await send_temporary_followup(
                interaction,
                t(
                    interaction,
                    "wz.setup.role.no_available_roles"
                    if slots > 0
                    else "wz.setup.role.max_roles",
                    max_roles=Role.MAX_PER_GUILD,
                ),
            )
            return

        view = SetupRoleSelection(
            guild=guild,
            module=module,
            owner_id=interaction.user.id,
            action="add",
            roles=available_roles,
            max_selected=slots,
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
            "%s WZ setup role add failed: %s",
            log_interaction(interaction),
            error,
        )
        await send_temporary_followup(
            interaction, t(interaction, "wz.setup.role.error")
        )
