from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import discord

from hmwz.i18n import t

from .modes.protocol import QueuePool
from .repository import QueueMode, QueueStage, SeasonTask

if TYPE_CHECKING:
    from .module import QueueModule

StageAction = Literal["join", "vote"]


class QueueOverviewView(discord.ui.View):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        *,
        mode: QueueMode,
        pools: tuple[QueuePool, ...] = (),
    ) -> None:
        super().__init__(timeout=None)
        self.module = module
        self.channel_id = channel_id
        self.mode = mode
        if mode == "seasons":
            for index, pool in enumerate(pools):
                self.add_item(
                    SeasonToggleButton(
                        module,
                        channel_id,
                        pool.index,
                        pool.label,
                        row=index // 2,
                    )
                )
            return
        if mode == "stages":
            for index, pool in enumerate(pools):
                self.add_item(
                    StageToggleButton(
                        module,
                        channel_id,
                        pool.index,
                        pool.label,
                        row=index // 5,
                    )
                )
            self.add_item(
                QueueButton(
                    module,
                    channel_id,
                    action="vote",
                    label=t(module.guild, "queue.overview.early_start"),
                    style=discord.ButtonStyle.primary,
                    row=min(4, (len(pools) + 4) // 5),
                )
            )
            return
        self.add_item(
            QueueButton(
                module,
                channel_id,
                action="toggle",
                label=t(module.guild, "queue.overview.toggle"),
                style=discord.ButtonStyle.secondary,
            )
        )


class QueueButton(discord.ui.Button):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        *,
        action: StageAction | Literal["leave", "toggle"],
        label: str,
        style: discord.ButtonStyle,
        row: int | None = None,
    ) -> None:
        super().__init__(
            label=label,
            style=style,
            custom_id=f"queue:{action}:{channel_id}",
            row=row,
        )
        self.module = module
        self.channel_id = channel_id
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.handle_queue_action(interaction, self.channel_id, self.action)


class StageToggleButton(discord.ui.Button):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        stage_index: int,
        label: str,
        *,
        row: int,
    ) -> None:
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"queue:stage:toggle:{channel_id}:{stage_index}",
            row=row,
        )
        self.module = module
        self.channel_id = channel_id
        self.stage_index = stage_index

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.toggle_stage_membership(
            interaction, self.channel_id, self.stage_index
        )


class SeasonToggleButton(discord.ui.Button):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        season_index: int,
        name: str,
        *,
        row: int,
    ) -> None:
        super().__init__(
            label=name[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"queue:season:toggle:{channel_id}:{season_index}",
            row=row,
        )
        self.module = module
        self.channel_id = channel_id
        self.season_index = season_index

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.toggle_season_membership(
            interaction, self.channel_id, self.season_index
        )


class SeasonOverviewView(discord.ui.View):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        season_index: int,
        *,
        enabled: bool,
        completed: bool,
    ) -> None:
        super().__init__(timeout=None)
        self.add_item(
            SeasonOverviewGoalButton(
                module, channel_id, season_index, disabled=not enabled or completed
            )
        )


class SeasonOverviewGoalButton(discord.ui.Button):
    def __init__(
        self, module: QueueModule, channel_id: int, season_index: int, *, disabled: bool
    ) -> None:
        super().__init__(
            label=t(module.guild, "queue.season.confirm_task"),
            style=discord.ButtonStyle.success,
            custom_id=f"queue:season:goal:{channel_id}:{season_index}",
            disabled=disabled,
        )
        self.module = module
        self.channel_id = channel_id
        self.season_index = season_index

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.open_season_task_selection(
            interaction, self.channel_id, self.season_index
        )


class StageSelect(discord.ui.Select):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        stages: tuple[QueueStage, ...],
        action: StageAction,
    ) -> None:
        super().__init__(
            placeholder=t(module.guild, "queue.stage.select_placeholder"),
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=stage.name[:100], value=str(stage.index))
                for stage in stages[:25]
            ],
        )
        self.module = module
        self.channel_id = channel_id
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.handle_stage_action(
            interaction,
            self.channel_id,
            self.action,
            int(self.values[0]),
        )


class StageSelectView(discord.ui.View):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        stages: tuple[QueueStage, ...],
        action: StageAction,
    ) -> None:
        super().__init__(timeout=180)
        self.add_item(StageSelect(module, channel_id, stages, action))


