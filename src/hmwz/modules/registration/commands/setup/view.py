from __future__ import annotations

import discord

from hmwz.i18n import t


class RegistrationSetupView(discord.ui.View):
    """Restrict setup controls to the user who opened the panel."""

    def __init__(self, *, owner_id: int, timeout: float | None) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "wz.setup.config.owner_only"),
            ephemeral=True,
        )
        return False
