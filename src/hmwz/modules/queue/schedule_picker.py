from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Awaitable, Callable, Protocol

import discord

from hmwz.i18n import t
from hmwz.ui import EphemeralView

from .rules import local_datetime_timestamp

if TYPE_CHECKING:
    from .module import QueueModule


_TIMEZONES: dict[str, tuple[str, ...]] = {
    "Europe": (
        "Europe/Berlin",
        "Europe/London",
        "Europe/Paris",
        "Europe/Rome",
        "Europe/Madrid",
        "Europe/Amsterdam",
        "Europe/Zurich",
        "Europe/Stockholm",
        "Europe/Warsaw",
        "Europe/Kyiv",
        "Europe/Istanbul",
    ),
    "Americas": (
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Toronto",
        "America/Vancouver",
        "America/Mexico_City",
        "America/Sao_Paulo",
        "America/Argentina/Buenos_Aires",
    ),
    "Asia": (
        "Asia/Tokyo",
        "Asia/Shanghai",
        "Asia/Hong_Kong",
        "Asia/Singapore",
        "Asia/Seoul",
        "Asia/Kolkata",
        "Asia/Dubai",
        "Asia/Bangkok",
        "Asia/Jakarta",
        "Asia/Manila",
    ),
    "Africa": (
        "Africa/Johannesburg",
        "Africa/Cairo",
        "Africa/Lagos",
    ),
    "Oceania": (
        "Australia/Sydney",
        "Australia/Brisbane",
        "Australia/Perth",
        "Pacific/Auckland",
        "Pacific/Honolulu",
    ),
    "UTC": ("UTC",),
}


class ScheduleDraft(Protocol):
    module: QueueModule
    owner_id: int
    start_date: str
    start_time: str
    timezone_name: str


class SchedulePickerView(EphemeralView):
    def __init__(
        self,
        draft: ScheduleDraft,
        on_done: Callable[[discord.Interaction], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(timeout=600)
        self.draft = draft
        self.on_done = on_done
        parsed_date = date.fromisoformat(draft.start_date)
        self.year = parsed_date.year
        self.month = parsed_date.month
        self.day_page = (parsed_date.day - 1) // 25
        self.minute_page = int(draft.start_time.split(":")[1]) // 25
        self.screen = "date"
        self._show_date()

    def _show_date(self) -> None:
        self.clear_items()
        self.add_item(MonthButton(self, -1))
        self.add_item(MonthButton(self, 1))
        self.add_item(DayPageButton(self, -1))
        self.add_item(DayPageButton(self, 1))
        self.add_item(DateSelect(self))
        self.add_item(TimezoneButton(self, row=3))
        self.add_item(ScheduleDoneButton(self, next_screen=True))

    def _show_time(self) -> None:
        self.clear_items()
        self.add_item(MinutePageButton(self, -1))
        self.add_item(MinutePageButton(self, 1))
        self.add_item(HourSelect(self))
        self.add_item(MinuteSelect(self))
        self.add_item(TimezoneButton(self, row=3))
        self.add_item(ScheduleDoneButton(self, next_screen=False))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.draft.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "queue.wizard.owner_only"),
            ephemeral=True,
            delete_after=5,
        )
        return False

    def summary(self, interaction: discord.Interaction) -> str:
        timestamp = local_datetime_timestamp(
            date.fromisoformat(self.draft.start_date),
            datetime.strptime(self.draft.start_time, "%H:%M").time(),
            self.draft.timezone_name,
        )
        if timestamp is None:
            discord_time = t(interaction, "queue.schedule.invalid_local_time")
        else:
            aware = datetime.fromtimestamp(timestamp, timezone.utc)
            discord_time = discord.utils.format_dt(aware, style="F")
        return t(
            interaction,
            "queue.schedule.picker",
            date=self.draft.start_date,
            time=self.draft.start_time,
            timezone=self.draft.timezone_name,
            discord_time=discord_time,
        )


