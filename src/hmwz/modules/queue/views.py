from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t

if TYPE_CHECKING:
    from .module import QueueModule


class QueueOverviewView(discord.ui.View):
    def __init__(self, module: QueueModule, channel_id: int) -> None:
        super().__init__(timeout=None)
        self.module = module
        self.channel_id = channel_id
        self.add_item(
            QueueButton(
                module,
                channel_id,
                action="join",
                label=t(module.guild, "queue.overview.join"),
                style=discord.ButtonStyle.success,
            )
        )
        self.add_item(
            QueueButton(
                module,
                channel_id,
                action="leave",
                label=t(module.guild, "queue.overview.leave"),
                style=discord.ButtonStyle.secondary,
            )
        )


class QueueButton(discord.ui.Button):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        *,
        action: str,
        label: str,
        style: discord.ButtonStyle,
    ) -> None:
        super().__init__(
            label=label,
            style=style,
            custom_id=f"queue:{action}:{channel_id}",
        )
        self.module = module
        self.channel_id = channel_id
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.handle_queue_action(interaction, self.channel_id, self.action)


class RunConfirmationView(discord.ui.View):
    def __init__(
        self, module: QueueModule, run_id: int, *, enabled: bool, completed: bool
    ) -> None:
        super().__init__(timeout=None)
        self.module = module
        self.run_id = run_id
        self.add_item(
            RunConfirmationButton(
                module,
                run_id,
                disabled=not enabled or completed,
            )
        )


class RunConfirmationButton(discord.ui.Button):
    def __init__(self, module: QueueModule, run_id: int, *, disabled: bool) -> None:
        super().__init__(
            label=t(module.guild, "queue.run.confirm"),
            style=discord.ButtonStyle.success,
            custom_id=f"queue:confirm:{run_id}",
            disabled=disabled,
        )
        self.module = module
        self.run_id = run_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.confirm_run(interaction, self.run_id)
