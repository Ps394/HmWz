from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from hmwz.i18n import t

from .repository import QueueConfiguration, QueueMode
from .rules import season_start_timestamp, valid_run_range

if TYPE_CHECKING:
    from .module import QueueModule


@dataclass(slots=True)
class QueueSetupDraft:
    module: QueueModule
    channel_id: int
    owner_id: int
    mode: QueueMode
    configuration: QueueConfiguration | None = None
    mode_change_confirmed: bool = False
    title: str = ""
    description: str = ""
    min_players: int = 1
    max_players: int = 5
    confirmation_delay_minutes: int = 30
    ping_participants: bool = False
    stages: list[str] = field(default_factory=list)
    stage_prefix: str = ""
    seasons: list[str] = field(default_factory=list)
    season_goal_limit: int = 1
    season_goal_description: str = ""
    season_start_date: str = ""
    timezone: str = "Europe/Berlin"
    season_duration_hours: int = 24
    season_tasks: list[tuple[str, int]] = field(default_factory=list)


async def create_draft(
    module: QueueModule,
    channel_id: int,
    owner_id: int,
    mode: QueueMode,
    configuration: QueueConfiguration | None,
) -> QueueSetupDraft:
    draft = QueueSetupDraft(
        module=module,
        channel_id=channel_id,
        owner_id=owner_id,
        mode=mode,
        configuration=configuration,
        title=configuration.title if configuration else "",
        description=configuration.description if configuration else "",
        min_players=configuration.min_players if configuration else 1,
        max_players=configuration.max_players if configuration else 5,
        confirmation_delay_minutes=(
            configuration.confirmation_delay_minutes if configuration else 30
        ),
        ping_participants=configuration.ping_participants if configuration else False,
        timezone=configuration.timezone if configuration else "Europe/Berlin",
        stage_prefix=configuration.stage_prefix if configuration else "",
        season_duration_hours=(
            configuration.season_duration_hours if configuration else 24
        ),
        season_start_date=(
            configuration.season_start_date
            if configuration and configuration.season_start_date
            else datetime.now(
                ZoneInfo(configuration.timezone if configuration else "Europe/Berlin")
            )
            .date()
            .isoformat()
        ),
    )
    if configuration is None or configuration.mode != mode:
        return draft
    if mode == "stages":
        stages = await module.queues.get_stages(
            guild=module.guild, channel_id=channel_id
        )
        draft.stages = [stage.name for stage in stages]
    elif mode == "seasons":
        seasons = await module.queues.get_seasons(
            guild=module.guild, channel_id=channel_id
        )
        draft.seasons = [
            season.name
            for season in seasons
            if len(season.name) == 5
            and season.name[2:] == ":00"
            and season.name[:2].isdigit()
            and 0 <= int(season.name[:2]) <= 23
        ]
        draft.season_tasks = [
            (task.label, task.completion_limit)
            for task in await module.queues.get_season_tasks(
                guild=module.guild, channel_id=channel_id
            )
        ]
        if not draft.season_tasks and seasons:
            draft.season_tasks = [(seasons[0].goal_description, seasons[0].goal_limit)]
    return draft


def panel_content(draft: QueueSetupDraft, interaction: discord.Interaction) -> str:
    mode_name = t(interaction, f"queue.wizard.mode_{draft.mode}")
    title = draft.title or t(interaction, "queue.wizard.default_title")
    description_status = t(
        interaction,
        "queue.wizard.text_custom"
        if draft.description
        else "queue.wizard.optional_empty",
    )
    mode_details = ""
    if draft.mode == "seasons":
        task_summary = ", ".join(
            f"{label}: {limit}" for label, limit in draft.season_tasks
        )
        if len(task_summary) > 700:
            task_summary = f"{task_summary[:697]}..."
        mode_details = t(
            interaction,
            "queue.wizard.seasons_status",
            hours=", ".join(draft.seasons),
            start_date=draft.season_start_date,
            timezone=draft.timezone,
            duration=draft.season_duration_hours,
            tasks=task_summary or t(interaction, "queue.wizard.optional_empty"),
        )
    else:
        mode_details = t(
            interaction,
            "queue.wizard.range_status",
            minimum=draft.min_players,
            maximum=draft.max_players,
        )
        if draft.mode == "stages":
            mode_details = (
                t(
                    interaction,
                    "queue.wizard.stages_status",
                    count=len(draft.stages),
                    prefix=draft.stage_prefix,
                )
                + "\n"
                + mode_details
            )
    return t(
        interaction,
        "queue.wizard.panel",
        mode=mode_name,
        title=title,
        description=description_status,
        ping=t(
            interaction,
            "queue.wizard.ping_enabled"
            if draft.ping_participants
            else "queue.wizard.ping_disabled",
        ),
        mode_details=mode_details,
    )


