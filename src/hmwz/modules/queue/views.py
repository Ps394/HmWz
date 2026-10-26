from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t

if TYPE_CHECKING:
    from .module import QueueModule


class QueueOverviewView(discord.ui.View):
    def __init__(
        self, module: QueueModule, eruption_id: int, phases: tuple[tuple[int, int], ...]
    ) -> None:
        super().__init__(timeout=None)
        for phase_id, index in phases:
            self.add_item(PhaseSignupButton(module, eruption_id, phase_id, index))


class PhaseSignupButton(discord.ui.Button):
    def __init__(
        self, module: QueueModule, eruption_id: int, phase_id: int, index: int
    ) -> None:
        super().__init__(
            label=t(module.guild, "queue.phase.signup", index=index),
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


class BaseDestructionModal(discord.ui.Modal):
    def __init__(
        self,
        module: QueueModule,
        eruption_id: int,
        phase_id: int,
        prompt: str,
    ) -> None:
        super().__init__(
            title=t(module.guild, "queue.destruction.modal_title"),
            timeout=300,
        )
        self.module = module
        self.eruption_id = eruption_id
        self.phase_id = phase_id
        self.details: discord.ui.TextInput = discord.ui.TextInput(
            label=prompt[:45],
            required=False,
            max_length=500,
            style=discord.TextStyle.short,
        )
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.module.confirm_destruction(
            interaction,
            self.eruption_id,
            self.phase_id,
            self.details.value,
        )
