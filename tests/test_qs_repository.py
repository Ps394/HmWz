import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from hmwz.modules.hs.qs.models import (
    Phase,
    PingSettings,
    phase_starts,
    validate_schedule,
)
from hmwz.modules.hs.qs.repositories import QsRepository
from hmwz.modules.hs.qs.repositories.bases import (
    BaseLimitReached,
    DuplicateBaseReport,
)
from hmwz.sqlite_db import Database
from hmwz.ui.components.timestamp_input import parse_local_datetime, resolve_timezone


@pytest.fixture
async def repository(tmp_path: Path) -> QsRepository:
    database = Database(folder=str(tmp_path), filename="qs.db")
    assert await database.execute("CREATE TABLE Servers (Guild INTEGER PRIMARY KEY)")
    assert await database.execute("INSERT INTO Servers VALUES (10), (11)")
    repository = QsRepository(database)
    assert await repository.ensure_schema()
    assert await repository.ensure_schema()
    await repository.configure(
        10, 20, 30, "2026-11-01", "UTC", (0, 7200, 14400, 21600, 28800)
    )
    return repository


@pytest.mark.asyncio
async def test_independent_schema_and_exact_five_phases(
    repository: QsRepository,
) -> None:
    rows = await repository.database.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    assert {row["name"] for row in rows} == {
        "Servers",
        "HsQsEvents",
        "HsQsPhases",
        "HsQsMembers",
        "HsQsBases",
    }
    phases = await repository.phases(10, 20)
    assert [phase.index for phase in phases] == [1, 2, 3, 4, 5]
    assert all(phase.ends_at - phase.starts_at == 7200 for phase in phases)
    assert not await repository.database.fetch_all("PRAGMA foreign_key_check")


@pytest.mark.asyncio
async def test_ping_settings_schema_upgrade_and_preservation(
    repository: QsRepository,
) -> None:
    for column in ("PingStart", "PingEnd", "PingGoal", "PingPhaseStart"):
        assert await repository.database.execute(
            f"ALTER TABLE HsQsEvents DROP COLUMN {column}"
        )
    assert await repository.ensure_schema()
    configuration = await repository.get(10, 20)
    assert configuration is not None
    assert configuration.ping_settings == PingSettings()
    settings = PingSettings(start=False, goal=False, phase_start=False)
    await repository.configure(
        10, 20, 30, "2026-11-01", "UTC", (0,) * 5, ping_settings=settings
    )
    assert await repository.ensure_schema()
    restored = QsRepository(repository.database)
    assert (await restored.all(10))[0].ping_settings == settings
    for reset in (False, True):
        await restored.configure(
            10, 20, 30, "2026-11-02", "UTC", (86400,) * 4, reset=reset
        )
        current = await restored.get(10, 20)
        assert current is not None
        assert current.ping_settings == settings
    await restored.configure(10, 21, 30, "2026-11-02", "UTC", (86400,) * 4)
    other = await restored.get(10, 21)
    assert other is not None
    assert other.ping_settings == PingSettings()


@pytest.mark.asyncio
async def test_participant_message_schema_upgrade_and_thread_replacement(
    repository: QsRepository,
) -> None:
    assert await repository.database.execute(
        "ALTER TABLE HsQsPhases DROP COLUMN MembersMessage"
    )
    assert await repository.ensure_schema()
    assert await repository.save_thread(10, 20, 1, 200, 201)
    assert await repository.save_members_message(10, 20, 1, 202)
    assert await repository.ensure_schema()
    assert await repository.save_thread(10, 20, 1, 200, 203)
    phase = (await repository.phases(10, 20))[0]
    assert phase.members_message_id == 202
    assert phase.message_id == 203
    assert await repository.save_thread(10, 20, 1, 300, None)
    assert (await repository.phases(10, 20))[0].members_message_id is None


@pytest.mark.parametrize("hour", range(24))
def test_all_start_hours_and_midnight(hour: int) -> None:
    starts = phase_starts("2026-11-01", (hour,) * 5, "UTC")
    assert len(starts) == 5
    assert starts[0] == 1793491200 + hour * 3600
    assert Phase(1, starts[0], None, None).ends_at == starts[0] + 7200


@pytest.mark.parametrize(
    ("date", "hours", "timezone"),
    [
        ("invalid", (0, 2, 4, 6, 8), "UTC"),
        ("2026-11-01", (0, 2, 4), "UTC"),
        ("2026-11-01", (-1, 2, 4, 6, 8), "UTC"),
        ("2026-11-01", (24, 2, 4, 6, 8), "UTC"),
        ("2026-11-01", (0, 2, 4, 6, 8), "Invalid/Zone"),
        ("2026-03-29", (2, 4, 6, 8, 10), "Europe/Berlin"),
        ("2026-10-25", (2, 4, 6, 8, 10), "Europe/Berlin"),
    ],
)
def test_invalid_schedule_rejected(
    date: str, hours: tuple[int, ...], timezone: str
) -> None:
    with pytest.raises(ValueError):
        phase_starts(date, hours, timezone)