class QueueSetupModeSelect(discord.ui.Select):
    def __init__(self, config_view: QueueConfigView) -> None:
        draft = config_view.draft
        options = [
            discord.SelectOption(
                label=t(draft.module.guild, f"queue.wizard.mode_{mode}"),
                value=mode,
                default=draft.mode == mode,
            )
            for mode in ("continuous", "stages", "seasons")
        ]
        super().__init__(
            placeholder=t(draft.module.guild, "queue.wizard.mode_placeholder"),
            min_values=1,
            max_values=1,
            options=options,
        )
        self.config_view = config_view

    async def callback(self, interaction: discord.Interaction) -> None:
        mode = self.values[0]
        if mode == "continuous":
            selected_mode: QueueMode = "continuous"
        elif mode == "stages":
            selected_mode = "stages"
        elif mode == "seasons":
            selected_mode = "seasons"
        else:
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_configuration"), ephemeral=True
            )
            return
        if selected_mode == self.config_view.draft.mode:
            await interaction.response.edit_message(
                content=panel_content(self.config_view.draft, interaction),
                view=self.config_view,
            )
            return
        if (
            self.config_view.draft.configuration is not None
            and selected_mode != self.config_view.draft.configuration.mode
        ):
            await interaction.response.edit_message(
                content=t(interaction, "queue.wizard.mode_change_confirm"),
                view=QueueModeChangeConfirmationView(self.config_view, selected_mode),
            )
            return
        draft = await _create_switched_draft(self.config_view.draft, selected_mode)
        draft.title = self.config_view.draft.title
        draft.description = self.config_view.draft.description
        draft.min_players = self.config_view.draft.min_players
        draft.max_players = self.config_view.draft.max_players
        draft.confirmation_delay_minutes = (
            self.config_view.draft.confirmation_delay_minutes
        )
        await interaction.response.edit_message(
            content=panel_content(draft, interaction),
            view=QueueConfigView(draft),
        )


async def _create_switched_draft(
    current: QueueSetupDraft, selected_mode: QueueMode
) -> QueueSetupDraft:
    draft = await create_draft(
        current.module,
        current.channel_id,
        current.owner_id,
        selected_mode,
        None,
    )
    draft.configuration = current.configuration
    draft.title = current.title
    draft.description = current.description
    draft.min_players = current.min_players
    draft.max_players = current.max_players
    draft.confirmation_delay_minutes = current.confirmation_delay_minutes
    draft.ping_participants = current.ping_participants
    draft.mode_change_confirmed = current.configuration is not None
    return draft


class QueueModeChangeConfirmationView(discord.ui.View):
    def __init__(self, config_view: QueueConfigView, selected_mode: QueueMode) -> None:
        super().__init__(timeout=180)
        self.config_view = config_view
        self.selected_mode = selected_mode
        self.add_item(QueueModeChangeConfirmButton(self))
        self.add_item(QueueModeChangeCancelButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.config_view.draft.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "queue.wizard.owner_only"), ephemeral=True
        )
        return False


class QueueModeChangeConfirmButton(discord.ui.Button):
    def __init__(self, confirmation_view: QueueModeChangeConfirmationView) -> None:
        super().__init__(
            label=t(
                confirmation_view.config_view.draft.module.guild,
                "queue.wizard.mode_change_confirm_button",
            ),
            style=discord.ButtonStyle.danger,
        )
        self.confirmation_view = confirmation_view

    async def callback(self, interaction: discord.Interaction) -> None:
        draft = await _create_switched_draft(
            self.confirmation_view.config_view.draft,
            self.confirmation_view.selected_mode,
        )
        draft.mode_change_confirmed = True
        await interaction.response.edit_message(
            content=panel_content(draft, interaction),
            view=QueueConfigView(draft),
        )
        self.confirmation_view.stop()


