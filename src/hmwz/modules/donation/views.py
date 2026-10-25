from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t

from .overview import DonationOverview
from .repository import DEFAULT_DONATION_CHOICES, DonationType
from .rush_pricing import RUSH_DURATIONS_HOURS
from .validation import parse_amount

if TYPE_CHECKING:
    from .module import DonationModule


class DonationRecordButton(discord.ui.Button):
    """Button that starts the donation flow for its channel."""

    def __init__(self, module: DonationModule, channel_id: int) -> None:
        super().__init__(
            label=t(module.guild, "donation.ui.record_button"),
            style=discord.ButtonStyle.success,
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
    ) -> None:
        super().__init__(
            label=(f"{DonationOverview._format_amount(amount)} {donation_type.unit}")[
                :80
            ],
            style=discord.ButtonStyle.primary,
            custom_id=f"donation:amount:{channel_id}:{index}",
            row=index // 5,
        )
        self.module = module
        self.channel_id = channel_id
        self.donation_type = donation_type
        self.amount = amount

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        saved, messages_updated = await self.module.record_donation(
            interaction,
            self.channel_id,
            self.donation_type,
            self.amount,
            time_reduction=None,
        )
        result_key = (
            "donation.error.save"
            if not saved
            else (
                "donation.success.saved"
                if messages_updated
                else "donation.success.saved_overview_failed"
            )
        )
        await interaction.followup.send(t(interaction, result_key), ephemeral=True)


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
                )
            )


class DonationTimeReductionButton(discord.ui.Button):
    """Select a configured Rush duration before recording a donation."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        time_reduction: str,
    ) -> None:
        super().__init__(
            label=t(
                module.guild,
                "donation.ui.time_reduction_button",
                reduction=time_reduction,
            )[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"donation:time:{channel_id}:{time_reduction.removesuffix('h')}",
        )
        self.module = module
        self.channel_id = channel_id
        self.time_reduction = time_reduction

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.start_donation(
            interaction, self.channel_id, time_reduction=self.time_reduction
        )


class DonationOverviewView(discord.ui.View):
    """Persistent donation controls attached to a channel overview."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_type: DonationType,
        *,
        rush_open: bool = True,
        rush_zone_index: int | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.donation_type = donation_type
        self.rush_open = rush_open
        self.rush_zone_index = rush_zone_index
        if donation_type.kind == "time_reduction":
            for reduction in (
                (f"{hours}h" for hours in RUSH_DURATIONS_HOURS) if rush_open else ()
            ):
                self.add_item(
                    DonationTimeReductionButton(module, channel_id, reduction)
                )
        elif donation_type.input_mode == "choice" and donation_type.choices:
            for index, choice in enumerate(donation_type.choices):
                self.add_item(
                    DonationAmountOptionButton(
                        module,
                        channel_id,
                        donation_type,
                        Decimal(choice),
                        index,
                    )
                )
        else:
            self.add_item(DonationRecordButton(module, channel_id))


class DonationTimeReductionView(discord.ui.View):
    """Offer configured Rush durations when recording via slash command."""

    def __init__(
        self, module: DonationModule, channel_id: int, donation_type: DonationType
    ) -> None:
        super().__init__(timeout=180)
        for reduction in (f"{hours}h" for hours in RUSH_DURATIONS_HOURS):
            self.add_item(DonationTimeReductionButton(module, channel_id, reduction))


class DonationRushConfirmationView(discord.ui.View):
    """Confirm a fixed-price Rush option before recording the donation."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_type: DonationType,
        duration_hours: int,
        amount: Decimal,
        expected_cycle: int,
        expected_start_at: datetime,
        quoted_at: datetime,
        owner_id: int,
    ) -> None:
        super().__init__(timeout=180)
        self.module = module
        self.channel_id = channel_id
        self.donation_type = donation_type
        self.duration_hours = duration_hours
        self.amount = amount
        self.expected_cycle = expected_cycle
        self.expected_start_at = expected_start_at
        self.quoted_at = quoted_at
        self.owner_id = owner_id
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    module.guild,
                    "donation.rush.confirm_button"
                    if item.custom_id == "donation_rush_confirm"
                    else "donation.delete.cancel",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "donation.setup.owner_only"), ephemeral=True
        )
        return False

    @discord.ui.button(
        label="Confirm donation",
        style=discord.ButtonStyle.success,
        custom_id="donation_rush_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        saved, messages_updated = await self.module.record_rush_donation(
            interaction,
            self.channel_id,
            self.donation_type,
            self.duration_hours,
            self.amount,
            self.expected_cycle,
            self.expected_start_at,
            self.quoted_at,
        )
        result_key = (
            "donation.error.save"
            if not saved
            else (
                "donation.success.saved"
                if messages_updated
                else "donation.success.saved_overview_failed"
            )
        )
        self.stop()
        await interaction.followup.send(t(interaction, result_key), ephemeral=True)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="donation_rush_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=t(interaction, "donation.rush.cancelled"), view=None
        )


class DonationDeleteConfirmationView(discord.ui.View):
    """Require explicit confirmation before deleting donation history."""

    def __init__(
        self,
        *,
        module: DonationModule,
        channel_id: int,
        owner_id: int,
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=120)
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    context,
                    "donation.delete.confirm"
                    if item.custom_id == "donation_delete_confirm"
                    else "donation.delete.cancel",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "donation.delete.owner_only"), ephemeral=True
        )
        return False

    @discord.ui.button(
        label="Delete permanently",
        style=discord.ButtonStyle.danger,
        custom_id="donation_delete_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        removed = await self.module.delete_channel(self.channel_id)
        self.stop()
        await interaction.edit_original_response(
            content=t(
                interaction,
                "donation.delete.complete" if removed else "donation.error.delete",
            ),
            view=None,
        )

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="donation_delete_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=t(interaction, "donation.delete.cancelled"), view=None
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
        if not await self._is_valid_time_reduction(interaction):
            return
        if not await self._is_valid_choice(interaction, amount):
            return
        await self._record(interaction, amount)

    async def _parse_amount(self, interaction: discord.Interaction) -> Decimal | None:
        try:
            return parse_amount(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_amount"), ephemeral=True
            )
            return None

    async def _is_valid_time_reduction(self, interaction: discord.Interaction) -> bool:
        if self.donation_type.kind != "time_reduction":
            return True
        if self.time_reduction in self.donation_type.time_reductions:
            return True
        await interaction.response.send_message(
            t(interaction, "donation.error.invalid_time_choice"), ephemeral=True
        )
        return False

    async def _is_valid_choice(
        self, interaction: discord.Interaction, amount: Decimal
    ) -> bool:
        if self.donation_type.input_mode != "choice" or amount in {
            Decimal(choice) for choice in self.donation_type.choices
        }:
            return True
        await interaction.response.send_message(
            t(interaction, "donation.error.invalid_amount_choice"), ephemeral=True
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
        await interaction.followup.send(
            t(interaction, self._result_key(saved, messages_updated)),
            ephemeral=True,
        )

    @staticmethod
    def _result_key(saved: bool, messages_updated: bool) -> str:
        if not saved:
            return "donation.error.save"
        if messages_updated:
            return "donation.success.saved"
        return "donation.success.saved_overview_failed"
