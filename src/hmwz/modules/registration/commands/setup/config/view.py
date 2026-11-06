"""Base view that restricts registration setup controls to their owner."""

from __future__ import annotations

import discord

from hmwz.ui.messages import send_initial_response
from hmwz.i18n import t


class RegistrationSetupView(discord.ui.View):
    """Restrict setup controls to the user who opened the panel."""

    def __init__(self, *, owner_id: int, timeout: float | None) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Allow only the user who opened the setup view to interact."""
        if interaction.user.id == self.owner_id:
            return True
        await send_initial_response(
            interaction,
            t(interaction, "wz.setup.config.owner_only"),
            ephemeral=True,
            delete_after=5,
        )
        return False
