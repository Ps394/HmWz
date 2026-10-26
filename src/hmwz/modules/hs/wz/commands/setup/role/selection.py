from __future__ import annotations

import logging

import discord

from hmwz import utils
from hmwz.i18n import t
from hmwz.ui import EphemeralView
from hmwz.modules.hs.wz.module import WzRegistrationModule

from .components import (
    SetupRoleConfirmation,
    _PageButton,
    _ReviewButton,
    _RoleSelect,
)
from .operations import RoleAction, RoleSetupOperations

logger = logging.getLogger(__name__)


class SetupRoleSelection(EphemeralView):
    def __init__(
        self,
        *,
        guild: discord.Guild,
        module: WzRegistrationModule,
        owner_id: int,
        action: RoleAction,
        channel_id: int,
        roles: list[discord.Role],
        max_selected: int,
        permanent: bool,
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=180)
        self.guild = guild
        self.module = module
        self.owner_id = owner_id
        self.action = action
        self.channel_id = channel_id
        self.roles = roles
        self.max_selected = max_selected
        self.permanent = permanent
        self.page = 0
        self.selected_role_ids: set[int] = set()
        self._update_components(context)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "wz.setup.role.selection_owner")
        )
        return False

    def _update_components(self, context: discord.Interaction) -> None:
        self.clear_items()
        start = self.page * 25
        page_roles = self.roles[start : start + 25]
        page_role_ids = {role.id for role in page_roles}
        selected_on_page = self.selected_role_ids & page_role_ids
        remaining = self.max_selected - len(self.selected_role_ids - page_role_ids)
        select = _RoleSelect(
            view=self,
            roles=page_roles,
            max_values=min(len(page_roles), remaining),
            selected_ids=selected_on_page,
            context=context,
        )
        select.disabled = remaining <= 0
        self.add_item(select)
        if self.page > 0:
            self.add_item(
                _PageButton(
                    view=self,
                    label=t(context, "wz.setup.role.previous_page"),
                    direction=-1,
                )
            )
        if start + 25 < len(self.roles):
            self.add_item(
                _PageButton(
                    view=self,
                    label=t(context, "wz.setup.role.next_page"),
                    direction=1,
                )
            )
        review = _ReviewButton(
            view=self,
            label=t(context, "wz.setup.role.review"),
        )
        review.disabled = not self.selected_role_ids
        self.add_item(review)

    async def select_roles(
        self, interaction: discord.Interaction, selected_ids: list[int]
    ) -> None:
        page_role_ids = {
            role.id for role in self.roles[self.page * 25 : self.page * 25 + 25]
        }
        self.selected_role_ids.difference_update(page_role_ids)
        self.selected_role_ids.update(selected_ids)
        self._update_components(interaction)
        await interaction.response.edit_message(
            content=t(
                interaction,
                "wz.setup.role.selection_count",
                selected=len(self.selected_role_ids),
                maximum=self.max_selected,
            ),
            view=self,
        )

    async def change_page(
        self, interaction: discord.Interaction, direction: int
    ) -> None:
        self.page += direction
        self._update_components(interaction)
        await interaction.response.edit_message(
            content=t(
                interaction,
                "wz.setup.role.select.add"
                if self.action == "add"
                else "wz.setup.role.select.remove",
            ),
            view=self,
        )

    async def review(self, interaction: discord.Interaction) -> None:
        selected = [
            self.guild.get_role(role_id) for role_id in sorted(self.selected_role_ids)
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
        await interaction.response.edit_message(
            content=t(
                interaction,
                action_label,
                role_names="\n".join(role_names),
                permanent=t(
                    interaction,
                    "wz.setup.role.permanent_yes"
                    if self.permanent
                    else "wz.setup.role.permanent_no",
                ),
            ),
            view=confirmation,
        )

    async def commit(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> None:
        await interaction.response.defer()
        try:
            registration = await self.module.registration.get(
                guild=self.guild, channel_id=self.channel_id
            )
            if registration is None:
                content = t(interaction, "wz.setup.role.registration_required")
            elif self.action == "add":
                content = await self._add_roles(interaction, selected_role_ids)
            else:
                content = await self._remove_roles(interaction, selected_role_ids)
        except Exception:
            logger.exception(
                "%s WZ setup role selection failed.",
                utils.log_interaction(interaction),
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
            channel_id=self.channel_id,
            permanent=self.permanent,
        )
