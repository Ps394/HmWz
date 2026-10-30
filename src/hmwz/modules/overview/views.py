from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord

from hmwz.modules.overview.models import Overview

OverviewButtonCallback = Callable[[discord.Interaction, str, str], Awaitable[None]]


class OverviewButton(discord.ui.Button):
    """Persistent Discord button that dispatches through the overview module."""

    def __init__(
        self,
        *,
        overview: Overview,
        button_id: str,
        label: str,
        style: discord.ButtonStyle,
        row: int | None,
        callback: OverviewButtonCallback,
    ) -> None:
        super().__init__(
            label=label,
            style=style,
            custom_id=f"overview:{overview.overview_id}:{button_id}",
            row=row,
        )
        self._overview_id = overview.overview_id
        self._button_id = button_id
        self._callback = callback

    async def callback(self, interaction: discord.Interaction) -> None:
        """Delegate the button interaction to its owning overview module."""
        await self._callback(interaction, self._overview_id, self._button_id)


class OverviewView(discord.ui.View):
    """Persistent view for the buttons configured on an overview."""

    def __init__(
        self,
        overview: Overview,
        callback: OverviewButtonCallback,
    ) -> None:
        super().__init__(timeout=None)
        for button in overview.buttons:
            self.add_item(
                OverviewButton(
                    overview=overview,
                    button_id=button.button_id,
                    label=button.label,
                    style=button.style,
                    row=button.row,
                    callback=callback,
                )
            )
