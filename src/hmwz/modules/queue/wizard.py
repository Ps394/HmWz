from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from hmwz.i18n import t
from hmwz.ui import EphemeralView

from .module import QueueModule
from .models import QueueConfiguration
from .rules import phase_schedule


@dataclass(slots=True)
class QueueSetupDraft:
    module: QueueModule
    channel_id: int
    owner_id: int
    configuration: QueueConfiguration | None = None
    role_id: int | None = None
    title: str = "QS Eruption"
    description: str = ""
    start_date: str = ""
    start_time: str = "00:00"
    timezone_name: str = "Europe/Berlin"
    phase_hours: tuple[tuple[str, int], ...] = (
        ("08:00", 1),
        ("12:00", 1),
        ("16:00", 1),
    )
    modal_prompt: str = "Bestätige die Zerstörung deiner Basis."
    remove_role_on_reset: bool = False
    reminder_settings: tuple[bool, int, bool, int, bool, int] = (
        False,
        60,
        False,
        60,
        False,
        15,
    )

    def __post_init__(self) -> None:
        config = self.configuration
        if config is not None:
            self.title = config.title or self.title
            self.description = config.description
            self.role_id = config.role_id or None
            self.modal_prompt = config.modal_prompt or self.modal_prompt
            self.timezone_name = config.timezone
            self.phase_hours = config.phase_hours or self.phase_hours
            self.remove_role_on_reset = config.remove_role_on_reset
            self.reminder_settings = (
                config.eruption_start_reminder_enabled,
                config.eruption_start_reminder_minutes,
                config.eruption_end_reminder_enabled,
                config.eruption_end_reminder_minutes,
                config.phase_start_reminder_enabled,
                config.phase_start_reminder_minutes,
            )
            if config.next_start_at is not None:
                try:
                    local_start = datetime.fromtimestamp(
                        config.next_start_at, timezone.utc
                    ).astimezone(ZoneInfo(config.timezone))
                    self.start_date = local_start.date().isoformat()
                    self.start_time = local_start.strftime("%H:%M")
                except (ValueError, ZoneInfoNotFoundError, OSError):
                    pass
        if not self.start_date:
            try:
                tomorrow = discord.utils.utcnow().astimezone(
                    ZoneInfo(self.timezone_name)
                ).date() + timedelta(days=1)
                self.start_date = tomorrow.isoformat()
            except ZoneInfoNotFoundError:
                self.start_date = discord.utils.utcnow().date().isoformat()


class QueueSetupView(EphemeralView):
    def __init__(self, draft: QueueSetupDraft) -> None:
        super().__init__(timeout=600)
        self.draft = draft
        self.add_item(QueueRoleSelect(self))
        self.add_item(QueueSetupButton(self, "details"))
        self.add_item(QueueSetupButton(self, "prompt"))
        self.add_item(QueueSetupButton(self, "reminders"))
        self.add_item(QueueSetupButton(self, "save"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.draft.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "queue.wizard.owner_only"),
            ephemeral=True,
            delete_after=5,
        )
        return False


class QueueRoleSelect(discord.ui.RoleSelect):
    def __init__(self, view: QueueSetupView) -> None:
        super().__init__(
            placeholder=t(view.draft.module.guild, "queue.wizard.role_placeholder"),
            min_values=1,
            max_values=1,
            row=0,
        )
        self.setup_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.setup_view.draft.role_id = self.values[0].id
        await interaction.response.edit_message(
            content=setup_content(self.setup_view.draft, interaction),
            view=self.setup_view,
        )