@pytest.mark.asyncio
async def test_multi_phase_signups_and_channel_isolation(
    repository: QsRepository,
) -> None:
    assert await repository.toggle(10, 20, 1, 100)
    assert await repository.toggle(10, 20, 5, 100)
    assert not await repository.toggle(10, 20, 1, 100)
    assert await repository.members(10, 20, 1) == ()
    assert await repository.members(10, 20, 5) == (100,)
    await repository.configure(10, 21, 31, "2026-11-01", "UTC", (0,) * 5)
    assert await repository.members(10, 21, 5) == ()
    assert await repository.members(11, 20, 5) == ()


@pytest.mark.asyncio
async def test_report_once_per_member_and_base_across_phases(
    repository: QsRepository,
) -> None:
    await repository.report(10, 20, 1, 100, "Player", 123)
    with pytest.raises(DuplicateBaseReport):
        await repository.report(10, 20, 5, 100, "Player", 124)
    await repository.report(10, 20, 2, 101, "Player", 125)
    assert len(await repository.reports(10, 20)) == 2


@pytest.mark.asyncio
async def test_concurrent_member_reports_cannot_double_count(
    repository: QsRepository,
) -> None:
    results = await asyncio.gather(
        repository.report(10, 20, 1, 100, "Player", 123),
        repository.report(10, 20, 2, 100, "Player", 124),
        return_exceptions=True,
    )
    assert sum(isinstance(result, DuplicateBaseReport) for result in results) == 1
    assert len(await repository.reports(10, 20)) == 1


@pytest.mark.asyncio
async def test_total_bases_is_exactly_40(repository: QsRepository) -> None:
    for number in range(1, 41):
        await repository.report(10, 20, number % 5 + 1, number + 100, "Player", number)
    assert len(await repository.reports(10, 20)) == 40
    with pytest.raises(BaseLimitReached):
        await repository.report(10, 20, 1, 999, "Player", 0)


@pytest.mark.asyncio
async def test_configuration_update_retains_event_data(
    repository: QsRepository,
) -> None:
    assert await repository.toggle(10, 20, 1, 100)
    await repository.report(10, 20, 1, 100, "Player", 123)
    assert await repository.save_thread(10, 20, 1, 300, 301)
    assert await repository.save_messages(10, 20, 200, 201)
    await repository.configure(10, 20, 31, "2026-11-02", "UTC", (3600,) * 5)
    configuration = await repository.get(10, 20)
    assert configuration is not None
    assert configuration.role_id == 31
    assert configuration.message_id == 200
    assert configuration.bases_message_id == 201
    assert (await repository.phases(10, 20))[0].thread_id == 300
    assert await repository.members(10, 20, 1) == (100,)
    assert len(await repository.reports(10, 20)) == 1


@pytest.mark.asyncio
async def test_cleanup_cascades_but_member_cleanup_preserves_reports(
    repository: QsRepository,
) -> None:
    await repository.toggle(10, 20, 1, 100)
    await repository.report(10, 20, 1, 100, "Player", 123)
    assert await repository.remove_member(10, 100, 20)
    assert await repository.members(10, 20, 1) == ()
    assert len(await repository.reports(10, 20)) == 1
    assert await repository.remove(10, 20)
    assert await repository.get(10, 20) is None
    assert await repository.phases(10, 20) == ()
    assert await repository.reports(10, 20) == ()


@pytest.mark.parametrize("count", [4, 5])
@pytest.mark.parametrize("duration", [1, 2, 3])
def test_supported_phase_counts_and_durations(count: int, duration: int) -> None:
    starts = (1000,) * count
    validate_schedule(1000, starts, (duration,) * count)


@pytest.mark.parametrize(
    ("starts", "durations"),
    [
        ((1000,) * 3, (1,) * 3),
        ((1000,) * 6, (1,) * 6),
        ((1000,) * 4, (0,) * 4),
        ((1000,) * 4, (4,) * 4),
        ((999,) * 4, (1,) * 4),
        ((1000 + 86400 - 3600 + 1,) * 4, (1,) * 4),
        ((1000,) * 4, (1,) * 5),
    ],
)
def test_schedule_rejects_invalid_counts_durations_and_window(
    starts: tuple[int, ...], durations: tuple[int, ...]
) -> None:
    with pytest.raises(ValueError):
        validate_schedule(1000, starts, durations)


def test_phase_can_end_exactly_at_eruption_end() -> None:
    validate_schedule(1000, (1000 + 86400 - 10800,) * 4, (3,) * 4)


