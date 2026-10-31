from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import cast

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import (
    delete_temporary_message,
    edit_original_response,
    send_interaction_response,
    send_temporary_followup,
)
from hmwz.utils.interactions import log_interaction
from hmwz.modules.hs.wz.module import WzModule

from ...models import Channel, Role
from .channel.add import add as add_channel
from .channel.remove import remove as remove_channel
from .role.add import add as add_role
from .role.remove import remove as remove_role

_logger = logging.getLogger(__name__)


async def configuration_embed(
    module: WzModule, context: discord.Interaction
) -> discord.Embed:
    """Present guild-wide WZ settings in clearly separated, bounded fields."""
    roles = await module.roles.get(guild=module.guild) or ()
    channels = await module.channels.get(guild=module.guild) or ()
    embed = create_embed(
        title=t(context, "wz.setup.menu.title"),
        description=t(
            context,
            "wz.setup.menu.summary",
            role_count=len(roles),
            max_roles=Role.MAX_PER_GUILD,
            channel_count=len(channels),
            max_channels=Channel.MAX_PER_GUILD,
        ),
    )
    names = [f"<@&{record.role}>" for record in roles]
    visible_roles = names[:25]
    if len(names) > len(visible_roles):
        visible_roles.append(
            t(
                context,
                "wz.setup.role.more_roles",
                count=len(names) - len(visible_roles),
            )
        )
    embed.add_field(
        name=t(context, "wz.setup.menu.roles"),
        value="\n".join(visible_roles) or t(context, "wz.setup.menu.none"),
        inline=False,
    )
    channel_names = [f"<#{record.channel_id}>" for record in channels]
    # Legacy configurations can contain more than the current guild limit.
    visible_channels = channel_names[:25]
    if len(channel_names) > len(visible_channels):
        visible_channels.append(
            t(
                context,
                "wz.clean_channels.more_channels",
                count=len(channel_names) - len(visible_channels),
            )
        )
    embed.add_field(
        name=t(context, "wz.setup.menu.channels"),
        value="\n".join(visible_channels) or t(context, "wz.setup.menu.none"),
        inline=False,
    )
    return embed


class WzSetupMenu(EphemeralView):
    def __init__(self, *, owner_id: int, context: discord.Interaction) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        labels = {
            "wz_setup_add_channel": "wz.setup.menu.add_channel",
            "wz_setup_remove_channel": "wz.setup.menu.remove_channel",
            "wz_setup_add_role": "wz.setup.menu.add_role",
            "wz_setup_remove_role": "wz.setup.menu.remove_role",
            "wz_setup_refresh": "wz.setup.menu.refresh",
            "wz_setup_close": "wz.setup.menu.close",
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
        row=1,
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
        row=1,
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
        row=0,
    )
    async def add_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        callback = cast(
            Callable[[discord.Interaction], Awaitable[None]], add_role.callback
        )
        await callback(interaction)

    @discord.ui.button(
        label="Remove role",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_setup_remove_role",
        row=0,
    )
    async def remove_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        callback = cast(
            Callable[[discord.Interaction], Awaitable[None]], remove_role.callback
        )
        await callback(interaction)

    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_setup_refresh",
        row=2,
    )
    async def refresh_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Reload settings after another setup action."""
        await interaction.response.defer()
        try:
            manager = getattr(interaction.client, "module_manager", None)
            if manager is None or interaction.guild is None:
                raise LookupError("WZ setup requires a guild and module manager.")
            module: WzModule = await manager.get_module(interaction.guild, WzModule)
            await edit_original_response(
                interaction,
                content=None,
                embed=await configuration_embed(module, interaction),
                view=self,
            )
        except (LookupError, discord.HTTPException):
            _logger.exception(
                "%s Failed to refresh WZ setup.", log_interaction(interaction)
            )
            await self.finish(interaction, t(interaction, "wz.setup.menu.error"))

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_setup_close",
        row=2,
    )
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Close the private setup panel."""
        self.stop()
        await interaction.response.defer()
        await delete_temporary_message(interaction.message or self.message)


@app_commands.command(
    name="setup",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup", "Configure WZ channels and roles"
        ),
        key="wz.setup.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "offiziere", "Moderator", "moderator", "officier", "Officier")
async def setup(interaction: discord.Interaction) -> None:
    view = WzSetupMenu(owner_id=interaction.user.id, context=interaction)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            content = t(interaction, "wz.setup.menu.error")
        else:
            module: WzModule = await manager.get_module(guild, WzModule)
            view.message = await send_interaction_response(
                interaction,
                embed=await configuration_embed(module, interaction),
                view=view,
                ephemeral=True,
            )
            return
    except Exception:
        _logger.exception(
            "%s WZ setup configuration failed.", log_interaction(interaction)
        )
        content = t(interaction, "wz.setup.menu.error")
    view.stop()
    if interaction.response.is_done():
        await send_temporary_followup(interaction, content)
    else:
        await view.send_temporary_response(interaction, content)
