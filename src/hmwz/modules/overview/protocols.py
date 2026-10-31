"""Callback protocol for buttons attached to overview messages."""

from __future__ import annotations

from typing import Protocol

import discord


class OverviewButtonHandler(Protocol):
    """Callback contract for a button attached to an overview."""

    async def __call__(self, interaction: discord.Interaction) -> None: ...