class QueueSetupButton(discord.ui.Button):
    def __init__(self, view: QueueSetupView, action: str) -> None:
        labels = {
            "details": "queue.wizard.edit_details",
            "prompt": "queue.wizard.edit_prompt",
            "reminders": "queue.wizard.edit_reminders",
            "save": "queue.wizard.save",
        }
        styles = {
            "details": discord.ButtonStyle.secondary,
            "prompt": discord.ButtonStyle.secondary,
            "reminders": discord.ButtonStyle.secondary,
            "save": discord.ButtonStyle.success,
        }
        super().__init__(
            label=t(view.draft.module.guild, labels[action]),
            style=styles[action],
            custom_id=f"queue:setup:{action}",
            row=1,
        )
        self.setup_view = view
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        draft = self.setup_view.draft
        if self.action == "details":
            await interaction.response.send_modal(QueueDetailsModal(draft))
        elif self.action == "prompt":
            await interaction.response.send_modal(QueuePromptModal(draft))
        elif self.action == "reminders":
            await interaction.response.send_modal(QueueReminderModal(draft))
        else:
            await _save_setup(interaction, draft, self.setup_view)


class QueueDetailsModal(discord.ui.Modal):
    def __init__(self, draft: QueueSetupDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "queue.wizard.details_title"),
            timeout=300,
        )
        self.draft = draft
        self.title_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.title_label"),
            default=draft.title[:100],
            max_length=100,
            required=True,
        )
        self.description_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.description_label"),
            default=draft.description[:1000],
            max_length=1000,
            required=False,
            style=discord.TextStyle.paragraph,
        )
        self.date_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.date_label"),
            default=f"{draft.start_date} {draft.start_time}",
            max_length=16,
            required=True,
        )
        self.timezone_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.timezone_label"),
            default=draft.timezone_name,
            max_length=64,
            required=True,
        )
        self.phases_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.phases_label"),
            default="\n".join(
                f"{hour},{duration}" for hour, duration in draft.phase_hours
            ),
            max_length=100,
            required=True,
            style=discord.TextStyle.paragraph,
        )
        for item in (
            self.title_input,
            self.description_input,
            self.date_input,
            self.timezone_input,
            self.phases_input,
        ):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        parsed_phases: list[tuple[str, int]] = []
        try:
            for line in self.phases_input.value.splitlines():
                hour, duration = (part.strip() for part in line.split(",", 1))
                parsed_phases.append((hour, int(duration)))
        except (ValueError, TypeError):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_schedule"),
                ephemeral=True,
            )
            return
        schedule = phase_schedule(
            self.date_input.value.strip().split(" ", 1)[0],
            self.timezone_input.value.strip(),
            tuple(parsed_phases),
            self.date_input.value.strip().split(" ", 1)[1]
            if " " in self.date_input.value.strip()
            else "",
        )
        if schedule is None:
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_schedule"),
                ephemeral=True,
            )
            return
        if schedule[0] <= discord.utils.utcnow().timestamp():
            await interaction.response.send_message(
                t(interaction, "queue.error.start_in_past"),
                ephemeral=True,
            )
            return
        self.draft.title = self.title_input.value.strip()
        self.draft.description = self.description_input.value.strip()
        self.draft.start_date, self.draft.start_time = (
            self.date_input.value.strip().split(" ", 1)
        )
        self.draft.timezone_name = self.timezone_input.value.strip()
        self.draft.phase_hours = tuple(parsed_phases)
        await interaction.response.send_message(
            t(interaction, "queue.wizard.details_updated"),
            ephemeral=True,
            delete_after=5,
        )


class QueuePromptModal(discord.ui.Modal):
    def __init__(self, draft: QueueSetupDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "queue.wizard.prompt_title"),
            timeout=300,
        )
        self.draft = draft
        self.prompt: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.prompt_label"),
            default=draft.modal_prompt[:45],
            max_length=45,
            required=True,
        )
        self.add_item(self.prompt)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.draft.modal_prompt = self.prompt.value.strip()
        await interaction.response.send_message(
            t(interaction, "queue.wizard.prompt_updated"),
            ephemeral=True,
            delete_after=5,
        )