class MonthButton(discord.ui.Button):
    def __init__(self, view: SchedulePickerView, offset: int) -> None:
        super().__init__(
            label=t(view.draft.module.guild, "queue.schedule.previous_month")
            if offset < 0
            else t(view.draft.module.guild, "queue.schedule.next_month"),
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        self.picker = view
        self.offset = offset

    async def callback(self, interaction: discord.Interaction) -> None:
        month = self.picker.month + self.offset
        if month < 1:
            self.picker.year -= 1
            month = 12
        elif month > 12:
            self.picker.year += 1
            month = 1
        self.picker.month = month
        self.picker.day_page = 0
        self.picker.draft.start_date = f"{self.picker.year:04d}-{month:02d}-01"
        self.picker._show_date()
        await interaction.response.edit_message(
            content=self.picker.summary(interaction), view=self.picker
        )


class DayPageButton(discord.ui.Button):
    def __init__(self, view: SchedulePickerView, offset: int) -> None:
        super().__init__(
            label=t(view.draft.module.guild, "queue.schedule.previous_days")
            if offset < 0
            else t(view.draft.module.guild, "queue.schedule.next_days"),
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.picker = view
        self.offset = offset

    async def callback(self, interaction: discord.Interaction) -> None:
        max_page = (
            calendar.monthrange(self.picker.year, self.picker.month)[1] - 1
        ) // 25
        self.picker.day_page = min(max(self.picker.day_page + self.offset, 0), max_page)
        self.picker._show_date()
        await interaction.response.edit_message(
            content=self.picker.summary(interaction), view=self.picker
        )


class DateSelect(discord.ui.Select):
    def __init__(self, view: SchedulePickerView) -> None:
        days = calendar.monthrange(view.year, view.month)[1]
        first = view.day_page * 25 + 1
        last = min(first + 24, days)
        options = [
            discord.SelectOption(
                label=f"{view.year:04d}-{view.month:02d}-{day:02d}",
                value=f"{view.year:04d}-{view.month:02d}-{day:02d}",
                default=view.draft.start_date
                == f"{view.year:04d}-{view.month:02d}-{day:02d}",
            )
            for day in range(first, last + 1)
        ]
        super().__init__(
            placeholder=t(view.draft.module.guild, "queue.schedule.date"),
            options=options,
            min_values=1,
            max_values=1,
            row=2,
        )
        self.picker = view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.picker.draft.start_date = self.values[0]
        await interaction.response.edit_message(
            content=self.picker.summary(interaction), view=self.picker
        )


class HourSelect(discord.ui.Select):
    def __init__(self, view: SchedulePickerView) -> None:
        selected_hour = view.draft.start_time.split(":")[0]
        super().__init__(
            placeholder=t(view.draft.module.guild, "queue.schedule.hour"),
            options=[
                discord.SelectOption(
                    label=f"{hour:02d}",
                    value=f"{hour:02d}",
                    default=f"{hour:02d}" == selected_hour,
                )
                for hour in range(24)
            ],
            min_values=1,
            max_values=1,
            row=1,
        )
        self.picker = view

    async def callback(self, interaction: discord.Interaction) -> None:
        minute = self.picker.draft.start_time.split(":")[1]
        self.picker.draft.start_time = f"{self.values[0]}:{minute}"
        await interaction.response.edit_message(
            content=self.picker.summary(interaction), view=self.picker
        )


class MinutePageButton(discord.ui.Button):
    def __init__(self, view: SchedulePickerView, offset: int) -> None:
        super().__init__(
            label=t(view.draft.module.guild, "queue.schedule.previous_minutes")
            if offset < 0
            else t(view.draft.module.guild, "queue.schedule.next_minutes"),
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        self.picker = view
        self.offset = offset

    async def callback(self, interaction: discord.Interaction) -> None:
        self.picker.minute_page = min(max(self.picker.minute_page + self.offset, 0), 2)
        self.picker._show_time()
        await interaction.response.edit_message(
            content=self.picker.summary(interaction), view=self.picker
        )


class MinuteSelect(discord.ui.Select):
    def __init__(self, view: SchedulePickerView) -> None:
        first = view.minute_page * 25
        last = min(first + 24, 59)
        selected_minute = view.draft.start_time.split(":")[1]
        super().__init__(
            placeholder=t(view.draft.module.guild, "queue.schedule.minute"),
            options=[
                discord.SelectOption(
                    label=f"{minute:02d}",
                    value=f"{minute:02d}",
                    default=f"{minute:02d}" == selected_minute,
                )
                for minute in range(first, last + 1)
            ],
            min_values=1,
            max_values=1,
            row=2,
        )
        self.picker = view

    async def callback(self, interaction: discord.Interaction) -> None:
        hour = self.picker.draft.start_time.split(":")[0]
        self.picker.draft.start_time = f"{hour}:{self.values[0]}"
        await interaction.response.edit_message(
            content=self.picker.summary(interaction), view=self.picker
        )


class TimezoneButton(discord.ui.Button):
    def __init__(self, view: SchedulePickerView, *, row: int) -> None:
        super().__init__(
            label=t(view.draft.module.guild, "queue.schedule.choose_timezone"),
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.picker = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            content=self.picker.summary(interaction),
            view=TimezonePickerView(self.picker.draft),
            ephemeral=True,
        )


class ScheduleDoneButton(discord.ui.Button):
    def __init__(self, view: SchedulePickerView, *, next_screen: bool) -> None:
        super().__init__(
            label=t(
                view.draft.module.guild,
                "queue.schedule.next" if next_screen else "queue.schedule.done",
            ),
            style=discord.ButtonStyle.primary
            if next_screen
            else discord.ButtonStyle.success,
            row=4,
        )
        self.picker = view
        self.next_screen = next_screen

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.next_screen:
            self.picker.screen = "time"
            self.picker._show_time()
            await interaction.response.edit_message(
                content=self.picker.summary(interaction), view=self.picker
            )
            return
        timestamp = local_datetime_timestamp(
            date.fromisoformat(self.picker.draft.start_date),
            datetime.strptime(self.picker.draft.start_time, "%H:%M").time(),
            self.picker.draft.timezone_name,
        )
        if timestamp is None:
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_schedule"), ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=t(
                interaction,
                "queue.schedule.selected",
                date=self.picker.draft.start_date,
                time=self.picker.draft.start_time,
                timezone=self.picker.draft.timezone_name,
                discord_time=discord.utils.format_dt(
                    datetime.fromtimestamp(timestamp, timezone.utc), style="F"
                ),
            ),
            view=None,
        )
        if self.picker.on_done is not None:
            await self.picker.on_done(interaction)


class TimezonePickerView(EphemeralView):
    def __init__(self, draft: ScheduleDraft) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        self.region = next(
            (
                region
                for region, zones in _TIMEZONES.items()
                if draft.timezone_name in zones
            ),
            "Europe",
        )
        self.add_item(RegionSelect(self))
        self.add_item(ZoneSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.draft.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "queue.wizard.owner_only"), ephemeral=True
        )
        return False


