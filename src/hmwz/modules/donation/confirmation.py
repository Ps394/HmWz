"""Single-use, owner-bound confirmations shared by both donation types."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.ui.messages import send_followup
from hmwz.i18n import t
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.messages import send_temporary_response

if TYPE_CHECKING:
    from .module import DonationModule


class DonationConfirmationView(EphemeralView):
    """Require an explicit confirmation of the user's latest donation."""

    def __init__(self, module: DonationModule, owner_id: int) -> None:
        super().__init__(timeout=180)
        self.module = module
        self.owner_id = owner_id
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    module.guild,
                    "donation.rush.confirm_button"
                    if item.custom_id == "donation_confirm"
                    else "donation.delete.cancel",
                )

    def _consume(self) -> bool:
        if self.module._pending_donations.get(self.owner_id) is not self:
            return False
        self.module._pending_donations.pop(self.owner_id)
        self.stop()
        return True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_temporary_response(
                interaction, t(interaction, "donation.confirm.owner_only")
            )
            return False
        if self.module._pending_donations.get(self.owner_id) is not self:
            await send_temporary_response(
                interaction, t(interaction, "donation.confirm.expired")
            )
            return False
        return True

    async def on_timeout(self) -> None:
        self._consume()
        await super().on_timeout()

    async def record(self, interaction: discord.Interaction) -> tuple[bool, bool]:
        """Persist the type-specific confirmed donation."""
        raise NotImplementedError

    @discord.ui.button(
        label="Confirm donation",
        style=discord.ButtonStyle.success,
        custom_id="donation_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self.interaction_check(interaction) or not self._consume():
            return
        await interaction.response.defer(ephemeral=True)
        saved, updated = await self.record(interaction)
        result_key = (
            "donation.error.save"
            if not saved
            else (
                "donation.success.saved"
                if updated
                else "donation.success.saved_overview_failed"
            )
        )
        await interaction.delete_original_response()
        result = await send_followup(
            interaction, t(interaction, result_key), ephemeral=True, wait=True
        )
        await result.delete(delay=5)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="donation_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self.interaction_check(interaction) or not self._consume():
            return
        await interaction.response.defer()
        await interaction.delete_original_response()
