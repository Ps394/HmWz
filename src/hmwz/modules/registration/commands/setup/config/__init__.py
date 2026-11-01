"""Interactive controls for configuring registration channels and roles."""

from __future__ import annotations

import logging

import discord

from hmwz.configuration import registration_defaults
from hmwz.emojis import emojis
from hmwz.i18n import t
from hmwz.modules.registration.module import RegistrationModule
from hmwz.ui.messages import send_temporary_followup
from hmwz.utils.loaders import fetch_member

from .configuration_message import configuration_message
from .view import RegistrationSetupView

_configuration_message = configuration_message
_logger = logging.getLogger(__name__)


class RegistrationConfigView(RegistrationSetupView):
    """Private control panel for one registration channel."""

    def __init__(
        self,
        module: RegistrationModule,
        channel_id: int,
        owner_id: int,
    ) -> None:
        super().__init__(owner_id=owner_id, timeout=300)
        self.module = module
        self.guild = module.guild
        self.channel_id = channel_id
        labels = {
            "wz_registration_config_title": "wz.setup.config.edit_title",
            "wz_registration_config_text": "wz.setup.config.edit_text",
            "wz_registration_config_lock_emojis": (
                "registration.setup.config.toggle_lock_emojis"
            ),
            "wz_registration_config_add_role": "wz.setup.config.add_role",
            "wz_registration_config_remove_role": "registration.setup.config.remove_role",
            "wz_registration_config_export_channel": ("wz.setup.config.export_channel"),
            "wz_registration_config_apply": "registration.setup.config.apply",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in labels:
                item.label = t(self.guild, labels[item.custom_id])
                if item.custom_id == "wz_registration_config_apply":
                    item.emoji = emojis.get("success", self.guild)

    @discord.ui.button(
        label="Titel bearbeiten",
        style=discord.ButtonStyle.primary,
        custom_id="wz_registration_config_title",
    )
    async def edit_title(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Open a modal to edit the registration overview title.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        settings = await self.module.registration.get(
            guild=self.guild, channel_id=self.channel_id
        )
        await interaction.response.send_modal(
            RegistrationTitleModal(
                self.module,
                self.channel_id,
                self.owner_id,
                settings.title if settings and settings.title else "",
            )
        )

    @discord.ui.button(
        label="Text bearbeiten",
        style=discord.ButtonStyle.primary,
        custom_id="wz_registration_config_text",
    )
    async def edit_text(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Open a modal to edit the registration overview description.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        settings = await self.module.registration.get(
            guild=self.guild, channel_id=self.channel_id
        )
        await interaction.response.send_modal(
            RegistrationTextModal(
                self.module,
                self.channel_id,
                self.owner_id,
                settings.description if settings and settings.description else "",
            )
        )

    @discord.ui.button(
        label="Schlossemojis umschalten",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_lock_emojis",
    )
    async def toggle_lock_emojis(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Toggle lock emoji visibility in the registration overview."""
        settings = await self.module.registration.get(
            guild=self.guild, channel_id=self.channel_id
        )
        show_lock_emojis = not (
            settings.show_lock_emojis if settings is not None else True
        )
        if not await self.module.registration.upsert(
            guild=self.guild,
            channel_id=self.channel_id,
            show_lock_emojis=show_lock_emojis,
        ):
            await interaction.response.send_message(
                t(interaction, "registration.setup.config.save_error"),
                ephemeral=True,
                delete_after=5,
            )
            return

        roles = await self.module.roles.get(
            guild=self.guild, channel_id=self.channel_id
        )
        refresh_failed = bool(
            roles
        ) and not await self.module.compose_registration_overview(
            force=True, channel_id=self.channel_id
        )
        await interaction.response.edit_message(
            content=(
                t(interaction, "registration.setup.config.lock_emojis_refresh_error")
                if refresh_failed
                else None
            ),
            embed=await configuration_message(
                self.module, interaction, self.channel_id
            ),
            view=RegistrationConfigView(self.module, self.channel_id, self.owner_id),
        )

    @discord.ui.button(
        label="Rolle hinzufügen",
        style=discord.ButtonStyle.success,
        custom_id="wz_registration_config_add_role",
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
            content=t(interaction, "wz.setup.config.role_prompt"),
            view=RegistrationRoleView(self.module, self.channel_id, self.owner_id),
        )

    @discord.ui.button(
        label="Rolle entfernen",
        style=discord.ButtonStyle.danger,
        custom_id="wz_registration_config_remove_role",
    )
    async def remove_role(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Open the role removal view for the current channel.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        configured_roles = await self.module.roles.get(
            guild=self.guild, channel_id=self.channel_id
        )
        if not configured_roles:
            await interaction.response.send_message(
                t(interaction, "registration.setup.config.no_roles_to_remove"),
                ephemeral=True,
                delete_after=5,
            )
            return
        roles = [
            (
                record.role,
                (
                    role.name
                    if (role := self.guild.get_role(record.role)) is not None
                    else str(record.role)
                ),
                record.permanent,
            )
            for record in configured_roles
        ]
        if not roles:
            await interaction.response.send_message(
                t(interaction, "registration.setup.config.no_roles_to_remove"),
                ephemeral=True,
                delete_after=5,
            )
            return
        await interaction.response.edit_message(
            content=t(interaction, "registration.setup.config.remove_role_prompt"),
            embed=None,
            view=RegistrationRoleRemovalView(
                self.module, self.channel_id, self.owner_id, roles
            ),
        )

    @discord.ui.button(
        label="JSON-Exportkanal",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_export_channel",
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
            content=t(interaction, "wz.setup.config.export_channel_prompt"),
            view=RegistrationExportChannelView(
                self.module, self.channel_id, self.owner_id
            ),
        )

    @discord.ui.button(
        label="Übernehmen",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="wz_registration_config_apply",
    )
    async def apply(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Close the setup panel after applying the persisted configuration."""
        await interaction.response.defer()
        await interaction.delete_original_response()


class RegistrationExportChannelSelect(discord.ui.ChannelSelect):
    """Select the guild-wide destination for registration JSON snapshots."""

    def __init__(self, export_view: RegistrationExportChannelView) -> None:
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder=t(
                export_view.guild,
                "wz.setup.config.export_channel_select",
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
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.export_channel_invalid"),
                ephemeral=True,
                delete_after=5,
            )
            return
        bot_member = self.export_view.guild.me
        if bot_member is None:
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.export_channel_error"),
                ephemeral=True,
                delete_after=5,
            )
            return
        permissions = channel.permissions_for(bot_member)
        if not permissions.send_messages or not permissions.attach_files:
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.export_channel_missing_permissions"),
                ephemeral=True,
                delete_after=5,
            )
            return
        if not await self.export_view.module.registration_event_channel.set(
            guild=self.export_view.guild,
            channel_id=channel.id,
        ):
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.export_channel_error"),
                ephemeral=True,
                delete_after=5,
            )
            return
        await interaction.response.edit_message(
            embed=await configuration_message(
                self.export_view.module,
                interaction,
                self.export_view.registration_channel_id,
            ),
            view=RegistrationConfigView(
                self.export_view.module,
                self.export_view.registration_channel_id,
                self.export_view.owner_id,
            ),
        )


class RegistrationExportChannelView(RegistrationSetupView):
    """Set or disable the guild-wide JSON export channel."""

    def __init__(
        self,
        module: RegistrationModule,
        registration_channel_id: int,
        owner_id: int,
    ) -> None:
        super().__init__(owner_id=owner_id, timeout=180)
        self.module = module
        self.guild = module.guild
        self.registration_channel_id = registration_channel_id
        self.channel_select: RegistrationExportChannelSelect = (
            RegistrationExportChannelSelect(self)
        )
        self.add_item(self.channel_select)
        labels = {
            "wz_registration_config_export_disable": ("wz.setup.config.export_disable"),
            "wz_registration_config_export_back": "wz.setup.config.back",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in labels:
                item.label = t(self.guild, labels[item.custom_id])

    @discord.ui.button(
        label="Export deaktivieren",
        style=discord.ButtonStyle.danger,
        custom_id="wz_registration_config_export_disable",
    )
    async def disable_export(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Disable the guild-wide registration snapshot export destination.

        Args:
            interaction: Interaction that triggered the button.
            button: Button that triggered the callback.
        """
        if not await self.module.registration_event_channel.remove(guild=self.guild):
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.export_channel_error"),
                ephemeral=True,
                delete_after=5,
            )
            return
        await interaction.response.edit_message(
            embed=await configuration_message(
                self.module, interaction, self.registration_channel_id
            ),
            content=None,
            view=RegistrationConfigView(
                self.module, self.registration_channel_id, self.owner_id
            ),
        )

    @discord.ui.button(
        label="Zurück",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_export_back",
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
                self.module, interaction, self.registration_channel_id
            ),
            content=None,
            view=RegistrationConfigView(
                self.module, self.registration_channel_id, self.owner_id
            ),
        )


class RegistrationTitleModal(discord.ui.Modal):
    """Collect and save a registration overview title."""

    def __init__(
        self,
        module: RegistrationModule,
        channel_id: int,
        owner_id: int,
        current_title: str,
    ) -> None:
        super().__init__(title=t(module.guild, "wz.setup.config.title_modal"))
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.title_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(module.guild, "wz.setup.config.title_label"),
            required=False,
            max_length=256,
            default=current_title,
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Validate and save the submitted registration title.

        Args:
            interaction: Interaction that submitted the modal.
        """
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.owner_only"),
                ephemeral=True,
                delete_after=5,
            )
            return
        if not await self.module.registration.upsert(
            guild=self.module.guild,
            channel_id=self.channel_id,
            title=self.title_input.value.strip(),
        ):
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.save_error"),
                ephemeral=True,
                delete_after=5,
            )
            return
        roles = await self.module.roles.get(
            guild=self.module.guild, channel_id=self.channel_id
        )
        if roles and not await self.module.compose_registration_overview(
            force=True, channel_id=self.channel_id
        ):
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.saved_refresh_error"),
                ephemeral=True,
                delete_after=5,
            )
            return
        await interaction.response.send_message(
            t(interaction, "wz.setup.config.title_saved"),
            ephemeral=True,
            delete_after=5,
        )


