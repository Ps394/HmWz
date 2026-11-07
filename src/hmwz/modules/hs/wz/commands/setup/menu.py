from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.components.entity_selection import EntitySelectionView
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import (
    send_interaction_response,
    send_temporary_followup,
)
from hmwz.utils.interactions import log_interaction
from hmwz.modules.hs.wz.module import WzModule

from ...models import Channel, Role
from .role.operations import RoleSetupOperations

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WzSetupDraft:
    """Keep WZ role and cleanup-channel changes until explicit save."""

    module: WzModule
    original_role_ids: set[int]
    original_channel_ids: set[int]
    role_ids: set[int]
    channel_ids: set[int]

    @classmethod
    async def load(cls, module: WzModule) -> WzSetupDraft:
        roles = await module.roles.get(guild=module.guild)
        channels = await module.channels.get(guild=module.guild)
        role_ids = {record.role for record in roles or ()}
        channel_ids = {record.channel_id for record in channels or ()}
        return cls(
            module=module,
            original_role_ids=role_ids.copy(),
            original_channel_ids=channel_ids.copy(),
            role_ids=role_ids.copy(),
            channel_ids=channel_ids.copy(),
        )


async def configuration_embed(
    module: WzModule,
    context: discord.Interaction,
    draft: WzSetupDraft | None = None,
) -> discord.Embed:
    """Present guild-wide WZ settings in clearly separated, bounded fields."""
    if draft is None:
        roles = await module.roles.get(guild=module.guild) or ()
        channels = await module.channels.get(guild=module.guild) or ()
        role_ids = [record.role for record in roles]
        channel_ids = [record.channel_id for record in channels]
    else:
        role_ids = sorted(draft.role_ids)
        channel_ids = sorted(draft.channel_ids)
    embed = create_embed(
        title=t(context, "wz.setup.menu.title"),
        description=t(
            context,
            "wz.setup.menu.summary",
            role_count=len(role_ids),
            max_roles=Role.MAX_PER_GUILD,
            channel_count=len(channel_ids),
            max_channels=Channel.MAX_PER_GUILD,
        ),
    )
    if draft is not None:
        embed.description += "\n" + t(context, "wz.setup.menu.pending")
    names = [f"<@&{role_id}>" for role_id in role_ids]
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
    channel_names = [f"<#{channel_id}>" for channel_id in channel_ids]
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


class WzSetupSelectionView(EntitySelectionView):
    """Stage selected WZ roles or channels without writing to storage."""

    def __init__(
        self,
        menu: WzSetupMenu,
        *,
        kind: Literal["role", "channel"],
        action: Literal["add", "remove"],
        entities: list[discord.Role] | list[discord.TextChannel],
        max_selected: int,
        context: discord.Interaction,
    ) -> None:
        self.menu = menu
        self.action = action
        self.entities = entities
        label = "wz.setup.menu.roles" if kind == "role" else "wz.setup.menu.channels"
        super().__init__(
            owner_id=menu.owner_id,
            kind=kind,
            allowed_ids=(entity.id for entity in entities),
            max_selected=max_selected,
            placeholder=t(
                context, "wz.setup.menu.select_placeholder", entity=t(context, label)
            ),
            owner_message=t(context, "wz.setup.menu.owner"),
            invalid_message=t(context, "wz.setup.menu.selection_invalid"),
            options=[
                discord.SelectOption(
                    label=entity.name[:100],
                    value=str(entity.id),
                )
                for entity in entities
            ],
        )
        self.message = menu.message
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "wz_setup_stage":
                    item.label = t(context, "wz.setup.menu.stage")
                    item.emoji = "➕" if action == "add" else "➖"
                elif item.custom_id == "wz_setup_selection_cancel":
                    item.label = t(context, "wz.setup.menu.back")
                    item.emoji = "↩️"

    def selection_embed(self, context: discord.Interaction) -> discord.Embed:
        """Preview the selected entities before changing the draft."""
        selected = [
            entity for entity in self.entities if entity.id in self.selected_ids
        ]
        embed = create_embed(
            title=t(
                context,
                "wz.setup.menu.selection_title",
                action=t(
                    context,
                    "wz.setup.menu.add_action"
                    if self.action == "add"
                    else "wz.setup.menu.remove_action",
                ),
            ),
            description=t(
                context,
                "wz.setup.menu.selection_count",
                selected=len(self.selected_ids),
                maximum=self.max_selected,
            ),
        )
        embed.add_field(
            name=t(context, "wz.setup.selection.preview"),
            value="\n".join(entity.mention for entity in selected)
            or t(context, "wz.setup.selection.empty"),
            inline=False,
        )
        return embed

    async def on_selection_changed(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=self.selection_embed(interaction),
            view=self,
        )

    @discord.ui.button(
        label="Stage",
        style=discord.ButtonStyle.primary,
        custom_id="wz_setup_stage",
        emoji="➕",
        row=1,
    )
    async def stage(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not self.selected_ids:
            await self.send_temporary_response(
                interaction, t(interaction, "wz.setup.menu.selection_invalid")
            )
            return
        target = (
            self.menu.draft.role_ids
            if self.kind == "role"
            else self.menu.draft.channel_ids
        )
        if self.action == "add":
            target.update(self.selected_ids)
        else:
            target.difference_update(self.selected_ids)
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=await configuration_embed(
                self.menu.draft.module, interaction, self.menu.draft
            ),
            view=self.menu,
        )

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_setup_selection_cancel",
        emoji="↩️",
        row=1,
    )
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=await configuration_embed(
                self.menu.draft.module, interaction, self.menu.draft
            ),
            view=self.menu,
        )


