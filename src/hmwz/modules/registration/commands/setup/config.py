from __future__ import annotations

import discord

from hmwz.configuration import wz_registration_config
from hmwz.i18n import t
from hmwz.modules.hs.wz.module import WzRegistrationModule

from ...responses import send_temporary_followup
from .configuration_message import configuration_message
from .view import RegistrationSetupView

_configuration_message = configuration_message


class RegistrationConfigView(RegistrationSetupView):
    """Private control panel for one registration channel."""

    def __init__(
        self,
        module: WzRegistrationModule,
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
            "wz_registration_config_add_role": "wz.setup.config.add_role",
            "wz_registration_config_export_channel": ("wz.setup.config.export_channel"),
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in labels:
                item.label = t(self.guild, labels[item.custom_id])

    @discord.ui.button(
        label="Titel bearbeiten",
        style=discord.ButtonStyle.primary,
        custom_id="wz_registration_config_title",
    )
    async def edit_title(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
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
        label="Rolle hinzufügen",
        style=discord.ButtonStyle.success,
        custom_id="wz_registration_config_add_role",
    )
    async def add_role(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content=t(interaction, "wz.setup.config.role_prompt"),
            view=RegistrationRoleView(self.module, self.channel_id, self.owner_id),
        )

    @discord.ui.button(
        label="JSON-Exportkanal",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_export_channel",
    )
    async def configure_export_channel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content=t(interaction, "wz.setup.config.export_channel_prompt"),
            view=RegistrationExportChannelView(
                self.module, self.channel_id, self.owner_id
            ),
        )


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
            content=await configuration_message(
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
        module: WzRegistrationModule,
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
        if not await self.module.registration_event_channel.remove(guild=self.guild):
            await interaction.response.send_message(
                t(interaction, "wz.setup.config.export_channel_error"),
                ephemeral=True,
                delete_after=5,
            )
            return
        await interaction.response.edit_message(
            content=await configuration_message(
                self.module, interaction, self.registration_channel_id
            ),
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
        await interaction.response.edit_message(
            content=await configuration_message(
                self.module, interaction, self.registration_channel_id
            ),
            view=RegistrationConfigView(
                self.module, self.registration_channel_id, self.owner_id
            ),
        )


class RegistrationTitleModal(discord.ui.Modal):
    """Collect and save a registration overview title."""

    def __init__(
        self,
        module: WzRegistrationModule,
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
        module: WzRegistrationModule,
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
        await self.config_view.on_role_select(interaction, self)


class RegistrationRoleView(RegistrationSetupView):
    """Select a role and choose its permanence."""

    def __init__(
        self,
        module: WzRegistrationModule,
        channel_id: int,
        owner_id: int,
    ) -> None:
        super().__init__(owner_id=owner_id, timeout=180)
        self.module = module
        self.guild = module.guild
        self.channel_id = channel_id
        self.selected_role: discord.Role | None = None
        labels = {
            "wz_registration_config_role_permanent": ("wz.setup.config.role_permanent"),
            "wz_registration_config_role_temporary": (
                "wz.setup.config.role_non_permanent"
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
        max_roles = int(wz_registration_config().get("max_registration_roles", 4))
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
            content=await configuration_message(
                self.module, interaction, self.channel_id
            ),
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
        await self._save_role(interaction, permanent=True)

    @discord.ui.button(
        label="Nicht permanent",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_role_temporary",
    )
    async def temporary(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._save_role(interaction, permanent=False)

    @discord.ui.button(
        label="Zurück",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_role_back",
    )
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content=await configuration_message(
                self.module, interaction, self.channel_id
            ),
            view=RegistrationConfigView(self.module, self.channel_id, self.owner_id),
        )
