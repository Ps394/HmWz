"""Interactive controls for configuring registration channels and roles."""

from __future__ import annotations

import logging

import discord

from hmwz.ui.messages import send_initial_response, send_followup
from hmwz.configuration import registration_defaults
from hmwz.i18n import t
from hmwz.ui.messages import send_temporary_followup
from hmwz.utils.loaders import fetch_member

from .configuration_message import configuration_message
from .draft import RegistrationSetupDraft
from .view import RegistrationSetupView

_configuration_message = configuration_message
_logger = logging.getLogger(__name__)


class RegistrationConfigView(RegistrationSetupView):
    """Private control panel for one registration channel."""

    def __init__(
        self,
        draft: RegistrationSetupDraft,
    ) -> None:
        super().__init__(owner_id=draft.owner_id, timeout=300)
        self.draft = draft
        self.module = draft.module
        self.guild = draft.module.guild
        self.channel_id = draft.channel_id
        labels = {
            "wz_registration_config_title": "registration.setup.config.edit_title",
            "wz_registration_config_text": "registration.setup.config.edit_text",
            "wz_registration_config_lock_emojis": (
                "registration.setup.config.toggle_lock_emojis"
            ),
            "wz_registration_config_add_role": "registration.setup.config.add_role",
            "wz_registration_config_remove_role": "registration.setup.config.remove_role",
            "wz_registration_config_export_channel": ("registration.setup.config.edit_export_channel"),
            "wz_registration_config_apply": "registration.setup.config.save",
            "wz_registration_config_cancel": "registration.setup.config.cancel",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in labels:
                item.label = t(self.guild, labels[item.custom_id])

    @discord.ui.button(
        label="Titel bearbeiten",
        style=discord.ButtonStyle.primary,
        custom_id="wz_registration_config_title",
        emoji="📝",
        row=0,
    )
    async def edit_title(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Open a modal to edit the registration overview title.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        await interaction.response.send_modal(
            RegistrationTitleModal(
                self.draft,
            )
        )

    @discord.ui.button(
        label="Text bearbeiten",
        style=discord.ButtonStyle.primary,
        custom_id="wz_registration_config_text",
        emoji="💬",
        row=0,
    )
    async def edit_text(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Open a modal to edit the registration overview description.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        await interaction.response.send_modal(
            RegistrationTextModal(
                self.draft,
            )
        )

    @discord.ui.button(
        label="Schlossemojis umschalten",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_lock_emojis",
        emoji="🔐",
        row=0,
    )
    async def toggle_lock_emojis(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Toggle lock emoji visibility in the registration overview."""
        self.draft.show_lock_emojis = not self.draft.show_lock_emojis
        await interaction.response.edit_message(
            embed=await configuration_message(
                self.module, interaction, self.channel_id, self.draft
            ),
            content=None,
            view=RegistrationConfigView(self.draft),
        )

    @discord.ui.button(
        label="Rolle hinzufügen",
        style=discord.ButtonStyle.success,
        custom_id="wz_registration_config_add_role",
        emoji="➕",
        row=1,
    )
    async def add_role(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Open the role selection view.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        await interaction.response.edit_message(
            content=t(interaction, "registration.setup.config.role_prompt"),
            embed=None,
            view=RegistrationRoleView(self.draft),
        )

    @discord.ui.button(
        label="Rolle entfernen",
        style=discord.ButtonStyle.danger,
        custom_id="wz_registration_config_remove_role",
        emoji="➖",
        row=1,
    )
    async def remove_role(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Open the role removal view for the current channel.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        if not self.draft.roles:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.no_roles_to_remove"),
                ephemeral=True,
                delete_after=5,
            )
            return
        roles = [
            (
                role_id,
                (
                    role.name
                    if (role := self.guild.get_role(role_id)) is not None
                    else str(role_id)
                ),
                permanent,
            )
            for role_id, permanent in self.draft.roles.items()
        ]
        if not roles:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.no_roles_to_remove"),
                ephemeral=True,
                delete_after=5,
            )
            return
        await interaction.response.edit_message(
            content=t(interaction, "registration.setup.config.remove_role_prompt"),
            embed=None,
            view=RegistrationRoleRemovalView(self.draft, roles),
        )

    @discord.ui.button(
        label="JSON-Exportkanal",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_export_channel",
        emoji="📤",
        row=1,
    )
    async def configure_export_channel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Open the view for configuring the snapshot destination channel.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        await interaction.response.edit_message(
            content=t(interaction, "registration.setup.config.export_channel_prompt"),
            embed=None,
            view=RegistrationExportChannelView(self.draft),
        )

    @discord.ui.button(
        label="Übernehmen",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="wz_registration_config_apply",
        row=2,
    )
    async def apply(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Persist the complete draft and close the setup panel."""
        await self.save(interaction)

    @discord.ui.button(
        label="Abbrechen",
        style=discord.ButtonStyle.secondary,
        emoji="❌",
        custom_id="wz_registration_config_cancel",
        row=2,
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Discard the draft without changing persisted settings."""
        self.stop()
        await interaction.response.defer()
        await interaction.delete_original_response()

    async def save(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if not await _save_registration_draft(self.draft, interaction):
            return
        self.stop()
        await interaction.delete_original_response()
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.saved"),
            ephemeral=True,
        )


class RegistrationExportChannelSelect(discord.ui.ChannelSelect):
    """Select the guild-wide destination for registration JSON snapshots."""

    def __init__(self, export_view: RegistrationExportChannelView) -> None:
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder=t(
                export_view.guild,
                "registration.setup.config.export_channel_select",
            ),
            min_values=1,
            max_values=1,
        )
        self.export_view = export_view

    async def callback(self, interaction: discord.Interaction) -> None:
        """Validate and save the selected export channel.

        Args:
            interaction: Interaction that selected the channel.
        """
        selected_channel = self.values[0]
        channel = self.export_view.guild.get_channel(selected_channel.id)
        if not isinstance(channel, discord.TextChannel):
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.export_channel_invalid"),
                ephemeral=True,
                delete_after=5,
            )
            return
        bot_member = self.export_view.guild.me
        if bot_member is None:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.export_channel_error"),
                ephemeral=True,
                delete_after=5,
            )
            return
        permissions = channel.permissions_for(bot_member)
        if not permissions.send_messages or not permissions.attach_files:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.export_channel_missing_permissions"),
                ephemeral=True,
                delete_after=5,
            )
            return
        self.export_view.draft.export_channel_id = channel.id
        await interaction.response.edit_message(
            embed=await configuration_message(
                self.export_view.module,
                interaction,
                self.export_view.registration_channel_id,
                self.export_view.draft,
            ),
            content=None,
            view=RegistrationConfigView(self.export_view.draft),
        )


class RegistrationExportChannelView(RegistrationSetupView):
    """Set or disable the guild-wide JSON export channel."""

    def __init__(
        self,
        draft: RegistrationSetupDraft,
    ) -> None:
        super().__init__(owner_id=draft.owner_id, timeout=180)
        self.draft = draft
        self.module = draft.module
        self.guild = draft.module.guild
        self.registration_channel_id = draft.channel_id
        self.channel_select: RegistrationExportChannelSelect = (
            RegistrationExportChannelSelect(self)
        )
        self.add_item(self.channel_select)
        labels = {
            "wz_registration_config_export_disable": ("registration.setup.config.export_disable"),
            "wz_registration_config_export_back": "registration.setup.config.back",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in labels:
                item.label = t(self.guild, labels[item.custom_id])

    @discord.ui.button(
        label="Export deaktivieren",
        style=discord.ButtonStyle.danger,
        custom_id="wz_registration_config_export_disable",
        emoji="🚫",
        row=1,
    )
    async def disable_export(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Disable the guild-wide registration snapshot export destination.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        self.draft.export_channel_id = None
        await interaction.response.edit_message(
            embed=await configuration_message(
                self.module, interaction, self.registration_channel_id, self.draft
            ),
            content=None,
            view=RegistrationConfigView(self.draft),
        )

    @discord.ui.button(
        label="Zurück",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_export_back",
        emoji="↩️",
        row=1,
    )
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Return to the registration configuration panel.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        await interaction.response.edit_message(
            embed=await configuration_message(
                self.module, interaction, self.registration_channel_id, self.draft
            ),
            content=None,
            view=RegistrationConfigView(self.draft),
        )


class RegistrationTitleModal(discord.ui.Modal):
    """Collect a registration overview title into the current draft."""

    def __init__(self, draft: RegistrationSetupDraft) -> None:
        super().__init__(title=t(draft.module.guild, "registration.setup.config.title_modal"))
        self.draft = draft
        self.title_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "registration.setup.config.title_label"),
            required=False,
            max_length=256,
            default=draft.title,
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Validate and save the submitted registration title.

        Args:
            interaction: Interaction that submitted the modal.
        """
        if interaction.user.id != self.draft.owner_id:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.owner_only"),
                ephemeral=True,
                delete_after=5,
            )
            return
        self.draft.title = self.title_input.value.strip()
        await interaction.response.edit_message(
            content=None,
            embed=await configuration_message(
                self.draft.module,
                interaction,
                self.draft.channel_id,
                self.draft,
            ),
            view=RegistrationConfigView(self.draft),
        )


class RegistrationTextModal(discord.ui.Modal):
    """Collect registration overview text into the current draft."""

    def __init__(self, draft: RegistrationSetupDraft) -> None:
        super().__init__(title=t(draft.module.guild, "registration.setup.config.text_modal"))
        self.draft = draft
        self.text_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "registration.setup.config.text_label"),
            style=discord.TextStyle.paragraph,
            required=len(draft.description) > 4000,
            max_length=4000,
            default=draft.description if len(draft.description) <= 4000 else None,
            placeholder=(
                t(draft.module.guild, "registration.setup.config.text_over_limit")
                if len(draft.description) > 4000
                else None
            ),
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Validate and save the submitted registration description.

        Args:
            interaction: Interaction that submitted the modal.
        """
        if interaction.user.id != self.draft.owner_id:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.owner_only"),
                ephemeral=True,
                delete_after=5,
            )
            return
        self.draft.description = self.text_input.value.strip()
        await interaction.response.edit_message(
            content=None,
            embed=await configuration_message(
                self.draft.module,
                interaction,
                self.draft.channel_id,
                self.draft,
            ),
            view=RegistrationConfigView(self.draft),
        )


class RegistrationRoleSelect(discord.ui.RoleSelect):
    """Role selector that forwards its selection to the setup view."""

    def __init__(self, config_view: RegistrationRoleView) -> None:
        super().__init__(
            placeholder=t(config_view.guild, "registration.setup.config.role_select_prompt"),
            min_values=1,
            max_values=1,
        )
        self.config_view = config_view

    async def callback(self, interaction: discord.Interaction) -> None:
        """Store the selected role and enable permanence choices.

        Args:
            interaction: Interaction that selected the role.
        """
        await self.config_view.on_role_select(interaction, self)


class RegistrationRoleView(RegistrationSetupView):
    """Select a role and choose its permanence."""

    def __init__(
        self,
        draft: RegistrationSetupDraft,
    ) -> None:
        super().__init__(owner_id=draft.owner_id, timeout=180)
        self.draft = draft
        self.module = draft.module
        self.guild = draft.module.guild
        self.channel_id = draft.channel_id
        self.selected_role: discord.Role | None = None
        labels = {
            "wz_registration_config_role_permanent": (
                "registration.setup.config.role_permanent"
            ),
            "wz_registration_config_role_temporary": (
                "registration.setup.config.role_non_permanent"
            ),
            "wz_registration_config_role_back": "registration.setup.config.back",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in labels:
                item.label = t(self.guild, labels[item.custom_id])

        self.role_select: RegistrationRoleSelect = RegistrationRoleSelect(self)
        self.add_item(self.role_select)
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in {
                "wz_registration_config_role_permanent",
                "wz_registration_config_role_temporary",
            }:
                item.disabled = True

    async def on_role_select(
        self,
        interaction: discord.Interaction,
        select: RegistrationRoleSelect,
    ) -> None:
        """Record the selected role and enable the role action buttons.

        Args:
            interaction: Interaction that selected the role.
            select: Role selector that produced the selection.
        """
        if not select.values:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.role_select"),
                ephemeral=True,
                delete_after=5,
            )
            return
        self.selected_role = select.values[0]
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in {
                "wz_registration_config_role_permanent",
                "wz_registration_config_role_temporary",
            }:
                item.disabled = False
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
                "max_registration_roles", 4
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

        await interaction.edit_original_response(
            embed=await configuration_message(
                self.module, interaction, self.channel_id, self.draft
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
        """Save the selected role as permanent.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
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
        """Save the selected role as temporary.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
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
        """Return to the registration configuration panel.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        await interaction.response.edit_message(
            embed=await configuration_message(
                self.module, interaction, self.channel_id, self.draft
            ),
            content=None,
            view=RegistrationConfigView(self.draft),
        )


class RegistrationRoleRemovalSelect(discord.ui.Select):
    """Select one or more registration roles available for removal."""

    def __init__(
        self,
        removal_view: RegistrationRoleRemovalView,
        configured_roles: list[tuple[int, str, bool]],
    ) -> None:
        super().__init__(
            placeholder=t(
                removal_view.guild, "registration.setup.config.remove_role_select"
            ),
            min_values=1,
            max_values=len(configured_roles),
            options=[
                discord.SelectOption(
                    label=role_name[:100],
                    value=str(role_id),
                    description=t(
                        removal_view.guild,
                        (
                            "registration.setup.config.role_permanent"
                            if permanent
                            else "registration.setup.config.role_non_permanent"
                        ),
                    ),
                )
                for role_id, role_name, permanent in configured_roles
            ],
        )
        self.removal_view = removal_view

    async def callback(self, interaction: discord.Interaction) -> None:
        """Enable confirmation after one or more roles are selected.

        Args:
            interaction: Interaction that changed the selection.
        """
        for item in self.removal_view.children:
            if (
                isinstance(item, discord.ui.Button)
                and item.custom_id == "wz_registration_config_role_remove_confirm"
            ):
                item.disabled = False
        await interaction.response.edit_message(view=self.removal_view)


class RegistrationRoleRemovalView(RegistrationSetupView):
    """Choose configured roles to remove from one registration."""

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
        labels = {
            "wz_registration_config_role_remove_confirm": (
                "registration.setup.config.remove_role_confirm"
            ),
            "wz_registration_config_role_remove_back": "registration.setup.config.back",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in labels:
                item.label = t(self.guild, labels[item.custom_id])
            if (
                isinstance(item, discord.ui.Button)
                and item.custom_id == "wz_registration_config_role_remove_confirm"
            ):
                item.disabled = True

    @discord.ui.button(
        label="Rollen entfernen",
        style=discord.ButtonStyle.danger,
        custom_id="wz_registration_config_role_remove_confirm",
    )
    async def confirm_remove(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Remove the selected roles and their registrations from the channel.

        Args:
            interaction: Interaction that confirmed role removal.
            button: Button that triggered the callback.
        """
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
                "min_registration_roles", 1
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

        await interaction.edit_original_response(
            content=None,
            embed=await configuration_message(
                self.module, interaction, self.channel_id, self.draft
            ),
            view=RegistrationConfigView(self.draft),
        )

    @discord.ui.button(
        label="Zurück",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_role_remove_back",
        emoji="↩️",
    )
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Return to the registration configuration panel.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        await interaction.response.edit_message(
            content=None,
            embed=await configuration_message(
                self.module, interaction, self.channel_id, self.draft
            ),
            view=RegistrationConfigView(self.draft),
        )


async def _save_registration_draft(
    draft: RegistrationSetupDraft, interaction: discord.Interaction
) -> str | None:
    """Apply the validated setup draft and return its user-facing result."""
    module = draft.module
    guild = module.guild
    min_roles = int(
        registration_defaults(module.module_key).get("min_registration_roles", 1)
    )
    max_roles = int(
        registration_defaults(module.module_key).get("max_registration_roles", 4)
    )
    if not min_roles <= len(draft.roles) <= max_roles:
        await send_followup(
            interaction,
            t(
                interaction,
                "registration.setup.config.role_count_invalid",
                minimum=min_roles,
                maximum=max_roles,
            ),
            ephemeral=True,
        )
        return None

    current_roles = await module.roles.get(guild=guild, channel_id=draft.channel_id)
    current_role_map = {role.role: role.permanent for role in current_roles or ()}
    if current_role_map != draft.original_roles:
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.stale"),
            ephemeral=True,
        )
        return None
    current_settings = await module.registration.get(
        guild=guild, channel_id=draft.channel_id
    )
    current_title = (
        current_settings.title if current_settings and current_settings.title else ""
    )
    current_description = (
        current_settings.description
        if current_settings and current_settings.description
        else ""
    )
    current_show_lock_emojis = (
        current_settings.show_lock_emojis if current_settings else True
    )
    if (
        current_title != draft.original_title
        or current_description != draft.original_description
        or current_show_lock_emojis != draft.original_show_lock_emojis
    ):
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.stale"),
            ephemeral=True,
        )
        return None
    current_export_channel_id = await module.registration_event_channel.get(guild=guild)
    if current_export_channel_id != draft.original_export_channel_id:
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.stale"),
            ephemeral=True,
        )
        return None

    for role_id in draft.roles:
        role = guild.get_role(role_id)
        if (
            role is None
            or role.is_default()
            or role.managed
            or (guild.me is not None and role >= guild.me.top_role)
        ):
            await send_followup(
                interaction,
                t(interaction, "registration.setup.config.role_hierarchy_error"),
                ephemeral=True,
            )
            return None

    export_channel = (
        guild.get_channel(draft.export_channel_id)
        if draft.export_channel_id is not None
        else None
    )
    if draft.export_channel_id is not None:
        if not isinstance(export_channel, discord.TextChannel):
            await send_followup(
                interaction,
                t(interaction, "registration.setup.config.export_channel_invalid"),
                ephemeral=True,
            )
            return None
        bot_member = guild.me
        if bot_member is None:
            await send_followup(
                interaction,
                t(interaction, "registration.setup.config.export_channel_error"),
                ephemeral=True,
            )
            return None
        permissions = export_channel.permissions_for(bot_member)
        if not permissions.send_messages or not permissions.attach_files:
            await send_followup(
                interaction,
                t(interaction, "registration.setup.config.export_channel_missing_permissions"),
                ephemeral=True,
            )
            return None

    if not await module.registration.upsert(
        guild=guild,
        channel_id=draft.channel_id,
        title=draft.title,
        description=draft.description,
        show_lock_emojis=draft.show_lock_emojis,
    ):
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.save_error"),
            ephemeral=True,
        )
        return None

    for role_id, permanent in draft.roles.items():
        if draft.original_roles.get(role_id) == permanent:
            continue
        if not await module.roles.add(
            guild=guild,
            role=role_id,
            permanent=permanent,
            score=1,
            channel_id=draft.channel_id,
        ):
            await send_followup(
                interaction,
                t(interaction, "registration.setup.config.partial_save_error"),
                ephemeral=True,
            )
            return None

    removed_role_ids = sorted(draft.original_roles.keys() - draft.roles.keys())
    failed_members: set[int] = set()
    if removed_role_ids:
        registrations = await module.registrations.get(
            guild=guild, roles=removed_role_ids, channel_id=draft.channel_id
        )
        if not await module.roles.remove(
            guild=guild, roles=removed_role_ids, channel_id=draft.channel_id
        ) or not await module.registrations.remove(
            guild=guild, roles=removed_role_ids, channel_id=draft.channel_id
        ):
            await send_followup(
                interaction,
                t(interaction, "registration.setup.config.partial_save_error"),
                ephemeral=True,
            )
            return None
        for member_id in {
            record.member for record in registrations or () if record.member is not None
        }:
            member = await fetch_member(guild, member_id)
            if member is None:
                continue
            roles_to_remove = [
                role
                for role_id in removed_role_ids
                if (role := guild.get_role(role_id)) is not None
                and role in member.roles
            ]
            if not roles_to_remove:
                continue
            try:
                await member.remove_roles(
                    *roles_to_remove,
                    reason="Registration setup role removal",
                )
            except discord.HTTPException:
                failed_members.add(member.id)
                _logger.exception(
                    "Failed to remove registration roles %s from member %s in guild %s.",
                    removed_role_ids,
                    member.id,
                    guild.id,
                )

    if draft.export_channel_id != draft.original_export_channel_id:
        if draft.export_channel_id is None:
            changed = await module.registration_event_channel.remove(guild=guild)
        else:
            changed = await module.registration_event_channel.set(
                guild=guild, channel_id=draft.export_channel_id
            )
        if not changed:
            await send_followup(
                interaction,
                t(interaction, "registration.setup.config.partial_save_error"),
                ephemeral=True,
            )
            return None

    if not await module.compose_registration_overview(
        force=True, channel_id=draft.channel_id
    ):
        return t(interaction, "registration.setup.config.saved_refresh_error")
    if failed_members:
        return t(
            interaction,
            "registration.setup.config.remove_role_member_warning",
            count=len(failed_members),
        )
    return t(interaction, "registration.setup.config.saved")