class QueueModeChangeCancelButton(discord.ui.Button):
    def __init__(self, confirmation_view: QueueModeChangeConfirmationView) -> None:
        super().__init__(
            label=t(
                confirmation_view.config_view.draft.module.guild,
                "queue.wizard.mode_change_cancel_button",
            ),
            style=discord.ButtonStyle.secondary,
        )
        self.confirmation_view = confirmation_view

    async def callback(self, interaction: discord.Interaction) -> None:
        draft = self.confirmation_view.config_view.draft
        await interaction.response.edit_message(
            content=panel_content(draft, interaction),
            view=self.confirmation_view.config_view,
        )
        self.confirmation_view.stop()


class QueueConfigButton(discord.ui.Button):
    def __init__(self, config_view: QueueConfigView, action: str, row: int) -> None:
        labels = {
            "title": "queue.wizard.edit_title",
            "description": "queue.wizard.edit_description",
            "range": "queue.wizard.edit_range",
            "ping": "queue.wizard.toggle_ping",
            "mode": (
                "queue.wizard.edit_stages"
                if config_view.draft.mode == "stages"
                else "queue.wizard.edit_seasons"
            ),
            "schedule": "queue.wizard.edit_season_schedule",
            "duration": "queue.wizard.edit_season_duration",
            "tasks": "queue.wizard.edit_season_tasks",
            "save": "queue.wizard.save",
        }
        super().__init__(
            label=t(config_view.draft.module.guild, labels[action]),
            style=(
                discord.ButtonStyle.success
                if action == "save"
                else discord.ButtonStyle.primary
            ),
            custom_id=f"queue:setup:{action}",
            row=row,
        )
        self.config_view = config_view
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.config_view.handle_action(interaction, self.action)


