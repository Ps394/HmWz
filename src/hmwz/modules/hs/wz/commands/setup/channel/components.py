from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.components.ephemeral_view import EphemeralView

if TYPE_CHECKING:
    from .selection import ChannelSelection


class ChannelConfirmation(EphemeralView):
    def __init__(
        self,
        *,
        selection: ChannelSelection,
        owner_id: int,
        selected_channel_ids: list[int],
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=180)
        self.selection = selection
        self.owner_id = owner_id
        self.selected_channel_ids = selected_channel_ids
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    context,
                    "wz.setup.channel.confirm_button"
                    if item.custom_id == "wz_channel_confirm"
                    else "wz.setup.channel.cancel_button",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "wz.setup.channel.selection_owner")
        )
        return False

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.primary,
        custom_id="wz_channel_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await self.selection.commit(interaction, self.selected_channel_ids)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_channel_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        self.selection.stop()
        await self.finish(interaction, t(interaction, "wz.setup.channel.cancelled"))
