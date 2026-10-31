"""Shared overview routing and donation-system deletion controls."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.messages import send_temporary_response as _send_temporary_response

from .models import DonationType
from .type.credit.views import add_overview_controls as add_credit_controls
from .type.rush.views import add_overview_controls as add_rush_controls

if TYPE_CHECKING:
    from .module import DonationModule


class DonationOverviewView(discord.ui.View):
    """Persistent overview delegating entry controls to the configured type."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_type: DonationType,
        *,
        rush_open: bool = True,
        rush_prices: dict[int, Decimal] | None = None,
        donations_enabled: bool = True,
    ) -> None:
        super().__init__(timeout=None)
        self.donation_type = donation_type
        self.rush_open = rush_open
        self.rush_prices = rush_prices or {}
        self.donations_enabled = donations_enabled
        if not donations_enabled:
            return
        if donation_type.kind == "time_reduction":
            add_rush_controls(
                self,
                module,
                channel_id,
                rush_open=rush_open,
                rush_prices=self.rush_prices,
            )
        else:
            add_credit_controls(self, module, channel_id, donation_type)


class DonationDeleteConfirmationView(EphemeralView):
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
        await _send_temporary_response(
            interaction, t(interaction, "donation.delete.owner_only")
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
        await interaction.delete_original_response()
        result = await interaction.followup.send(
            t(
                interaction,
                "donation.delete.complete" if removed else "donation.error.delete",
            ),
            ephemeral=True,
            wait=True,
        )
        await result.delete(delay=5)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="donation_delete_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.defer(ephemeral=True)
        await interaction.delete_original_response()
