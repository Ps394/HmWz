from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t

if TYPE_CHECKING:
    from .selection import SetupRoleSelection


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
