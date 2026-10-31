"""Credit donation amount buttons and input modal."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import discord

from hmwz.emojis import emojis
from hmwz.i18n import t
from hmwz.ui.messages import (
    send_temporary_response as _send_temporary_response,
)

from ...overview import DonationOverview
from ...models import DEFAULT_DONATION_CHOICES, DonationType
from .validation import parse_amount

if TYPE_CHECKING:
    from ...module import DonationModule


class DonationRecordButton(discord.ui.Button):
    """Button that starts the donation flow for its channel."""

    def __init__(self, module: DonationModule, channel_id: int) -> None:
        super().__init__(
            label=t(module.guild, "donation.ui.record_button"),
            style=discord.ButtonStyle.success,
            emoji=emojis.get("credit", module.guild),
            custom_id="donation:record",
        )
        self.module = module
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.start_donation(interaction, self.channel_id)


class DonationAmountOptionButton(discord.ui.Button):
    """Record a simple donation using one configured fixed amount."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_type: DonationType,
        amount: Decimal,
        index: int,
        *,
        dismiss_prompt: bool = False,
    ) -> None:
        super().__init__(
            label=(f"{DonationOverview._format_amount(amount)} {donation_type.unit}")[
                :80
            ],
            style=discord.ButtonStyle.primary,
            emoji=emojis.get("credit", module.guild),
            custom_id=f"donation:amount:{channel_id}:{index}",
            row=index // 5,
        )
        self.module = module
        self.channel_id = channel_id
        self.donation_type = donation_type
        self.amount = amount
        self.dismiss_prompt = dismiss_prompt

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        saved, messages_updated = await self.module.record_donation(
            interaction,
            self.channel_id,
            self.donation_type,
            self.amount,
            time_reduction=None,
        )
        if self.dismiss_prompt:
            await interaction.delete_original_response()
        result_key = (
            "donation.error.save"
            if not saved
            else (
                "donation.success.saved"
                if messages_updated
                else "donation.success.saved_overview_failed"
            )
        )
        result = await interaction.followup.send(
            t(interaction, result_key), ephemeral=True, wait=True
        )
        await result.delete(delay=5)


class DonationAmountChoiceView(discord.ui.View):
    """Present fixed donation amounts as directly selectable buttons."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_type: DonationType,
        *,
        timeout: float | None = 180,
    ) -> None:
        super().__init__(timeout=timeout)
        choices = donation_type.choices or DEFAULT_DONATION_CHOICES
        for index, choice in enumerate(choices):
            self.add_item(
                DonationAmountOptionButton(
                    module,
                    channel_id,
                    donation_type,
                    Decimal(choice),
                    index,
                    dismiss_prompt=True,
                )
            )


class DonationAmountModal(discord.ui.Modal):
    """Collect and validate the amount for a configured donation."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_type: DonationType,
        time_reduction: str | None = None,
    ) -> None:
        super().__init__(title=t(module.guild, "donation.modal.title")[:45])
        self.module = module
        self.channel_id = channel_id
        self.donation_type = donation_type
        self.time_reduction = time_reduction
        self.amount_input = self._create_amount_input(module, donation_type)
        self.add_item(self.amount_input)

    @staticmethod
    def _create_amount_input(
        module: DonationModule, donation_type: DonationType
    ) -> discord.ui.TextInput:
        placeholder = t(module.guild, "donation.modal.amount_placeholder")
        if donation_type.choices:
            placeholder = t(
                module.guild,
                "donation.modal.amount_choices",
                choices=", ".join(donation_type.choices),
            )
        return discord.ui.TextInput(
            label=t(module.guild, "donation.modal.amount", unit=donation_type.unit)[
                :45
            ],
            placeholder=placeholder[:100],
            max_length=32,
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        amount = await self._parse_amount(interaction)
        if amount is None:
            return
        if not await self._is_valid_choice(interaction, amount):
            return
        await self._record(interaction, amount)

    async def _parse_amount(self, interaction: discord.Interaction) -> Decimal | None:
        try:
            return parse_amount(self.amount_input.value)
        except ValueError:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_amount")
            )
            return None

    async def _is_valid_choice(
        self, interaction: discord.Interaction, amount: Decimal
    ) -> bool:
        if self.donation_type.input_mode != "choice" or amount in {
            Decimal(choice) for choice in self.donation_type.choices
        }:
            return True
        await _send_temporary_response(
            interaction, t(interaction, "donation.error.invalid_amount_choice")
        )
        return False

    async def _record(self, interaction: discord.Interaction, amount: Decimal) -> None:
        await interaction.response.defer(ephemeral=True)
        saved, messages_updated = await self.module.record_donation(
            interaction,
            self.channel_id,
            self.donation_type,
            amount,
            time_reduction=self.time_reduction,
        )
        result = await interaction.followup.send(
            t(interaction, self._result_key(saved, messages_updated)),
            ephemeral=True,
            wait=True,
        )
        await result.delete(delay=5)

    @staticmethod
    def _result_key(saved: bool, messages_updated: bool) -> str:
        if not saved:
            return "donation.error.save"
        if messages_updated:
            return "donation.success.saved"
        return "donation.success.saved_overview_failed"


def add_overview_controls(
    view: discord.ui.View,
    module: DonationModule,
    channel_id: int,
    donation_type: DonationType,
) -> None:
    """Attach fixed credit amounts or a free-entry button to an overview."""
    if donation_type.input_mode == "choice" and donation_type.choices:
        for index, choice in enumerate(donation_type.choices):
            view.add_item(
                DonationAmountOptionButton(
                    module, channel_id, donation_type, Decimal(choice), index
                )
            )
    else:
        view.add_item(DonationRecordButton(module, channel_id))
