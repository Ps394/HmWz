from __future__ import annotations

from datetime import date, time
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from zoneinfo import ZoneInfo

import pytest
import discord

from hmwz.i18n.loader import load_translation
from hmwz.modules.queue.commands import QueueGroup
from hmwz.modules.queue.module import QueueModule
from hmwz.modules.queue.rules import local_datetime_timestamp, phase_schedule
from hmwz.modules.queue.schedule_picker import (
    DateSelect,
    MinuteSelect,
    RegionSelect,
    SchedulePickerView,
    TimezonePickerView,
    ZoneSelect,
    _TIMEZONES,
)
from hmwz.modules.queue.views import (
    BaseDestructionConfirmationView,
    PhaseThreadView,
    QueueOverviewView,
)


def test_queue_setup_remove_and_reset_commands_are_available() -> None:
    group = QueueGroup()

    assert {command.name for command in group.commands} == {"setup", "remove", "reset"}


def test_local_time_rejects_dst_gaps_and_ambiguous_hours() -> None:
    assert (
        local_datetime_timestamp(
            date(2025, 3, 30),
            time(2),
            "Europe/Berlin",
        )
        is None
    )
    assert (
        local_datetime_timestamp(
            date(2025, 10, 26),
            time(2),
            "Europe/Berlin",
        )
        is None
    )
    assert (
        local_datetime_timestamp(
            date(2025, 3, 30),
            time(3),
            "Europe/Berlin",
        )
        == 1743296400
    )


def test_phase_schedule_enforces_count_duration_and_non_overlap() -> None:
    valid = phase_schedule(
        "2025-01-02",
        "UTC",
        (("08:00", 1), ("12:00", 2), ("16:00", 3)),
    )
    assert valid is not None
    assert valid[1] - valid[0] == 24 * 60 * 60
    assert len(valid[2]) == 3

    assert (
        phase_schedule(
            "2025-01-02",
            "UTC",
            (("08:00", 3), ("10:00", 2), ("16:00", 1)),
        )
        is None
    )
    assert (
        phase_schedule(
            "2025-01-02",
            "UTC",
            (("08:00", 1), ("12:00", 4), ("16:00", 1)),
        )
        is None
    )
    assert (
        phase_schedule(
            "2025-01-02",
            "UTC",
            (("08:00", 1), ("12:00", 1)),
        )
        is None
    )


def test_phase_schedule_rejects_dst_gap_and_ambiguous_start() -> None:
    assert (
        phase_schedule(
            "2025-03-30",
            "Europe/Berlin",
            (("02:00", 1), ("08:00", 1), ("12:00", 1)),
        )
        is None
    )
    assert (
        phase_schedule(
            "2025-10-26",
            "Europe/Berlin",
            (("02:00", 1), ("08:00", 1), ("12:00", 1)),
        )
        is None
    )