class QueueConfigView(discord.ui.View):
    def __init__(self, draft: QueueSetupDraft) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        self.add_item(QueueSetupModeSelect(self))
        actions = ["title", "description", "ping"]
        if draft.mode != "seasons":
            actions.append("range")
        for action in actions:
            self.add_item(QueueConfigButton(self, action, row=1))
        if draft.mode == "stages":
            self.add_item(QueueConfigButton(self, "mode", row=2))
        elif draft.mode == "seasons":
            self.add_item(QueueConfigButton(self, "mode", row=2))
            self.add_item(QueueConfigButton(self, "schedule", row=2))
            self.add_item(QueueConfigButton(self, "duration", row=2))
            self.add_item(QueueConfigButton(self, "tasks", row=2))
        self.add_item(QueueConfigButton(self, "save", row=3))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.draft.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "queue.wizard.owner_only"), ephemeral=True
        )
        return False

    async def handle_action(
        self, interaction: discord.Interaction, action: str
    ) -> None:
        if action in ("title", "description"):
            await interaction.response.send_modal(QueueTextModal(self.draft, action))
        elif action == "range":
            await interaction.response.send_modal(QueueRangeModal(self.draft))
        elif action == "ping":
            self.draft.ping_participants = not self.draft.ping_participants
            await interaction.response.edit_message(
                content=panel_content(self.draft, interaction), view=self
            )
        elif action == "mode" and self.draft.mode == "stages":
            await interaction.response.send_modal(QueueStageCountModal(self.draft))
        elif action == "mode" and self.draft.mode == "seasons":
            await interaction.response.send_message(
                t(interaction, "queue.wizard.select_season_hours"),
                view=QueueSeasonHoursView(self.draft),
                ephemeral=True,
            )
        elif action == "duration" and self.draft.mode == "seasons":
            await interaction.response.send_message(
                t(interaction, "queue.wizard.select_season_duration"),
                view=QueueSeasonDurationView(self.draft, self),
                ephemeral=True,
            )
        elif action == "tasks" and self.draft.mode == "seasons":
            await interaction.response.send_modal(QueueSeasonTasksModal(self.draft))
        elif action == "schedule" and self.draft.mode == "seasons":
            await interaction.response.send_message(
                calendar_content(self.draft, interaction),
                view=QueueSeasonScheduleView(self.draft, self),
                ephemeral=True,
            )
        elif action == "save":
            await self.save(interaction)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=panel_content(self.draft, interaction), view=self
        )

    async def save(self, interaction: discord.Interaction) -> None:
        if self.draft.mode == "stages" and not self.draft.stages:
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_stage_count"), ephemeral=True
            )
            return
        if self.draft.mode == "seasons" and (
            not 1 <= len(self.draft.seasons) <= 6
            or not self.draft.season_tasks
            or self.draft.season_duration_hours not in {12, 24, 36, 48, 60, 72}
            or not self.draft.season_start_date
            or any(
                season_start_timestamp(
                    self.draft.season_start_date, season, self.draft.timezone
                )
                is None
                for season in self.draft.seasons
            )
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_season"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        success = await self.draft.module.configure(
            channel_id=self.draft.channel_id,
            title=self.draft.title,
            description=self.draft.description,
            min_players=self.draft.min_players,
            max_players=self.draft.max_players,
            mode=self.draft.mode,
            confirmation_delay_minutes=self.draft.confirmation_delay_minutes,
            ping_participants=self.draft.ping_participants,
            stages=tuple(self.draft.stages),
            stage_prefix=self.draft.stage_prefix,
            seasons=tuple(self.draft.seasons),
            season_goal_limit=(
                self.draft.season_tasks[0][1] if self.draft.season_tasks else 1
            ),
            season_goal_description=(
                self.draft.season_tasks[0][0] if self.draft.season_tasks else ""
            ),
            season_start_date=(
                self.draft.season_start_date if self.draft.mode == "seasons" else None
            ),
            timezone=self.draft.timezone,
            season_duration_hours=self.draft.season_duration_hours,
            season_tasks=tuple(self.draft.season_tasks),
            confirmed_mode_change=self.draft.mode_change_confirmed,
        )
        key = "queue.wizard.saved" if success else "queue.error.configuration_failed"
        if success:
            await interaction.edit_original_response(
                content=t(interaction, key),
                view=None,
            )
            self.stop()
        else:
            await interaction.followup.send(t(interaction, key), ephemeral=True)


class QueueTextModal(discord.ui.Modal):
    def __init__(self, draft: QueueSetupDraft, field_name: str) -> None:
        label_key = (
            "queue.wizard.title_label"
            if field_name == "title"
            else "queue.wizard.text_label"
        )
        modal_title = (
            "queue.wizard.title_modal"
            if field_name == "title"
            else "queue.wizard.description_modal"
        )
        super().__init__(title=t(draft.module.guild, modal_title)[:45])
        self.draft = draft
        self.config_view = QueueConfigView(draft)
        value = draft.title if field_name == "title" else draft.description
        self.text_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, label_key)[:45],
            default=value,
            style=(
                discord.TextStyle.short
                if field_name == "title"
                else discord.TextStyle.paragraph
            ),
            required=False,
            max_length=256 if field_name == "title" else 4000,
        )
        self.field_name = field_name
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = self.text_input.value.strip()
        if self.field_name == "title":
            self.draft.title = value
        else:
            self.draft.description = value
        await self.config_view.refresh(interaction)


class QueueRangeModal(discord.ui.Modal):
    def __init__(self, draft: QueueSetupDraft) -> None:
        super().__init__(title=t(draft.module.guild, "queue.wizard.range_title")[:45])
        self.draft = draft
        self.config_view = QueueConfigView(draft)
        self.min_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.min_label")[:45],
            default=str(draft.min_players),
            max_length=3,
        )
        self.max_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.max_label")[:45],
            default=str(draft.max_players),
            max_length=3,
        )
        self.add_item(self.min_input)
        self.add_item(self.max_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            minimum = int(self.min_input.value.strip())
            maximum = int(self.max_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_range"), ephemeral=True
            )
            return
        if not valid_run_range(minimum, maximum):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_range"), ephemeral=True
            )
            return
        self.draft.min_players = minimum
        self.draft.max_players = maximum
        await self.config_view.refresh(interaction)


