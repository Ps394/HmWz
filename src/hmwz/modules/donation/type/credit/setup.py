"""Configuration of credit units and optional fixed donation amounts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_temporary_response

from ...models import DonationType
from .validation import parse_donation_choices

if TYPE_CHECKING:
    from ...commands.setup.config.view import DonationSetupView
    from ...commands.setup.config.draft import DonationSetupDraft


def configured_type(draft: DonationSetupDraft) -> DonationType:
    """Build the credit input configuration collected by the setup."""
    return DonationType(
        name=t(draft.module.guild, "donation.setup.simple"),
        kind="simple",
        unit=draft.unit,
        input_mode="choice" if draft.choices else "free",
        choices=draft.choices,
        time_reductions=(),
    )


class DonationValuesModal(discord.ui.Modal):
    """Edit the donation unit and optional fixed amount values."""

    def __init__(self, setup_view: DonationSetupView) -> None:
        draft = setup_view.draft
        super().__init__(
            title=t(draft.module.guild, "donation.setup.values_title")[:45]
        )
        self.draft = draft
        self.setup_view = setup_view
        self.unit_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "donation.setup.unit")[:45],
            placeholder=t(draft.module.guild, "donation.setup.unit_example")[:100],
            default=draft.unit,
            max_length=45,
        )
        self.choices_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "donation.setup.choices")[:45],
            placeholder=t(draft.module.guild, "donation.setup.choices_example")[:100],
            default="; ".join(draft.choices),
            required=False,
            max_length=1000,
        )
        self.add_item(self.unit_input)
        self.add_item(self.choices_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        unit = self.unit_input.value.strip()
        if not unit:
            await send_temporary_response(
                interaction, t(interaction, "donation.error.unit_required")
            )
            return
        try:
            choices = parse_donation_choices(self.choices_input.value)
        except ValueError:
            await send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_setup_values")
            )
            return
        self.draft.unit = unit
        self.draft.choices = choices
        await self.setup_view.refresh(interaction)