class WzSetupMenu(EphemeralView):
    def __init__(
        self,
        *,
        owner_id: int,
        context: discord.Interaction,
        draft: WzSetupDraft,
    ) -> None:
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.draft = draft
        labels = {
            "wz_setup_add_channel": "wz.setup.menu.add_channel",
            "wz_setup_remove_channel": "wz.setup.menu.remove_channel",
            "wz_setup_add_role": "wz.setup.menu.add_role",
            "wz_setup_remove_role": "wz.setup.menu.remove_role",
            "wz_setup_save": "wz.setup.menu.save",
            "wz_setup_cancel": "wz.setup.menu.cancel",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in labels:
                item.label = t(context, labels[item.custom_id])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "wz.setup.menu.owner")
        )
        return False

    async def open_selection(
        self,
        interaction: discord.Interaction,
        *,
        kind: Literal["role", "channel"],
        action: Literal["add", "remove"],
    ) -> None:
        guild = self.draft.module.guild
        if kind == "channel":
            if action == "add":
                configured_count = len(self.draft.channel_ids)
                entities: list[discord.Role] | list[discord.TextChannel] = [
                    channel
                    for channel in guild.text_channels
                    if channel.id not in self.draft.channel_ids
                    and guild.me is not None
                    and channel.permissions_for(guild.me).view_channel
                ]
                maximum = Channel.MAX_PER_GUILD - configured_count
            else:
                entities = [
                    channel
                    for channel_id in sorted(self.draft.channel_ids)
                    if isinstance(
                        channel := guild.get_channel(channel_id), discord.TextChannel
                    )
                ]
                maximum = len(entities)
            no_options_key = (
                "wz.setup.channel.no_available_channels"
                if action == "add"
                else "wz.setup.channel.selection_no_changes"
            )
        else:
            if action == "add":
                entities = [
                    role
                    for role in guild.roles
                    if role.id not in self.draft.role_ids
                    and not role.is_default()
                    and not role.managed
                    and (guild.me is None or role < guild.me.top_role)
                ]
                maximum = Role.MAX_PER_GUILD - len(self.draft.role_ids)
            else:
                entities = [
                    role
                    for role_id in sorted(self.draft.role_ids)
                    if (role := guild.get_role(role_id)) is not None
                ]
                maximum = len(entities)
            no_options_key = (
                "wz.setup.role.no_available_roles"
                if action == "add"
                else "wz.setup.role.selection_no_changes"
            )
        if not entities or maximum <= 0:
            await self.send_temporary_response(
                interaction, t(interaction, no_options_key)
            )
            return
        selection = WzSetupSelectionView(
            self,
            kind=kind,
            action=action,
            entities=entities,
            max_selected=min(maximum, len(entities), 25),
            context=interaction,
        )
        selection.message = interaction.message
        await interaction.response.edit_message(
            content=None,
            embed=selection.selection_embed(interaction),
            view=selection,
        )

    @discord.ui.button(
        label="Add role",
        style=discord.ButtonStyle.primary,
        custom_id="wz_setup_add_role",
        emoji="➕",
        row=0,
    )
    async def add_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.open_selection(interaction, kind="role", action="add")

    @discord.ui.button(
        label="Remove role",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_setup_remove_role",
        emoji="➖",
        row=0,
    )
    async def remove_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.open_selection(interaction, kind="role", action="remove")

    @discord.ui.button(
        label="Add channel",
        style=discord.ButtonStyle.primary,
        custom_id="wz_setup_add_channel",
        emoji="➕",
        row=1,
    )
    async def add_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.open_selection(interaction, kind="channel", action="add")

    @discord.ui.button(
        label="Remove channel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_setup_remove_channel",
        emoji="➖",
        row=1,
    )
    async def remove_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.open_selection(interaction, kind="channel", action="remove")

    @discord.ui.button(
        label="Save",
        style=discord.ButtonStyle.success,
        custom_id="wz_setup_save",
        emoji="✅",
        row=2,
    )
    async def save_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.save(interaction)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_setup_cancel",
        emoji="❌",
        row=2,
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.defer()
        await interaction.delete_original_response()

    async def save(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        module = self.draft.module
        current = await WzSetupDraft.load(module)
        if (
            current.role_ids != self.draft.original_role_ids
            or current.channel_ids != self.draft.original_channel_ids
        ):
            self.draft = current
            await interaction.edit_original_response(
                content=t(interaction, "wz.setup.menu.stale"),
                embed=await configuration_embed(module, interaction, self.draft),
                view=self,
            )
            return

        for role_id in sorted(self.draft.role_ids - self.draft.original_role_ids):
            role = module.guild.get_role(role_id)
            if (
                role is None
                or role.is_default()
                or role.managed
                or (module.guild.me is not None and role >= module.guild.me.top_role)
                or not await module.roles.add(guild=module.guild, role=role_id)
            ):
                await self._report_save_error(interaction)
                return

        for channel_id in sorted(
            self.draft.channel_ids - self.draft.original_channel_ids
        ):
            if not await module.channels.add(guild=module.guild, channel_id=channel_id):
                await self._report_save_error(interaction)
                return

        for channel_id in sorted(
            self.draft.original_channel_ids - self.draft.channel_ids
        ):
            if not await module.channels.remove(
                guild=module.guild, channel_id=channel_id
            ):
                await self._report_save_error(interaction)
                return

        removed_role_ids = sorted(self.draft.original_role_ids - self.draft.role_ids)
        if removed_role_ids:
            await RoleSetupOperations(guild=module.guild, module=module).remove(
                interaction, removed_role_ids
            )

        saved = await WzSetupDraft.load(module)
        if (
            saved.role_ids != self.draft.role_ids
            or saved.channel_ids != self.draft.channel_ids
        ):
            await self._report_save_error(interaction)
            return
        self.stop()
        await interaction.delete_original_response()
        await send_temporary_followup(
            interaction, t(interaction, "wz.setup.menu.saved")
        )

    async def _report_save_error(self, interaction: discord.Interaction) -> None:
        self.draft = await WzSetupDraft.load(self.draft.module)
        await interaction.edit_original_response(
            content=t(interaction, "wz.setup.menu.save_error"),
            embed=await configuration_embed(self.draft.module, interaction, self.draft),
            view=self,
        )


@app_commands.command(
    name="setup",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup", "Configure WZ channels and roles"
        ),
        key="wz.setup.description",
    ),
)
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
async def setup(interaction: discord.Interaction) -> None:
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            content = t(interaction, "wz.setup.menu.error")
        else:
            module: WzModule = await manager.get_module(guild, WzModule)
            draft = await WzSetupDraft.load(module)
            view = WzSetupMenu(
                owner_id=interaction.user.id,
                context=interaction,
                draft=draft,
            )
            view.message = await send_interaction_response(
                interaction,
                embed=await configuration_embed(module, interaction, draft),
                view=view,
                ephemeral=True,
            )
            return
    except Exception:
        _logger.exception(
            "%s WZ setup configuration failed.", log_interaction(interaction)
        )
        content = t(interaction, "wz.setup.menu.error")
    if interaction.response.is_done():
        await send_temporary_followup(interaction, content)
    else:
        await send_interaction_response(interaction, content, ephemeral=True)