def test_evening_eruption_rolls_morning_phases_to_tomorrow() -> None:
    start = int(parse_local_datetime("2026-11-01 22:00", "Europe/Berlin").timestamp())
    starts = phase_starts(
        "2026-11-01", (22, 8, 12, 16, 19), "Europe/Berlin", eruption_start=start
    )
    validate_schedule(start, starts, (3, 3, 3, 3, 2))
    local = [
        datetime.fromtimestamp(value, resolve_timezone("Europe/Berlin")).isoformat()
        for value in starts
    ]
    assert local == [
        "2026-11-01T22:00:00+01:00",
        "2026-11-02T08:00:00+01:00",
        "2026-11-02T12:00:00+01:00",
        "2026-11-02T16:00:00+01:00",
        "2026-11-02T19:00:00+01:00",
    ]
    assert starts[0] + 3 * 3600 == int(
        parse_local_datetime("2026-11-02 01:00", "Europe/Berlin").timestamp()
    )


def test_hour_before_start_minutes_rolls_to_next_day() -> None:
    start = int(parse_local_datetime("2026-11-01 22:30", "UTC").timestamp())
    starts = phase_starts("unused", (22, 23, 8, 12), "UTC", eruption_start=start)
    assert starts[0] == int(parse_local_datetime("2026-11-02 22:00", "UTC").timestamp())
    with pytest.raises(ValueError):
        validate_schedule(start, starts, (1,) * 4)


@pytest.mark.parametrize("date", ["2026-03-28", "2026-10-24"])
def test_rolled_day_rejects_dst_missing_or_ambiguous_hour(date: str) -> None:
    start = int(parse_local_datetime(f"{date} 22:00", "Europe/Berlin").timestamp())
    with pytest.raises(ValueError):
        phase_starts(date, (22, 2, 8, 12), "Europe/Berlin", eruption_start=start)


@pytest.mark.asyncio
async def test_existing_schema_migration_preserves_records(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="legacy-qs.db")
    assert await database.execute("CREATE TABLE Servers (Guild INTEGER PRIMARY KEY)")
    assert await database.execute("INSERT INTO Servers VALUES (10)")
    assert await database.execute(
        "CREATE TABLE HsQsEvents (Guild INTEGER, Channel INTEGER, Role INTEGER, Date TEXT, "
        "Timezone TEXT, Message INTEGER, BasesMessage INTEGER, PRIMARY KEY(Guild,Channel))"
    )
    assert await database.execute(
        "CREATE TABLE HsQsPhases (Guild INTEGER, Channel INTEGER, Phase INTEGER, StartsAt INTEGER, "
        "Thread INTEGER, Message INTEGER, PRIMARY KEY(Guild,Channel,Phase))"
    )
    assert await database.execute(
        "INSERT INTO HsQsEvents VALUES (10,20,30,'2026-11-01','UTC',100,101)"
    )
    assert await database.execute(
        "INSERT INTO HsQsPhases VALUES (10,20,1,1793491200,200,201)"
    )
    repository = QsRepository(database)
    assert await repository.ensure_schema()
    assert await repository.ensure_schema()
    configuration = await repository.get(10, 20)
    assert configuration is not None
    assert configuration.eruption_start == 1793491200
    assert configuration.message_id == 100
    assert configuration.state == "active"
    phase = (await repository.phases(10, 20))[0]
    assert phase.duration_hours == 2
    assert phase.thread_id == 200 and phase.message_id == 201


@pytest.mark.asyncio
async def test_legacy_numbered_reports_migrate_without_losing_counts(
    repository: QsRepository,
) -> None:
    database = repository.database
    assert await database.execute("DROP TABLE HsQsBases")
    assert await database.execute(
        "CREATE TABLE HsQsBases (Guild INTEGER, Channel INTEGER, Phase INTEGER, Member INTEGER, "
        "Base INTEGER NOT NULL, Note TEXT NOT NULL, CreatedAt INTEGER, "
        "PRIMARY KEY (Guild,Channel,Member), UNIQUE (Guild,Channel,Base), "
        "FOREIGN KEY (Guild,Channel,Phase) REFERENCES HsQsPhases (Guild,Channel,Phase) ON DELETE CASCADE)"
    )
    assert await database.execute(
        "INSERT INTO HsQsBases VALUES (10,20,1,100,1,'old',123)"
    )
    assert await repository.ensure_schema()
    assert await repository.ensure_schema()
    reports = await repository.reports(10, 20)
    assert len(reports) == 1
    assert reports[0].member_id == 100
    assert reports[0].created_at == 123
    columns = {
        row["name"] for row in await database.fetch_all("PRAGMA table_info(HsQsBases)")
    }
    assert "Base" not in columns and "Note" not in columns
    assert "DisplayName" in columns
    assert not await database.fetch_all("PRAGMA foreign_key_check")
    await repository.report(10, 20, 2, 101, "Player Name", 124)
    assert len(await repository.reports(10, 20)) == 2


@pytest.mark.asyncio
async def test_concurrent_reports_cannot_exceed_forty(repository: QsRepository) -> None:
    for member_id in range(39):
        await repository.report(10, 20, 1, member_id, "Player", member_id)
    results = await asyncio.gather(
        repository.report(10, 20, 1, 100, "A", 123),
        repository.report(10, 20, 1, 101, "B", 123),
        return_exceptions=True,
    )
    assert sum(isinstance(result, BaseLimitReached) for result in results) == 1
    assert len(await repository.reports(10, 20)) == 40
