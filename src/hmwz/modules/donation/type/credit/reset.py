"""Credit donation cycle reset confirmation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_temporary_response, send_followup

from .. import reset_result_key

if TYPE_CHECKING:
    from ...module import DonationModule


class DonationCycleResetView(discord.ui.View):
    """Confirm a simple-donation cycle reset without deleting its history."""

    def __init__(self, module: DonationModule, channel_id: int, owner_id: int) -> None:
        super().__init__(timeout=120)
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    module.guild,
                    "donation.reset.confirm"
                    if item.custom_id == "donation_reset_confirm"
                    else "donation.delete.cancel",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await send_temporary_response(
            interaction, t(interaction, "donation.setup.owner_only")
        )
        return False

    @discord.ui.button(
        label="Start new cycle",
        style=discord.ButtonStyle.danger,
        custom_id="donation_reset_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        reset_done, messages_updated, export_failed = await self.module.reset_cycle(
            self.channel_id, rush_start_at=None
        )
        result_key = reset_result_key(
            reset_done, messages_updated, export_failed=export_failed
        )
        self.stop()
        await interaction.delete_original_response()
        result = await send_followup(
            interaction, t(interaction, result_key), ephemeral=True, wait=True
        )
        await result.delete(delay=5)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="donation_reset_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.defer(ephemeral=True)
        await interaction.delete_original_response()