class QueueDelayModal(discord.ui.Modal):
    def __init__(self, draft: QueueSetupDraft) -> None:
        super().__init__(title=t(draft.module.guild, "queue.wizard.delay_title")[:45])
        self.draft = draft
        self.config_view = QueueConfigView(draft)
        self.delay_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.delay_label")[:45],
            default=str(draft.confirmation_delay_minutes),
            max_length=5,
        )
        self.add_item(self.delay_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            delay = int(self.delay_input.value.strip())
        except ValueError:
            delay = -1
        if not 0 <= delay <= 10080:
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_timing"), ephemeral=True
            )
            return
        self.draft.confirmation_delay_minutes = delay
        await self.config_view.refresh(interaction)


class QueueStageCountModal(discord.ui.Modal):
    def __init__(self, draft: QueueSetupDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "queue.wizard.stage_count_title")[:45]
        )
        self.draft = draft
        self.config_view = QueueConfigView(draft)
        self.count_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.stage_count_label")[:45],
            default=str(len(draft.stages) or 12),
            max_length=2,
        )
        self.prefix_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.stage_prefix_label")[:45],
            default=draft.stage_prefix,
            required=False,
            max_length=78,
        )
        self.add_item(self.count_input)
        self.add_item(self.prefix_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            count = int(self.count_input.value.strip())
        except ValueError:
            count = 0
        if not 1 <= count <= 24:
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_stage_count"), ephemeral=True
            )
            return
        self.draft.stage_prefix = self.prefix_input.value.strip()
        self.draft.stages = [
            f"{self.draft.stage_prefix}{stage_number}"
            for stage_number in range(1, count + 1)
        ]
        await self.config_view.refresh(interaction)


class QueueSeasonHoursSelect(discord.ui.Select):
    def __init__(self, draft: QueueSetupDraft) -> None:
        current_hours = set(draft.seasons)
        super().__init__(
            placeholder=t(draft.module.guild, "queue.wizard.season_hours_placeholder"),
            min_values=1,
            max_values=6,
            options=[
                discord.SelectOption(
                    label=f"{hour:02}:00",
                    value=f"{hour:02}:00",
                    default=f"{hour:02}:00" in current_hours,
                )
                for hour in range(24)
            ],
        )
        self.draft = draft

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            QueueSeasonTasksModal(
                self.draft,
                tuple(sorted(self.values)),
            )
        )


class QueueSeasonHoursView(discord.ui.View):
    def __init__(self, draft: QueueSetupDraft) -> None:
        super().__init__(timeout=300)
        self.add_item(QueueSeasonHoursSelect(draft))


class QueueSeasonDurationSelect(discord.ui.Select):
    def __init__(
        self, draft: QueueSetupDraft, config_view: QueueConfigView | None = None
    ) -> None:
        super().__init__(
            placeholder=t(
                draft.module.guild, "queue.wizard.season_duration_placeholder"
            ),
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=t(
                        draft.module.guild,
                        "queue.wizard.season_duration_option",
                        hours=hours,
                    ),
                    value=str(hours),
                    default=draft.season_duration_hours == hours,
                )
                for hours in (12, 24, 36, 48, 60, 72)
            ],
        )
        self.draft = draft
        self.config_view = config_view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.draft.season_duration_hours = int(self.values[0])
        if self.config_view is not None:
            await interaction.response.edit_message(
                content=panel_content(self.draft, interaction),
                view=self.config_view,
            )
            return
        await interaction.response.send_message(
            t(
                interaction,
                "queue.wizard.season_duration_saved",
                hours=self.draft.season_duration_hours,
            ),
            ephemeral=True,
        )


class QueueSeasonDurationView(discord.ui.View):
    def __init__(self, draft: QueueSetupDraft, config_view: QueueConfigView) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        self.add_item(QueueSeasonDurationSelect(draft, config_view))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.draft.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "queue.wizard.owner_only"), ephemeral=True
        )
        return False