class RegistrationTextModal(discord.ui.Modal):
    """Collect and save registration overview text."""

    def __init__(
        self,
        module: RegistrationModule,
        channel_id: int,
        owner_id: int,
        current_text: str,
    ) -> None:
        super().__init__(title=t(module.guild, "wz.setup.config.text_modal"))
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.text_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(module.guild, "wz.setup.config.text_label"),
            style=discord.TextStyle.paragraph,
            required=len(current_text) > 4000,
            max_length=4000,
            default=current_text if len(current_text) <= 4000 else None,
            placeholder=(
                t(module.guild, "wz.setup.config.text_over_limit")
                if len(current_text) > 4000
                else None
            ),
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Validate and save the submitted registration description.

        Args:
            interaction: Interaction that submitted the modal.
        """
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.owner_only"),
                ephemeral=True,
                delete_after=5,
            )
            return
        if not await self.module.registration.upsert(
            guild=self.module.guild,
            channel_id=self.channel_id,
            description=self.text_input.value.strip(),
        ):
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.save_error"),
                ephemeral=True,
                delete_after=5,
            )
            return
        roles = await self.module.roles.get(
            guild=self.module.guild, channel_id=self.channel_id
        )
        if roles and not await self.module.compose_registration_overview(
            force=True, channel_id=self.channel_id
        ):
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.saved_refresh_error"),
                ephemeral=True,
                delete_after=5,
            )
            return
        await interaction.response.send_message(
            t(interaction, "wz.setup.config.text_saved"),
            ephemeral=True,
            delete_after=5,
        )


class RegistrationRoleSelect(discord.ui.RoleSelect):
    """Role selector that forwards its selection to the setup view."""

    def __init__(self, config_view: RegistrationRoleView) -> None:
        super().__init__(
            placeholder=t(config_view.guild, "wz.setup.config.role_select_prompt"),
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
        module: RegistrationModule,
        channel_id: int,
        owner_id: int,
    ) -> None:
        super().__init__(owner_id=owner_id, timeout=180)
        self.module = module
        self.guild = module.guild
        self.channel_id = channel_id
        self.selected_role: discord.Role | None = None
        labels = {
            "wz_registration_config_role_permanent": (
                "registration.setup.config.role_permanent"
            ),
            "wz_registration_config_role_temporary": (
                "registration.setup.config.role_non_permanent"
            ),
            "wz_registration_config_role_back": "wz.setup.config.back",
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
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.role_select"),
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
                t(interaction, "wz.setup.config.role_select"),
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
                t(interaction, "wz.setup.config.role_hierarchy_error"),
                ephemeral=True,
            )
            return

        configured_roles = await self.module.roles.get(
            guild=self.guild, channel_id=self.channel_id
        )
        configured_ids = {configured.role for configured in configured_roles or ()}
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
                    "wz.setup.config.max_roles",
                    max_roles=max_roles,
                ),
                ephemeral=True,
            )
            return
        if not await self.module.roles.add(
            guild=self.guild,
            role=role.id,
            permanent=permanent,
            score=1,
            channel_id=self.channel_id,
        ):
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.setup.config.save_error"),
                ephemeral=True,
            )
            return
        if not await self.module.compose_registration_overview(
            force=True, channel_id=self.channel_id
        ):
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.setup.config.role_saved_refresh_error"),
                ephemeral=True,
            )
            return

        await interaction.edit_original_response(
            embed=await configuration_message(
                self.module, interaction, self.channel_id
            ),
            content=None,
            view=RegistrationConfigView(self.module, self.channel_id, self.owner_id),
        )

    @discord.ui.button(
        label="Permanent",
        style=discord.ButtonStyle.primary,
        custom_id="wz_registration_config_role_permanent",
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
                self.module, interaction, self.channel_id
            ),
            content=None,
            view=RegistrationConfigView(self.module, self.channel_id, self.owner_id),
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
        module: RegistrationModule,
        channel_id: int,
        owner_id: int,
        configured_roles: list[tuple[int, str, bool]],
    ) -> None:
        super().__init__(owner_id=owner_id, timeout=180)
        self.module = module
        self.guild = module.guild
        self.channel_id = channel_id
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
            await interaction.response.send_message(
                t(interaction, "registration.setup.config.remove_role_select"),
                ephemeral=True,
                delete_after=5,
            )
            return

        configured_roles = await self.module.roles.get(
            guild=self.guild, channel_id=self.channel_id
        )
        configured_ids = {record.role for record in configured_roles or ()}
        min_roles = int(
            registration_defaults(self.module.module_key).get(
                "min_registration_roles", 1
            )
        )
        if not set(selected_role_ids).issubset(configured_ids):
            await interaction.response.send_message(
                t(interaction, "registration.setup.config.remove_role_stale"),
                ephemeral=True,
                delete_after=5,
            )
            return
        if len(configured_ids) - len(selected_role_ids) < min_roles:
            await interaction.response.send_message(
                t(interaction, "registration.setup.config.remove_role_minimum"),
                ephemeral=True,
                delete_after=5,
            )
            return

        await interaction.response.defer()
        registrations = await self.module.registrations.get(
            guild=self.guild,
            roles=selected_role_ids,
            channel_id=self.channel_id,
        )
        if not await self.module.roles.remove(
            guild=self.guild,
            roles=selected_role_ids,
            channel_id=self.channel_id,
        ):
            await interaction.followup.send(
                t(interaction, "registration.setup.config.save_error"),
                ephemeral=True,
            )
            return
        if not await self.module.registrations.remove(
            guild=self.guild,
            roles=selected_role_ids,
            channel_id=self.channel_id,
        ):
            await interaction.followup.send(
                t(interaction, "registration.setup.config.save_error"),
                ephemeral=True,
            )
            return

        failed_members: set[int] = set()
        for member_id in {
            record.member for record in registrations or () if record.member is not None
        }:
            member = await fetch_member(self.guild, member_id)
            if member is None:
                continue
            roles_to_remove = [
                role
                for role_id in selected_role_ids
                if (role := self.guild.get_role(role_id)) is not None
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
                    selected_role_ids,
                    member.id,
                    self.guild.id,
                )

        if not await self.module.compose_registration_overview(
            force=True, channel_id=self.channel_id
        ):
            await interaction.edit_original_response(
                content=t(
                    interaction,
                    "registration.setup.config.role_saved_refresh_error",
                ),
                view=None,
            )
            return

        await interaction.edit_original_response(
            content=(
                t(
                    interaction,
                    "registration.setup.config.remove_role_member_warning",
                    count=len(failed_members),
                )
                if failed_members
                else None
            ),
            embed=await configuration_message(
                self.module, interaction, self.channel_id
            ),
            view=RegistrationConfigView(self.module, self.channel_id, self.owner_id),
        )

    @discord.ui.button(
        label="Zurück",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_role_remove_back",
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
                self.module, interaction, self.channel_id
            ),
            view=RegistrationConfigView(self.module, self.channel_id, self.owner_id),
        )
