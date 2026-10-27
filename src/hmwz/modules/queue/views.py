from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui import EphemeralView

if TYPE_CHECKING:
    from .module import QueueModule


class QueueOverviewView(discord.ui.View):
    def __init__(
        self,
        module: QueueModule,
        eruption_id: int,
        phases: tuple[tuple[int, int, str], ...],
    ) -> None:
        super().__init__(timeout=None)
        for phase_id, index, label in phases:
            self.add_item(
                PhaseSignupButton(module, eruption_id, phase_id, index, label)
            )


class PhaseSignupButton(discord.ui.Button):
    def __init__(
        self,
        module: QueueModule,
        eruption_id: int,
        phase_id: int,
        index: int,
        phase_label: str,
    ) -> None:
        super().__init__(
            label=f"📝 {phase_label}"[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"qsphase:signup:{eruption_id}:{phase_id}",
            row=(index - 1) // 5,
        )
        self.module = module
        self.eruption_id = eruption_id
        self.phase_id = phase_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.toggle_phase_signup(
            interaction,
            self.eruption_id,
            self.phase_id,
        )


class PhaseThreadView(discord.ui.View):
    def __init__(
        self,
        module: QueueModule,
        eruption_id: int,
        phase_id: int,
        *,
        enabled: bool,
    ) -> None:
        super().__init__(timeout=None)
        self.add_item(
            BaseDestructionButton(
                module,
                eruption_id,
                phase_id,
                disabled=not enabled,
            )
        )


class BaseDestructionButton(discord.ui.Button):
    def __init__(
        self,
        module: QueueModule,
        eruption_id: int,
        phase_id: int,
        *,
        disabled: bool,
    ) -> None:
        super().__init__(
            label=t(module.guild, "queue.destruction.open_modal"),
            style=discord.ButtonStyle.success,
            custom_id=f"qsphase:destroy:{eruption_id}:{phase_id}",
            disabled=disabled,
        )
        self.module = module
        self.eruption_id = eruption_id
        self.phase_id = phase_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.open_destruction_modal(
            interaction,
            self.eruption_id,
            self.phase_id,
        )


class BaseDestructionConfirmationView(EphemeralView):
    def __init__(
        self,
        module: QueueModule,
        eruption_id: int,
        phase_id: int,
    ) -> None:
        super().__init__(timeout=300)
        self.module = module
        self.eruption_id = eruption_id
        self.phase_id = phase_id
        self.add_item(BaseDestructionConfirmButton(self))


class BaseDestructionConfirmButton(discord.ui.Button):
    def __init__(self, view: BaseDestructionConfirmationView) -> None:
        super().__init__(
            label=t(view.module.guild, "queue.destruction.confirm"),
            style=discord.ButtonStyle.success,
            custom_id=f"qsphase:destroy:confirm:{view.eruption_id}:{view.phase_id}",
        )
        self.confirmation = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.confirmation.module.confirm_destruction(
            interaction,
            self.confirmation.eruption_id,
            self.confirmation.phase_id,
            "",
        )
