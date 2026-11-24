"""Export channel views for registration setup."""

from __future__ import annotations

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_initial_response

from .configuration_message import configuration_message
from .draft import RegistrationSetupDraft
from .view import RegistrationSetupView


class RegistrationExportChannelSelect(discord.ui.ChannelSelect):
    """Select the guild-wide JSON export destination."""

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
        channel = self.export_view.guild.get_channel(self.values[0].id)
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
                t(
                    interaction,
                    "registration.setup.config.export_channel_missing_permissions",
                ),
                ephemeral=True,
                delete_after=5,
            )
            return
        self.export_view.draft.export_channel_id = channel.id
        from . import RegistrationConfigView

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
    """Set or disable the registration snapshot export destination."""

    def __init__(self, draft: RegistrationSetupDraft) -> None:
        super().__init__(owner_id=draft.owner_id, timeout=180)
        self.draft = draft
        self.module = draft.module
        self.guild = draft.module.guild
        self.registration_channel_id = draft.channel_id
        self.channel_select = RegistrationExportChannelSelect(self)
        self.add_item(self.channel_select)

    @discord.ui.button(
        label="Export deaktivieren",
        style=discord.ButtonStyle.danger,
        custom_id="wz_registration_config_export_disable",
        row=1,
    )
    async def disable_export(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        del button
        self.draft.export_channel_id = None
        from . import RegistrationConfigView

        await interaction.response.edit_message(
            embed=await configuration_message(
                self.module,
                interaction,
                self.registration_channel_id,
                self.draft,
            ),
            content=None,
            view=RegistrationConfigView(self.draft),
        )

    @discord.ui.button(
        label="Zurück",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_config_export_back",
        row=1,
    )
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        del button
        from . import RegistrationConfigView

        await interaction.response.edit_message(
            embed=await configuration_message(
                self.module,
                interaction,
                self.registration_channel_id,
                self.draft,
            ),
            content=None,
            view=RegistrationConfigView(self.draft),
        )