class QueueReminderModal(discord.ui.Modal):
    def __init__(self, draft: QueueSetupDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "queue.wizard.reminders_title"),
            timeout=300,
        )
        self.draft = draft
        start, start_minutes, end, end_minutes, phase, phase_minutes = (
            draft.reminder_settings
        )
        self.reset_role: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.reset_role_label"),
            default="on" if draft.remove_role_on_reset else "off",
            max_length=3,
        )
        self.start: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.start_reminder_label"),
            default=f"{'on' if start else 'off'},{start_minutes}",
            max_length=10,
        )
        self.end: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.end_reminder_label"),
            default=f"{'on' if end else 'off'},{end_minutes}",
            max_length=10,
        )
        self.phase: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "queue.wizard.phase_reminder_label"),
            default=f"{'on' if phase else 'off'},{phase_minutes}",
            max_length=10,
        )
        for item in (self.reset_role, self.start, self.end, self.phase):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            parsed: list[tuple[bool, int]] = []
            for entry in (self.start.value, self.end.value, self.phase.value):
                toggle, minutes = (value.strip() for value in entry.split(",", 1))
                if toggle not in ("on", "off"):
                    raise ValueError
                parsed.append((toggle == "on", int(minutes)))
            if self.reset_role.value.strip() not in ("on", "off"):
                raise ValueError
            settings: tuple[bool, int, bool, int, bool, int] = (
                parsed[0][0],
                parsed[0][1],
                parsed[1][0],
                parsed[1][1],
                parsed[2][0],
                parsed[2][1],
            )
            if not self.draft.module._valid_reminder_settings(
                settings, self.draft.phase_hours
            ):
                raise ValueError
        except (ValueError, TypeError):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_reminder"),
                ephemeral=True,
            )
            return
        self.draft.remove_role_on_reset = self.reset_role.value.strip() == "on"
        self.draft.reminder_settings = settings
        await interaction.response.send_message(
            t(interaction, "queue.wizard.reminders_updated"),
            ephemeral=True,
            delete_after=5,
        )


def setup_content(
    draft: QueueSetupDraft,
    interaction: discord.Interaction,
) -> str:
    role = (
        f"<@&{draft.role_id}>"
        if draft.role_id is not None
        else t(interaction, "queue.wizard.role_missing")
    )
    phases = ", ".join(f"{hour} ({duration} h)" for hour, duration in draft.phase_hours)
    start, start_minutes, end, end_minutes, phase, phase_minutes = (
        draft.reminder_settings
    )
    return t(
        interaction,
        "queue.wizard.panel",
        title=draft.title or t(interaction, "queue.wizard.default_title"),
        role=role,
        date=draft.start_date,
        time=draft.start_time,
        timezone=draft.timezone_name,
        phases=phases,
        prompt=draft.modal_prompt,
        remove_role="on" if draft.remove_role_on_reset else "off",
        reminders=f"start {'on' if start else 'off'}/{start_minutes}, end {'on' if end else 'off'}/{end_minutes}, phase {'on' if phase else 'off'}/{phase_minutes}",
    )


async def _save_setup(
    interaction: discord.Interaction,
    draft: QueueSetupDraft,
    view: QueueSetupView,
) -> None:
    if draft.role_id is None:
        await interaction.response.send_message(
            t(interaction, "queue.error.role_required"),
            ephemeral=True,
        )
        return
    result = await draft.module.configure_queue(
        channel_id=draft.channel_id,
        title=draft.title,
        description=draft.description,
        role_id=draft.role_id,
        modal_prompt=draft.modal_prompt,
        start_date=draft.start_date,
        timezone_name=draft.timezone_name,
        phase_hours=draft.phase_hours,
        start_time=draft.start_time,
        remove_role_on_reset=draft.remove_role_on_reset,
        reminder_settings=draft.reminder_settings,
    )
    await interaction.response.edit_message(
        content=t(interaction, f"queue.setup.result_{result}"),
        view=None if result in ("saved", "settings_saved") else view,
    )
