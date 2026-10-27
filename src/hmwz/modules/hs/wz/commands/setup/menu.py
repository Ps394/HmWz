from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import cast

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.utils.interactions import log_interaction
from hmwz.modules.hs.wz.module import WzRegistrationModule

from .channel.add import add as add_channel
from .channel.remove import remove as remove_channel
from .role.add import add as add_role
from .role.remove import remove as remove_role

_logger = logging.getLogger(__name__)


class WzSetupMenu(EphemeralView):
    def __init__(self, *, owner_id: int, context: discord.Interaction) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        labels = {
            "wz_setup_add_channel": "wz.setup.menu.add_channel",
            "wz_setup_remove_channel": "wz.setup.menu.remove_channel",
            "wz_setup_add_role": "wz.setup.menu.add_role",
            "wz_setup_remove_role": "wz.setup.menu.remove_role",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id is None:
                    continue
                label = labels.get(item.custom_id)
                if label is not None:
                    item.label = t(context, label)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "wz.setup.menu.owner")
        )
        return False

    @discord.ui.button(
        label="Add channel",
        style=discord.ButtonStyle.primary,
        custom_id="wz_setup_add_channel",
    )
    async def add_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        callback = cast(
            Callable[[discord.Interaction], Awaitable[None]], add_channel.callback
        )
        await callback(interaction)

    @discord.ui.button(
        label="Remove channel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_setup_remove_channel",
    )
    async def remove_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        callback = cast(
            Callable[[discord.Interaction], Awaitable[None]], remove_channel.callback
        )
        await callback(interaction)

    @discord.ui.button(
        label="Add role",
        style=discord.ButtonStyle.primary,
        custom_id="wz_setup_add_role",
    )
    async def add_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        callback = cast(
            Callable[[discord.Interaction, bool], Awaitable[None]], add_role.callback
        )
        await callback(interaction, False)

    @discord.ui.button(
        label="Remove role",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_setup_remove_role",
    )
    async def remove_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        callback = cast(
            Callable[[discord.Interaction], Awaitable[None]], remove_role.callback
        )
        await callback(interaction)


@app_commands.command(
    name="setup",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup", "Configure WZ channels and roles"
        ),
        key="wz.setup.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
async def setup(interaction: discord.Interaction) -> None:
    view = WzSetupMenu(owner_id=interaction.user.id, context=interaction)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            content = t(interaction, "wz.setup.menu.error")
        else:
            module: WzRegistrationModule = await manager.get_module(
                guild, WzRegistrationModule
            )
            registrations = await module.registration.get_all(guild=guild)
            roles = await module.roles.get(guild=guild)
            channels = await module.purge_channels.get(guild=guild)
            registration_channels = [
                f"<#{record.channel}>"
                for record in registrations or ()
                if record.channel is not None
            ]
            role_names = [
                f"{role.mention} — <#{record.channel_id}> "
                f"({t(interaction, 'wz.setup.role.permanent_yes' if record.permanent else 'wz.setup.role.permanent_no')})"
                for record in roles or ()
                if (role := guild.get_role(record.role)) is not None
            ]
            cleanup_channels = [f"<#{record.channel_id}>" for record in channels or ()]
            content = t(
                interaction,
                "wz.setup.menu.overview_content",
                registration_channels="\n".join(registration_channels)
                or t(interaction, "wz.setup.menu.none"),
                roles="\n".join(role_names) or t(interaction, "wz.setup.menu.none"),
                channels="\n".join(cleanup_channels)
                or t(interaction, "wz.setup.menu.none"),
            )
    except Exception:
        _logger.exception(
            "%s WZ setup configuration failed.", log_interaction(interaction)
        )
        content = t(interaction, "wz.setup.menu.error")
    await interaction.response.send_message(content, view=view, ephemeral=True)
    view.message = await interaction.original_response()