def test_overview_formats_discord_and_queue_local_phase_times() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    start = datetime(2025, 1, 2, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    end = datetime(2025, 1, 2, 13, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert QueueModule._discord_timestamp(start.timestamp()) == (
        f"<t:{int(start.timestamp())}:F>"
    )
    assert (
        QueueModule._phase_local_range(
            start.timestamp(), end.timestamp(), "Europe/Berlin"
        )
        == "12:00-13:00"
    )


@pytest.mark.asyncio
async def test_queue_views_expose_phase_signup_and_destruction_controls() -> None:
    module = cast(
        QueueModule,
        SimpleNamespace(guild=SimpleNamespace()),
    )

    overview = QueueOverviewView(
        module,
        42,
        ((101, 1, "08:00-09:00"), (102, 2, "12:00-13:00"), (103, 3, "16:00-17:00")),
    )
    assert [item.custom_id for item in overview.children] == [
        "qsphase:signup:42:101",
        "qsphase:signup:42:102",
        "qsphase:signup:42:103",
    ]
    assert [button.label for button in overview.children] == [
        "📝 08:00-09:00",
        "📝 12:00-13:00",
        "📝 16:00-17:00",
    ]

    thread_view = PhaseThreadView(module, 42, 101, enabled=True)
    assert [item.custom_id for item in thread_view.children] == [
        "qsphase:destroy:42:101"
    ]

    confirmation = BaseDestructionConfirmationView(module, 42, 101)
    assert len(confirmation.children) == 1
    assert confirmation.children[0].label == "Bestätigen"
    assert not any(
        isinstance(item, discord.ui.TextInput) for item in confirmation.children
    )


@pytest.mark.asyncio
async def test_datetime_picker_has_component_based_date_minute_and_timezone_selects() -> (
    None
):
    module = cast(QueueModule, SimpleNamespace(guild=SimpleNamespace()))
    draft = SimpleNamespace(
        module=module,
        owner_id=1,
        start_date="2026-10-27",
        start_time="23:33",
        timezone_name="Europe/Berlin",
    )
    picker = SchedulePickerView(draft)
    date_select = next(item for item in picker.children if isinstance(item, DateSelect))
    assert len(date_select.options) <= 25
    assert any(option.value == "2026-10-27" for option in date_select.options)

    picker.screen = "time"
    picker._show_time()
    minutes = next(item for item in picker.children if isinstance(item, MinuteSelect))
    assert len(minutes.options) <= 25
    assert any(option.value == "33" for option in minutes.options)

    timezone_view = TimezonePickerView(draft)
    zone_select = next(
        item for item in timezone_view.children if isinstance(item, ZoneSelect)
    )
    region_select = next(
        item for item in timezone_view.children if isinstance(item, RegionSelect)
    )
    assert len(zone_select.options) <= 25
    assert len(region_select.options) <= 25
    assert any(option.value == "Europe/Berlin" for option in zone_select.options)
    for zone in (zone for zones in _TIMEZONES.values() for zone in zones):
        ZoneInfo(zone)


def test_phase_schedule_accepts_local_start_time_and_rejects_dst_start() -> None:
    schedule = phase_schedule(
        "2025-01-02",
        "Europe/Berlin",
        (("11:00", 1), ("13:00", 1), ("16:00", 1)),
        "10:30",
    )
    assert schedule is not None
    assert schedule[0] == 1735810200
    assert (
        phase_schedule(
            "2025-10-26",
            "Europe/Berlin",
            (("08:00", 1), ("12:00", 1), ("16:00", 1)),
            "02:30",
        )
        is None
    )


def test_past_and_future_starts_are_valid_but_dst_ambiguous_starts_are_not() -> None:
    phases = (("11:00", 1), ("13:00", 1), ("16:00", 1))
    past = phase_schedule("2025-01-02", "Europe/Berlin", phases, "10:30")
    future = phase_schedule("2027-01-02", "Europe/Berlin", phases, "10:30")
    assert past is not None
    assert future is not None
    assert past[0] < future[0]
    assert (
        phase_schedule(
            "2025-03-30",
            "Europe/Berlin",
            (("03:00", 1), ("12:00", 1), ("16:00", 1)),
            "02:30",
        )
        is None
    )
    assert (
        phase_schedule(
            "2025-10-26",
            "Europe/Berlin",
            (("03:00", 1), ("12:00", 1), ("16:00", 1)),
            "02:30",
        )
        is None
    )


def test_queue_translation_has_required_german_and_english_runtime_keys() -> None:
    root = Path(__file__).parents[1] / "src" / "hmwz" / "modules" / "queue" / "i18n"
    german = load_translation(root / "runtime" / "de.json")
    english = load_translation(root / "runtime" / "en.json")
    required = {
        "queue.error.invalid_schedule",
        "queue.error.participant_limit",
        "queue.destruction.already_confirmed",
        "queue.wizard.panel",
    }

    assert required.issubset(german)
    assert required.issubset(english)
