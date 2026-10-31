"""Rush duration buttons and quoted-price confirmation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import discord

from hmwz.emojis import emojis
from hmwz.i18n import t
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.messages import send_temporary_response as _send_temporary_response

from ...models import DonationType
from ...overview import DonationOverview
from .pricing import RUSH_BUTTON_DURATIONS_HOURS

if TYPE_CHECKING:
    from ...module import DonationModule


class DonationTimeReductionButton(discord.ui.Button):
    """Select a configured Rush duration before recording a donation."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        time_reduction: str,
        price: Decimal,
        *,
        replace_prompt: bool = False,
    ) -> None:
        super().__init__(
            label=t(
                module.guild,
                "donation.ui.time_reduction_button",
                reduction=time_reduction,
                cost=DonationOverview._format_amount(price),
                unit=t(module.guild, "donation.setup.crystals_unit"),
            )[:80],
            style=discord.ButtonStyle.primary,
            emoji=emojis.get("cristall", module.guild),
            custom_id=f"donation:time:{channel_id}:{time_reduction.removesuffix('h')}",
        )
        self.module = module
        self.channel_id = channel_id
        self.time_reduction = time_reduction
        self.replace_prompt = replace_prompt

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.replace_prompt:
            await self.module.start_donation(
                interaction,
                self.channel_id,
                time_reduction=self.time_reduction,
                replace_prompt=True,
            )
        else:
            await self.module.start_donation(
                interaction, self.channel_id, time_reduction=self.time_reduction
            )


class DonationTimeReductionView(discord.ui.View):
    """Offer available Rush durations in an ephemeral donation prompt."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_type: DonationType,
        rush_prices: dict[int, Decimal],
    ) -> None:
        super().__init__(timeout=180)
        for hours in RUSH_BUTTON_DURATIONS_HOURS:
            if hours not in rush_prices:
                continue
            self.add_item(
                DonationTimeReductionButton(
                    module,
                    channel_id,
                    f"{hours}h",
                    rush_prices[hours],
                    replace_prompt=True,
                )
            )


class DonationRushConfirmationView(EphemeralView):
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
                if item.custom_id == "donation_rush_confirm":
                    item.emoji = emojis.get("cristall", module.guild)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await _send_temporary_response(
            interaction, t(interaction, "donation.setup.owner_only")
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
        await interaction.delete_original_response()
        result_message = await interaction.followup.send(
            t(interaction, result_key), ephemeral=True, wait=True
        )
        await result_message.delete(delay=5)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="donation_rush_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.defer()
        await interaction.delete_original_response()


def add_overview_controls(
    view: discord.ui.View,
    module: DonationModule,
    channel_id: int,
    *,
    rush_open: bool,
    rush_prices: dict[int, Decimal],
) -> None:
    """Attach only available Rush donation controls to a persistent overview."""
    for hours in RUSH_BUTTON_DURATIONS_HOURS:
        if rush_open and hours in rush_prices:
            view.add_item(
                DonationTimeReductionButton(
                    module, channel_id, f"{hours}h", rush_prices[hours]
                )
            )
