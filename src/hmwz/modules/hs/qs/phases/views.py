"""Persistent controls of a phase thread."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ..models import Phase
from .bases.views import ReportButton, WithdrawButton

if TYPE_CHECKING:
    from ..module import QsModule


class PhaseView(discord.ui.View):
    """Persistent destroyed-base action without thread signup controls."""

    def __init__(self, module: QsModule, channel_id: int, phase: Phase) -> None:
        super().__init__(timeout=None)
        self.add_item(ReportButton(module, channel_id, phase.index))
        self.add_item(WithdrawButton(module, channel_id, phase.index))
