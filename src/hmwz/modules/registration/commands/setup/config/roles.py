"""Role add/remove views for registration setup."""

from __future__ import annotations

import discord

from hmwz.configuration import registration_defaults
from hmwz.i18n import t
from hmwz.ui.messages import send_initial_response, send_temporary_followup

from .configuration_message import configuration_message
from .draft import RegistrationSetupDraft
from .view import RegistrationSetupView


class RegistrationRoleSelect(discord.ui.RoleSelect):
    """Forward a selected role to the role setup view."""

    def __init__(self, role_view: RegistrationRoleView) -> None:
        super().__init__(
            placeholder=t(
                role_view.guild,
                "registration.setup.config.role_select_prompt",
            ),
            min_values=1,
            max_values=1,
        )
        self.role_view = role_view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.role_view.on_role_select(interaction, self)


class RegistrationRoleView(RegistrationSetupView):
    """Select one role and choose permanence."""

    def __init__(self, draft: RegistrationSetupDraft) -> None:
        super().__init__(owner_id=draft.owner_id, timeout=180)
        self.draft = draft
        self.module = draft.module
        self.guild = draft.module.guild
        self.channel_id = draft.channel_id
        self.selected_role: discord.Role | None = None
        self.role_select = RegistrationRoleSelect(self)
        self.add_item(self.role_select)

    async def on_role_select(
        self,
        interaction: discord.Interaction,
        select: RegistrationRoleSelect,
    ) -> None:
        if not select.values:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.role_select"),
                ephemeral=True,
                delete_after=5,
            )
            return
        self.selected_role = select.values[0]
        await interaction.response.edit_message(view=self)

    async def _save_role(
        self, interaction: discord.Interaction, permanent: bool
    ) -> None:
        await interaction.response.defer()
        role = self.selected_role
        if role is None:
            await send_temporary_followup(
                interaction,
                t(interaction, "registration.setup.config.role_select"),
                ephemeral=True,
            )
            return
        if (
            role.is_default()
            or role.managed
            or (self.guild.me is not None and role >= self.guild.me.top_role)
        ):
            await send_temporary_followup(
                interaction,
                t(interaction, "registration.setup.config.role_hierarchy_error"),
                ephemeral=True,
            )
            return
        configured_ids = set(self.draft.roles)
        max_roles = int(
            registration_defaults(self.module.module_key).get(
                "max_registration_roles",
                4,
            )
        )
        if role.id not in configured_ids and len(configured_ids) >= max_roles:
            await send_temporary_followup(
                interaction,
                t(
                    interaction,
                    "registration.setup.config.max_roles",
                    max_roles=max_roles,
                ),
                ephemeral=True,
            )
            return
        self.draft.roles[role.id] = permanent
        from .main import RegistrationConfigView

        await interaction.edit_original_response(
            embed=await configuration_message(
                self.module,
                interaction,
                self.channel_id,
                self.draft,
            ),
            content=None,
            view=RegistrationConfigView(self.draft),
        )

    @discord.ui.button(
        label="Permanent",
        style=discord.ButtonStyle.primary,
        custom_id="wz_registration_config_role_permanent",
        emoji="🔒",
    )
    async def permanent(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        del button
        await self._save_role(interaction, permanent=True)

    @discord.ui.button(
        label="Nicht permanent",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_role_temporary",
        emoji="🔓",
    )
    async def temporary(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        del button
        await self._save_role(interaction, permanent=False)

    @discord.ui.button(
        label="Zurück",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_role_back",
        emoji="↩️",
    )
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        del button
        from .main import RegistrationConfigView

        await interaction.response.edit_message(
            embed=await configuration_message(
                self.module,
                interaction,
                self.channel_id,
                self.draft,
            ),
            content=None,
            view=RegistrationConfigView(self.draft),
        )


class RegistrationRoleRemovalSelect(discord.ui.Select):
    """Select configured roles for removal."""

    def __init__(
        self,
        removal_view: RegistrationRoleRemovalView,
        configured_roles: list[tuple[int, str, bool]],
    ) -> None:
        super().__init__(
            placeholder=t(
                removal_view.guild,
                "registration.setup.config.remove_role_select",
            ),
            min_values=1,
            max_values=len(configured_roles),
            options=[
                discord.SelectOption(
                    label=role_name[:100],
                    value=str(role_id),
                )
                for role_id, role_name, _permanent in configured_roles
            ],
        )
        self.removal_view = removal_view

    async def callback(self, interaction: discord.Interaction) -> None:
        for item in self.removal_view.children:
            if (
                isinstance(item, discord.ui.Button)
                and item.custom_id == "wz_registration_config_role_remove_confirm"
            ):
                item.disabled = False
        await interaction.response.edit_message(view=self.removal_view)


class RegistrationRoleRemovalView(RegistrationSetupView):
    """Choose configured roles to remove."""

    def __init__(
        self,
        draft: RegistrationSetupDraft,
        configured_roles: list[tuple[int, str, bool]],
    ) -> None:
        super().__init__(owner_id=draft.owner_id, timeout=180)
        self.draft = draft
        self.module = draft.module
        self.guild = draft.module.guild
        self.channel_id = draft.channel_id
        self.role_select = RegistrationRoleRemovalSelect(self, configured_roles)
        self.add_item(self.role_select)

    @discord.ui.button(
        label="Rollen entfernen",
        style=discord.ButtonStyle.danger,
        custom_id="wz_registration_config_role_remove_confirm",
    )
    async def confirm_remove(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        del button
        selected_role_ids = [int(value) for value in self.role_select.values]
        if not selected_role_ids:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.remove_role_select"),
                ephemeral=True,
                delete_after=5,
            )
            return
        configured_ids = set(self.draft.roles)
        min_roles = int(
            registration_defaults(self.module.module_key).get(
                "min_registration_roles",
                1,
            )
        )
        if not set(selected_role_ids).issubset(configured_ids):
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.remove_role_stale"),
                ephemeral=True,
                delete_after=5,
            )
            return
        if len(configured_ids) - len(selected_role_ids) < min_roles:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.remove_role_minimum"),
                ephemeral=True,
                delete_after=5,
            )
            return
        await interaction.response.defer()
        for role_id in selected_role_ids:
            self.draft.roles.pop(role_id, None)
        from .main import RegistrationConfigView

        await interaction.edit_original_response(
            content=None,
            embed=await configuration_message(
                self.module,
                interaction,
                self.channel_id,
                self.draft,
            ),
            view=RegistrationConfigView(self.draft),
        )

    @discord.ui.button(
        label="Zurück",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_role_remove_back",
    )
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        del button
        from .main import RegistrationConfigView

        await interaction.response.edit_message(
            content=None,
            embed=await configuration_message(
                self.module,
                interaction,
                self.channel_id,
                self.draft,
            ),
            view=RegistrationConfigView(self.draft),
        )
