"""Rush duration buttons and quoted-price confirmation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import discord

from hmwz.emojis import emojis
from hmwz.i18n import t
from ...confirmation import DonationConfirmationView
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
                "donation.type.rush.ui.time_reduction_button",
                reduction=time_reduction,
                cost=DonationOverview._format_amount(price),
                unit=t(module.guild, "donation.type.rush.unit"),
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


class DonationRushConfirmationView(DonationConfirmationView):
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
        super().__init__(module, owner_id)
        self.channel_id = channel_id
        self.donation_type = donation_type
        self.duration_hours = duration_hours
        self.amount = amount
        self.expected_cycle = expected_cycle
        self.expected_start_at = expected_start_at
        self.quoted_at = quoted_at
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "donation_confirm":
                    item.custom_id = "donation_rush_confirm"
                    item.emoji = emojis.get("cristall", module.guild)
                else:
                    item.custom_id = "donation_rush_cancel"

    async def record(self, interaction: discord.Interaction) -> tuple[bool, bool]:
        return await self.module.record_rush_donation(
            interaction,
            self.channel_id,
            self.donation_type,
            self.duration_hours,
            self.amount,
            self.expected_cycle,
            self.expected_start_at,
            self.quoted_at,
        )


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
