from __future__ import annotations

from dataclasses import dataclass

import discord


@dataclass(frozen=True, slots=True)
class OverviewButton:
    """A persistent button displayed on an overview message."""

    button_id: str
    label: str
    style: discord.ButtonStyle = discord.ButtonStyle.primary
    row: int | None = None
