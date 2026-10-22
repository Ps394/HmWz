from __future__ import annotations

import logging
from typing import Literal

import discord

from hmwz import utils
from hmwz.configuration import wz_registration_config
from hmwz.i18n import t
from hmwz.modules.hs.wz.module import WzRegistrationModule

logger = logging.getLogger(__name__)
RoleAction = Literal["add", "remove"]


class SetupRoleSelection(discord.ui.View):
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
        await interaction.response.send_message(
            t(interaction, "wz.setup.role.selection_owner"), ephemeral=True
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
            await interaction.response.edit_message(
                content=t(interaction, "wz.setup.role.selection_no_changes"),
                view=None,
            )
            self.stop()
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
            view=SetupRoleConfirmation(
                selection=self,
                owner_id=self.owner_id,
                selected_role_ids=[role.id for role in selected_roles],
                context=interaction,
            ),
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
        await interaction.edit_original_response(content=content, view=None)

    async def _add_roles(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> str:
        configured = await self.module.roles.get(
            guild=self.guild, channel_id=self.channel_id
        )
        configured_ids = {record.role for record in configured or ()}
        configured_anywhere = await self.module.roles.get(guild=self.guild)
        configured_global_ids = {record.role for record in configured_anywhere or ()}
        max_roles = int(wz_registration_config().get("max_registration_roles", 4))
        added: list[str] = []
        failed: list[str] = []
        for role_id in selected_role_ids:
            role = self.guild.get_role(role_id)
            if (
                role is None
                or role.id in configured_global_ids
                or role.is_default()
                or role.managed
                or (self.guild.me is not None and role >= self.guild.me.top_role)
                or len(configured_ids) >= max_roles
            ):
                failed.append(f"<@&{role_id}>")
                continue
            if await self.module.roles.add(
                guild=self.guild,
                role=role.id,
                permanent=self.permanent,
                score=1,
                channel_id=self.channel_id,
            ):
                configured_ids.add(role.id)
                added.append(role.mention)
            else:
                failed.append(role.mention)

        if added and not await self.module.compose_registration_overview(
            force=True, channel_id=self.channel_id
        ):
            return t(
                interaction,
                "wz.setup.role.add.overview_failed",
                role_names=", ".join(added),
            )
        return self._result_message(interaction, "add", added, failed)

    async def _remove_roles(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> str:
        configured = await self.module.roles.get(
            guild=self.guild, channel_id=self.channel_id
        )
        configured_ids = {record.role for record in configured or ()}
        min_roles = int(wz_registration_config().get("min_registration_roles", 1))
        selected = [
            role_id for role_id in selected_role_ids if role_id in configured_ids
        ]
        if len(configured_ids) - len(selected) < min_roles:
            return t(interaction, "wz.setup.role.min_roles")
        if not selected:
            return t(interaction, "wz.setup.role.selection_no_changes")

        roles = [
            role
            for role_id in selected
            if (role := self.guild.get_role(role_id)) is not None
        ]
        failed_members: set[int] = set()
        member_fetch_failed = False
        try:
            async for member in self.guild.fetch_members(limit=None):
                held_roles = [role for role in roles if role in member.roles]
                if not held_roles:
                    continue
                try:
                    await member.remove_roles(
                        *held_roles, reason="WZ Setup Role Removal"
                    )
                except discord.HTTPException:
                    failed_members.add(member.id)
                    logger.exception(
                        "Failed to remove WZ roles %s from member %s in guild %s.",
                        [role.id for role in held_roles],
                        member.id,
                        self.guild.id,
                    )
        except discord.HTTPException:
            member_fetch_failed = True
            logger.exception(
                "Failed to fetch guild members while removing WZ roles in guild %s.",
                self.guild.id,
            )
        if member_fetch_failed:
            return t(
                interaction,
                "wz.setup.role.member_fetch_failed",
                count=len(failed_members),
            )
        removed_roles = await self.module.roles.remove(
            guild=self.guild, roles=selected, channel_id=self.channel_id
        )
        removed_registrations = await self.module.registrations.remove(
            guild=self.guild, roles=selected, channel_id=self.channel_id
        )
        if not removed_roles or not removed_registrations:
            return t(interaction, "wz.setup.role.error")
        if not await self.module.compose_registration_overview(
            force=True, channel_id=self.channel_id
        ):
            return t(
                interaction,
                "wz.setup.role.remove.overview_failed",
                role_names=", ".join(f"<@&{role_id}>" for role_id in selected),
            )
        result = self._result_message(
            interaction,
            "remove",
            [role.mention for role in roles],
            [],
        )
        if failed_members:
            result += "\n" + t(
                interaction,
                "wz.setup.role.member_removal_failed",
                count=len(failed_members),
            )
        return result

    def _result_message(
        self,
        interaction: discord.Interaction,
        action: RoleAction,
        completed: list[str],
        failed: list[str],
    ) -> str:
        messages = []
        if completed:
            messages.append(
                t(
                    interaction,
                    f"wz.setup.role.{action}.success",
                    role_names=", ".join(completed),
                )
            )
        if failed:
            messages.append(
                t(
                    interaction,
                    "wz.setup.role.operation_failed",
                    role_names=", ".join(failed),
                )
            )
        return "\n".join(messages) or t(
            interaction, "wz.setup.role.selection_no_changes"
        )


class _RoleSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        view: SetupRoleSelection,
        roles: list[discord.Role],
        max_values: int,
        selected_ids: set[int],
        context: discord.Interaction,
    ) -> None:
        super().__init__(
            placeholder=t(
                context,
                "wz.setup.role.select.add"
                if view.action == "add"
                else "wz.setup.role.select.remove",
            ),
            min_values=0,
            max_values=max(1, max_values),
            options=[
                discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    default=role.id in selected_ids,
                )
                for role in roles
            ],
        )
        self.selection = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selection.select_roles(
            interaction, [int(role_id) for role_id in self.values]
        )


class _PageButton(discord.ui.Button):
    def __init__(self, *, view: SetupRoleSelection, label: str, direction: int) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.selection = view
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selection.change_page(interaction, self.direction)


class _ReviewButton(discord.ui.Button):
    def __init__(self, *, view: SetupRoleSelection, label: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.selection = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selection.review(interaction)


class SetupRoleConfirmation(discord.ui.View):
    def __init__(
        self,
        *,
        selection: SetupRoleSelection,
        owner_id: int,
        selected_role_ids: list[int],
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=180)
        self.selection = selection
        self.owner_id = owner_id
        self.selected_role_ids = selected_role_ids
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    context,
                    "wz.setup.role.confirm_button"
                    if item.custom_id == "wz_role_confirm"
                    else "wz.setup.role.cancel_button",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "wz.setup.role.selection_owner"), ephemeral=True
        )
        return False

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.primary,
        custom_id="wz_role_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await self.selection.commit(interaction, self.selected_role_ids)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_role_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        self.selection.stop()
        self.stop()
        await interaction.response.edit_message(
            content=t(interaction, "wz.setup.role.cancelled"), view=None
        )