def calendar_content(
    draft: QueueSetupDraft, interaction: discord.Interaction, month: date | None = None
) -> str:
    visible_month = month or date.fromisoformat(draft.season_start_date)
    weekday_labels = t(interaction, "queue.wizard.calendar_weekdays")
    rows = [" ".join(weekday_labels.split())]
    rows.extend(
        " ".join(f"{day:02}" if day else "  " for day in week)
        for week in calendar.monthcalendar(visible_month.year, visible_month.month)
    )
    return t(
        interaction,
        "queue.wizard.season_schedule_panel",
        month=visible_month.strftime("%Y-%m"),
        calendar="\n".join(rows),
        start_date=draft.season_start_date,
        timezone=draft.timezone,
    )


class QueueSeasonDaysSelect(discord.ui.Select):
    def __init__(self, schedule_view: QueueSeasonScheduleView) -> None:
        self.schedule_view = schedule_view
        days_in_month = calendar.monthrange(
            schedule_view.visible_month.year, schedule_view.visible_month.month
        )[1]
        first_day = 1 if schedule_view.day_page == 0 else 26
        last_day = (
            min(25, days_in_month) if schedule_view.day_page == 0 else days_in_month
        )
        super().__init__(
            placeholder=t(
                schedule_view.draft.module.guild, "queue.wizard.calendar_day"
            ),
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=f"{day:02}",
                    value=date(
                        schedule_view.visible_month.year,
                        schedule_view.visible_month.month,
                        day,
                    ).isoformat(),
                    default=(
                        schedule_view.draft.season_start_date
                        == date(
                            schedule_view.visible_month.year,
                            schedule_view.visible_month.month,
                            day,
                        ).isoformat()
                    ),
                )
                for day in range(first_day, last_day + 1)
            ],
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.schedule_view.draft.season_start_date = self.values[0]
        await interaction.response.edit_message(
            content=calendar_content(
                self.schedule_view.draft,
                interaction,
                self.schedule_view.visible_month,
            ),
            view=self.schedule_view,
        )


