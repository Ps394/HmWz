from __future__ import annotations

import logging

import discord

from hmwz.i18n import t
from hmwz.ui.components.entity_selection import EntitySelectionView
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import edit_interaction_response
from hmwz.utils.interactions import log_interaction
from hmwz.modules.hs.wz.module import WzModule

from .components import SetupRoleConfirmation
from .operations import RoleAction, RoleSetupOperations

_logger = logging.getLogger(__name__)


class SetupRoleSelection(EntitySelectionView):
    """Preview WZ role selections before confirmation."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        module: WzModule,
        owner_id: int,
        action: RoleAction,
        roles: list[discord.Role],
        max_selected: int,
        context: discord.Interaction,
    ) -> None:
        super().__init__(
            owner_id=owner_id,
            kind="role",
            allowed_ids=(role.id for role in roles),
            max_selected=min(max_selected, 25),
            placeholder=t(context, f"wz.setup.role.select.{action}"),
            owner_message=t(context, "wz.setup.role.selection_owner"),
            invalid_message=t(context, "wz.setup.role.invalid_selection"),
            options=[
                discord.SelectOption(label=role.name[:100], value=str(role.id))
                for role in roles
            ]
            if action == "remove"
            else None,
        )
        self.guild = guild
        self.module = module
        self.owner_id = owner_id
        self.action = action
        self.roles = roles
        labels = {
            "wz_role_select_review": "wz.setup.role.review",
            "wz_role_select_cancel": "wz.setup.role.cancel_button",
        }
        for item in list(self.children):
            if not isinstance(item, discord.ui.Button) or item.custom_id not in labels:
                continue
            item.label = t(context, labels[item.custom_id])
            item.disabled = item.custom_id != "wz_role_select_cancel"

    def selection_embed(self, context: discord.Interaction) -> discord.Embed:
        """Show the selected roles, limit, and next step."""
        embed = create_embed(
            title=t(context, f"wz.setup.role.title.{self.action}"),
            description=t(
                context,
                "wz.setup.role.selection_count",
                selected=len(self.selected_ids),
                maximum=self.max_selected,
            )
            + "\n"
            + t(context, f"wz.setup.role.selection_rules.{self.action}"),
        )
        embed.add_field(
            name=t(context, "wz.setup.selection.preview"),
            value="\n".join(f"<@&{role_id}>" for role_id in sorted(self.selected_ids))
            or t(context, "wz.setup.selection.empty"),
            inline=False,
        )
        return embed

    async def on_selection_changed(self, interaction: discord.Interaction) -> None:
        """Enable role actions once a valid selection is present."""
        for item in self.children:
            if (
                isinstance(item, discord.ui.Button)
                and item.custom_id == "wz_role_select_review"
            ):
                item.disabled = not self.selected_ids
        await edit_interaction_response(
            interaction,
            content=None,
            embed=self.selection_embed(interaction),
            view=self,
        )

    @discord.ui.button(
        label="Review",
        style=discord.ButtonStyle.primary,
        custom_id="wz_role_select_review",
        row=1,
    )
    async def review_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.review(interaction)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_role_select_cancel",
        row=1,
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.finish(interaction, t(interaction, "wz.setup.role.cancelled"))

    async def review(self, interaction: discord.Interaction) -> None:
        selected = [
            self.guild.get_role(role_id) for role_id in sorted(self.selected_ids)
        ]
        selected_roles = [role for role in selected if role is not None]
        if not selected_roles:
            await self.finish(
                interaction, t(interaction, "wz.setup.role.selection_no_changes")
            )
            return
        action_label = (
            "wz.setup.role.confirmation.add"
            if self.action == "add"
            else "wz.setup.role.confirmation.remove"
        )
        role_names = [role.mention for role in selected_roles[:60]]
        if len(selected_roles) > len(role_names):
            role_names.append(
                t(
                    interaction,
                    "wz.setup.role.more_roles",
                    count=len(selected_roles) - len(role_names),
                )
            )
        confirmation = SetupRoleConfirmation(
            selection=self,
            owner_id=self.owner_id,
            selected_role_ids=[role.id for role in selected_roles],
            context=interaction,
        )
        confirmation.message = interaction.message
        self.stop()
        await edit_interaction_response(
            interaction,
            content=t(
                interaction,
                action_label,
                role_names="\n".join(role_names),
            ),
            embed=None,
            view=confirmation,
        )

    async def commit(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> None:
        await interaction.response.defer()
        try:
            if self.action == "add":
                content = await self._add_roles(interaction, selected_role_ids)
            else:
                content = await self._remove_roles(interaction, selected_role_ids)
        except Exception:
            _logger.exception(
                "%s WZ setup role selection failed.",
                log_interaction(interaction),
            )
            content = t(interaction, "wz.setup.role.error")
        self.stop()
        await self.finish(interaction, content)

    async def _add_roles(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> str:
        operations = self._operations()
        return await operations.add(interaction, selected_role_ids)

    async def _remove_roles(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> str:
        operations = self._operations()
        return await operations.remove(interaction, selected_role_ids)

    def _operations(self) -> RoleSetupOperations:
        return RoleSetupOperations(
            guild=self.guild,
            module=self.module,
        )