class RunConfirmationView(discord.ui.View):
    def __init__(
        self, module: QueueModule, run_id: int, *, enabled: bool, completed: bool
    ) -> None:
        super().__init__(timeout=None)
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


class SeasonGoalView(discord.ui.View):
    def __init__(
        self, module: QueueModule, run_id: int, *, enabled: bool, completed: bool
    ) -> None:
        super().__init__(timeout=None)
        self.add_item(
            SeasonGoalButton(
                module,
                run_id,
                disabled=not enabled or completed,
            )
        )


class SeasonGoalButton(discord.ui.Button):
    def __init__(self, module: QueueModule, run_id: int, *, disabled: bool) -> None:
        super().__init__(
            label=t(module.guild, "queue.season.add_goal"),
            style=discord.ButtonStyle.success,
            custom_id=f"queue:goal:{run_id}",
            disabled=disabled,
        )
        self.module = module
        self.run_id = run_id

    async def callback(self, interaction: discord.Interaction) -> None:
        run = await self.module.queues.get_run(self.run_id)
        if run is None:
            await interaction.response.send_message(
                t(interaction, "queue.error.run_unavailable"), ephemeral=True
            )
            return
        await interaction.response.send_modal(SeasonGoalModal(self.module, self.run_id))


class SeasonGoalModal(discord.ui.Modal):
    def __init__(self, module: QueueModule, run_id: int) -> None:
        super().__init__(title=t(module.guild, "queue.season.goal_modal_title")[:45])
        self.module = module
        self.run_id = run_id
        self.goal_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(module.guild, "queue.season.goal_modal_label")[:45],
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )
        self.add_item(self.goal_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.module.record_season_goal(
            interaction, self.run_id, self.goal_input.value.strip()
        )


class SeasonTaskSelect(discord.ui.Select):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        season_index: int,
        tasks: tuple[SeasonTask, ...],
    ) -> None:
        super().__init__(
            placeholder=t(module.guild, "queue.season.task_select_placeholder"),
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=task.label[:100],
                    value=str(task.index),
                    description=f"{task.completed} / {task.completion_limit}",
                )
                for task in tasks
                if task.completed < task.completion_limit
            ],
        )
        self.module = module
        self.channel_id = channel_id
        self.season_index = season_index

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.open_season_task_dialog(
            interaction,
            self.channel_id,
            self.season_index,
            int(self.values[0]),
        )


class SeasonTaskSelectView(discord.ui.View):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        season_index: int,
        tasks: tuple[SeasonTask, ...],
    ) -> None:
        super().__init__(timeout=180)
        self.add_item(SeasonTaskSelect(module, channel_id, season_index, tasks))


class SeasonTaskCompletionModal(discord.ui.Modal):
    def __init__(
        self,
        module: QueueModule,
        channel_id: int,
        season_index: int,
        task_index: int,
    ) -> None:
        super().__init__(title=t(module.guild, "queue.season.task_modal_title")[:45])
        self.module = module
        self.channel_id = channel_id
        self.season_index = season_index
        self.task_index = task_index
        self.goal_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(module.guild, "queue.season.task_modal_label")[:45],
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False,
        )
        self.add_item(self.goal_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.module.record_season_task_completion(
            interaction,
            self.channel_id,
            self.season_index,
            self.task_index,
            self.goal_input.value.strip(),
        )


class EarlyVoteView(discord.ui.View):
    def __init__(self, module: QueueModule, vote_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(EarlyVoteButton(module, vote_id, True))
        self.add_item(EarlyVoteButton(module, vote_id, False))


class EarlyVoteButton(discord.ui.Button):
    def __init__(self, module: QueueModule, vote_id: int, approve: bool) -> None:
        super().__init__(
            label=t(
                module.guild,
                "queue.vote.approve" if approve else "queue.vote.reject",
            ),
            style=(
                discord.ButtonStyle.success if approve else discord.ButtonStyle.danger
            ),
            custom_id=f"queue:vote:{vote_id}:{int(approve)}",
        )
        self.module = module
        self.vote_id = vote_id
        self.approve = approve

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.cast_early_vote(interaction, self.vote_id, self.approve)
