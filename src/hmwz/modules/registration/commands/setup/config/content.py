"""Modals for editing registration setup title and description."""

from __future__ import annotations

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_initial_response

from .configuration_message import configuration_message
from .draft import RegistrationSetupDraft


class RegistrationTitleModal(discord.ui.Modal):
    """Collect a registration overview title."""

    def __init__(self, draft: RegistrationSetupDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "registration.setup.config.title_modal")
        )
        self.draft = draft
        self.title_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "registration.setup.config.title_label"),
            required=False,
            max_length=256,
            default=draft.title,
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.draft.owner_id:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.owner_only"),
                ephemeral=True,
                delete_after=5,
            )
            return
        self.draft.title = self.title_input.value.strip()
        from . import RegistrationConfigView

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
    """Collect registration overview text."""

    def __init__(self, draft: RegistrationSetupDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "registration.setup.config.text_modal")
        )
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
        if interaction.user.id != self.draft.owner_id:
            await send_initial_response(
                interaction,
                t(interaction, "registration.setup.config.owner_only"),
                ephemeral=True,
                delete_after=5,
            )
            return
        self.draft.description = self.text_input.value.strip()
        from . import RegistrationConfigView

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