class RegionSelect(discord.ui.Select):
    def __init__(self, view: TimezonePickerView) -> None:
        super().__init__(
            placeholder=t(view.draft.module.guild, "queue.schedule.region"),
            options=[
                discord.SelectOption(
                    label=region, value=region, default=region == view.region
                )
                for region in _TIMEZONES
            ],
            min_values=1,
            max_values=1,
            row=0,
        )
        self.picker = view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.picker.region = self.values[0]
        self.picker.clear_items()
        self.picker.add_item(RegionSelect(self.picker))
        self.picker.add_item(ZoneSelect(self.picker))
        await interaction.response.edit_message(
            content=t(
                interaction,
                "queue.schedule.timezone_picker",
                timezone=self.picker.draft.timezone_name,
            ),
            view=self.picker,
        )


class ZoneSelect(discord.ui.Select):
    def __init__(self, view: TimezonePickerView) -> None:
        zones = _TIMEZONES[view.region]
        super().__init__(
            placeholder=t(view.draft.module.guild, "queue.schedule.zone"),
            options=[
                discord.SelectOption(
                    label=zone,
                    value=zone,
                    default=zone == view.draft.timezone_name,
                )
                for zone in zones
            ],
            min_values=1,
            max_values=1,
            row=1,
        )
        self.picker = view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.picker.draft.timezone_name = self.values[0]
        await interaction.response.edit_message(
            content=t(
                interaction,
                "queue.schedule.timezone_selected",
                timezone=self.picker.draft.timezone_name,
            ),
            view=None,
        )
