from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t

if TYPE_CHECKING:
    from .selection import PurgeChannelSelection


class PurgeChannelConfirmation(discord.ui.View):
    def __init__(
        self,
        *,
        selection: PurgeChannelSelection,
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
        await interaction.response.send_message(
            t(interaction, "wz.setup.channel.selection_owner"), ephemeral=True
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
        await interaction.response.edit_message(
            content=t(interaction, "wz.setup.channel.cancelled"),
            view=None,
        )


class _ChannelSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        view: PurgeChannelSelection,
        placeholder: str,
        channels: list[discord.TextChannel],
        max_values: int,
        selected_ids: set[int],
    ) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=max(1, max_values),
            options=[
                discord.SelectOption(
                    label=channel.name[:100],
                    value=str(channel.id),
                    default=channel.id in selected_ids,
                )
                for channel in channels
            ],
        )
        self.purge_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.purge_view.select_channels(
            interaction,
            [int(channel_id) for channel_id in self.values],
        )


class _ChannelPageButton(discord.ui.Button):
    def __init__(
        self,
        *,
        view: PurgeChannelSelection,
        label: str,
        direction: int,
    ) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.selection = view
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selection.change_page(interaction, self.direction)


class _ChannelReviewButton(discord.ui.Button):
    def __init__(self, *, view: PurgeChannelSelection, label: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.selection = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selection.review(interaction)
