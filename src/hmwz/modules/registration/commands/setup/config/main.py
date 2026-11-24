"""Main registration setup control panel."""

from __future__ import annotations

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_followup, send_initial_response

from .configuration_message import configuration_message
from .content import RegistrationTextModal, RegistrationTitleModal
from .draft import RegistrationSetupDraft
from .export_channel import RegistrationExportChannelView
from .roles import RegistrationRoleRemovalView, RegistrationRoleView
from .service import save_registration_draft
from .view import RegistrationSetupView


class RegistrationConfigView(RegistrationSetupView):
    """Private control panel for one registration channel."""

    def __init__(self, draft: RegistrationSetupDraft) -> None:
        super().__init__(owner_id=draft.owner_id, timeout=300)
        self.draft = draft
        self.module = draft.module
        self.guild = draft.module.guild
        self.channel_id = draft.channel_id

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
        del button
        await interaction.response.send_modal(RegistrationTitleModal(self.draft))

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
        del button
        await interaction.response.send_modal(RegistrationTextModal(self.draft))

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
        del button
        self.draft.show_lock_emojis = not self.draft.show_lock_emojis
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
        del button
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
        del button
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
        del button
        await interaction.response.edit_message(
            content=t(
                interaction,
                "registration.setup.config.export_channel_prompt",
            ),
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
        del button
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
        del button
        self.stop()
        await interaction.response.defer()
        await interaction.delete_original_response()

    async def save(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        result = await save_registration_draft(self.draft, interaction)
        if result is None:
            return
        self.stop()
        await interaction.delete_original_response()
        await send_followup(
            interaction,
            result,
            ephemeral=True,
        )