class QueueSeasonMonthButton(discord.ui.Button):
    def __init__(self, schedule_view: QueueSeasonScheduleView, direction: int) -> None:
        super().__init__(
            label=t(
                schedule_view.draft.module.guild,
                "queue.wizard.calendar_previous"
                if direction < 0
                else "queue.wizard.calendar_next",
            ),
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        self.schedule_view = schedule_view
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        month_number = (
            self.schedule_view.visible_month.year * 12
            + self.schedule_view.visible_month.month
            - 1
            + self.direction
        )
        self.schedule_view.visible_month = date(
            month_number // 12, month_number % 12 + 1, 1
        )
        self.schedule_view.refresh_components()
        await interaction.response.edit_message(
            content=calendar_content(
                self.schedule_view.draft,
                interaction,
                self.schedule_view.visible_month,
            ),
            view=self.schedule_view,
        )


class QueueSeasonDaysPageButton(discord.ui.Button):
    def __init__(self, schedule_view: QueueSeasonScheduleView) -> None:
        super().__init__(
            label=t(
                schedule_view.draft.module.guild, "queue.wizard.calendar_more_days"
            ),
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        self.schedule_view = schedule_view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.schedule_view.day_page = 1 - self.schedule_view.day_page
        self.schedule_view.refresh_components()
        await interaction.response.edit_message(
            content=calendar_content(
                self.schedule_view.draft,
                interaction,
                self.schedule_view.visible_month,
            ),
            view=self.schedule_view,
        )


class QueueSeasonTimezoneButton(discord.ui.Button):
    def __init__(self, schedule_view: QueueSeasonScheduleView) -> None:
        super().__init__(
            label=t(schedule_view.draft.module.guild, "queue.wizard.edit_timezone"),
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        self.schedule_view = schedule_view

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            QueueSeasonTimezoneModal(self.schedule_view)
        )


class QueueSeasonScheduleApplyButton(discord.ui.Button):
    def __init__(self, schedule_view: QueueSeasonScheduleView) -> None:
        super().__init__(
            label=t(schedule_view.draft.module.guild, "queue.wizard.calendar_apply"),
            style=discord.ButtonStyle.success,
            row=3,
        )
        self.schedule_view = schedule_view

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=panel_content(self.schedule_view.draft, interaction),
            view=self.schedule_view.config_view,
        )


class QueueSeasonScheduleView(discord.ui.View):
    def __init__(
        self,
        draft: QueueSetupDraft,
        config_view: QueueConfigView,
        *,
        visible_month: date | None = None,
        day_page: int | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        self.config_view = config_view
        selected_date = date.fromisoformat(draft.season_start_date)
        self.visible_month = visible_month or selected_date.replace(day=1)
        self.day_page = (
            day_page if day_page is not None else int(selected_date.day > 25)
        )
        self.refresh_components()

    def refresh_components(self) -> None:
        self.clear_items()
        days_in_month = calendar.monthrange(
            self.visible_month.year, self.visible_month.month
        )[1]
        if self.day_page and days_in_month <= 25:
            self.day_page = 0
        self.add_item(QueueSeasonMonthButton(self, -1))
        self.add_item(QueueSeasonMonthButton(self, 1))
        self.add_item(QueueSeasonDaysSelect(self))
        if days_in_month > 25:
            self.add_item(QueueSeasonDaysPageButton(self))
        self.add_item(QueueSeasonTimezoneButton(self))
        self.add_item(QueueSeasonScheduleApplyButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.draft.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "queue.wizard.owner_only"), ephemeral=True
        )
        return False


class QueueSeasonTimezoneModal(discord.ui.Modal):
    def __init__(self, schedule_view: QueueSeasonScheduleView) -> None:
        super().__init__(
            title=t(schedule_view.draft.module.guild, "queue.wizard.timezone_title")[
                :45
            ]
        )
        self.schedule_view = schedule_view
        self.timezone_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(schedule_view.draft.module.guild, "queue.wizard.timezone_label")[
                :45
            ],
            default=schedule_view.draft.timezone,
            placeholder="Europe/Berlin",
            max_length=100,
        )
        self.add_item(self.timezone_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        timezone_name = self.timezone_input.value.strip()
        try:
            ZoneInfo(timezone_name)
        except (ValueError, ZoneInfoNotFoundError):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_timezone"), ephemeral=True
            )
            return
        self.schedule_view.draft.timezone = timezone_name
        await interaction.response.send_message(
            t(interaction, "queue.wizard.timezone_saved", timezone=timezone_name),
            ephemeral=True,
        )


class QueueSeasonTasksModal(discord.ui.Modal):
    def __init__(
        self, draft: QueueSetupDraft, hours: tuple[str, ...] | None = None
    ) -> None:
        super().__init__(
            title=t(draft.module.guild, "queue.wizard.season_tasks_title")[:45]
        )
        self.draft = draft
        self.hours = hours
        self.config_view = QueueConfigView(draft)
        task_text = "\n".join(
            f"{label} | {limit}" for label, limit in draft.season_tasks
        )
        self.tasks_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.season_tasks_label")[:45],
            placeholder=t(draft.module.guild, "queue.wizard.season_tasks_example"),
            default=task_text,
            style=discord.TextStyle.paragraph,
            max_length=4000,
        )
        self.add_item(self.tasks_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        tasks: list[tuple[str, int]] = []
        for line in self.tasks_input.value.splitlines():
            if not line.strip():
                continue
            label, separator, raw_limit = line.rpartition("|")
            try:
                completion_limit = int(raw_limit.strip())
            except ValueError:
                completion_limit = 0
            label = label.strip()
            if (
                not separator
                or not label
                or len(label) > 100
                or not 1 <= completion_limit <= 10000
            ):
                await interaction.response.send_message(
                    t(interaction, "queue.error.invalid_season_tasks"),
                    ephemeral=True,
                )
                return
            tasks.append((label, completion_limit))
        normalized_labels = [label.casefold() for label, _ in tasks]
        if not 1 <= len(tasks) <= 25 or len(set(normalized_labels)) != len(tasks):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_season_tasks"),
                ephemeral=True,
            )
            return
        self.draft.season_tasks = tasks
        if self.hours is not None:
            self.draft.seasons = list(self.hours)
        await self.config_view.refresh(interaction)
