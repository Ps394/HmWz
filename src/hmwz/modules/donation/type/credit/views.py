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
from ...confirmation import DonationConfirmationView
from ...models import DEFAULT_DONATION_CHOICES, DonationType
from .validation import parse_amount

if TYPE_CHECKING:
    from ...module import DonationModule


class DonationRecordButton(discord.ui.Button):
    """Button that starts the donation flow for its channel."""

    def __init__(self, module: DonationModule, channel_id: int) -> None:
        super().__init__(
            label=t(module.guild, "donation.type.credit.record_button"),
            style=discord.ButtonStyle.success,
            emoji=emojis.get("credit", module.guild),
            custom_id="donation:record",
        )
        self.module = module
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.start_donation(interaction, self.channel_id)


class DonationAmountOptionButton(discord.ui.Button):
    """Request confirmation of one configured fixed amount."""

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
        await request_confirmation(
            self.module,
            interaction,
            self.channel_id,
            self.donation_type,
            self.amount,
            replace_prompt=self.dismiss_prompt,
        )


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
        super().__init__(title=t(module.guild, "donation.type.credit.modal.title")[:45])
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
        placeholder = t(module.guild, "donation.type.credit.modal.amount_placeholder")
        if donation_type.choices:
            placeholder = t(
                module.guild,
                "donation.type.credit.modal.amount_choices",
                choices=", ".join(donation_type.choices),
            )
        return discord.ui.TextInput(
            label=t(
                module.guild,
                "donation.type.credit.modal.amount",
                unit=donation_type.unit,
            )[:45],
            placeholder=placeholder[:100],
            max_length=32,
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        amount = await self._parse_amount(interaction)
        if amount is None:
            return
        if not await self._is_valid_choice(interaction, amount):
            return
        await request_confirmation(
            self.module, interaction, self.channel_id, self.donation_type, amount
        )

    async def _parse_amount(self, interaction: discord.Interaction) -> Decimal | None:
        try:
            return parse_amount(self.amount_input.value)
        except ValueError:
            await _send_temporary_response(
                interaction,
                t(interaction, "donation.type.credit.error.invalid_amount"),
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
            interaction,
            t(interaction, "donation.type.credit.error.invalid_amount_choice"),
        )
        return False


class DonationCreditConfirmationView(DonationConfirmationView):
    """Confirm a credit amount in the cycle in which it was selected."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_type: DonationType,
        amount: Decimal,
        expected_cycle: int,
        owner_id: int,
    ) -> None:
        super().__init__(module, owner_id)
        self.channel_id = channel_id
        self.donation_type = donation_type
        self.amount = amount
        self.expected_cycle = expected_cycle
        for item in self.children:
            if (
                isinstance(item, discord.ui.Button)
                and item.custom_id == "donation_confirm"
            ):
                item.emoji = emojis.get("credit", module.guild)

    async def record(self, interaction: discord.Interaction) -> tuple[bool, bool]:
        return await self.module.record_donation(
            interaction,
            self.channel_id,
            self.donation_type,
            self.amount,
            time_reduction=None,
            expected_cycle=self.expected_cycle,
        )


async def request_confirmation(
    module: DonationModule,
    interaction: discord.Interaction,
    channel_id: int,
    donation_type: DonationType,
    amount: Decimal,
    *,
    replace_prompt: bool = False,
) -> None:
    """Open a confirmation without writing a donation."""
    configuration = await module.donations.get_channel(
        guild=module.guild, channel_id=channel_id
    )
    if configuration is None:
        await _send_temporary_response(
            interaction, t(interaction, "donation.error.not_configured")
        )
        return
    if not configuration.donations_enabled:
        await _send_temporary_response(
            interaction, t(interaction, "donation.error.stopped")
        )
        return
    view = DonationCreditConfirmationView(
        module,
        channel_id,
        donation_type,
        amount,
        configuration.current_cycle,
        interaction.user.id,
    )
    await module.show_donation_confirmation(
        interaction,
        view,
        t(
            interaction,
            "donation.type.credit.confirm",
            amount=DonationOverview._format_amount(amount),
            unit=donation_type.unit,
        ),
        replace_prompt=replace_prompt,
    )


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
