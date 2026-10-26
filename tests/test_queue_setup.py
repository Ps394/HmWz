from __future__ import annotations

from datetime import date, time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from hmwz.i18n.loader import load_translation
from hmwz.modules.queue.commands import QueueGroup
from hmwz.modules.queue.module import QueueModule
from hmwz.modules.queue.rules import local_datetime_timestamp, phase_schedule
from hmwz.modules.queue.views import PhaseThreadView, QueueOverviewView


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


@pytest.mark.asyncio
async def test_queue_views_expose_phase_signup_and_destruction_controls() -> None:
    module = cast(
        QueueModule,
        SimpleNamespace(guild=SimpleNamespace()),
    )

    overview = QueueOverviewView(module, 42, ((101, 1), (102, 2), (103, 3)))
    assert [item.custom_id for item in overview.children] == [
        "qsphase:signup:42:101",
        "qsphase:signup:42:102",
        "qsphase:signup:42:103",
    ]

    thread_view = PhaseThreadView(module, 42, 101, enabled=True)
    assert [item.custom_id for item in thread_view.children] == [
        "qsphase:destroy:42:101"
    ]


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
