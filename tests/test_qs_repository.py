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
from hmwz.modules.hs.qs.models import MemberSignup
from hmwz.modules.hs.qs.repositories.bases import (
    BaseLimitReached,
    DuplicateBaseReport,
    InvalidGameAccount,
)
from hmwz.modules.hs.account.repositories import MemberGameAccountRepository
from hmwz.sqlite_db import Database
from hmwz.ui.components.timestamp_input import parse_local_datetime, resolve_timezone


@pytest.fixture
async def repository(tmp_path: Path) -> QsRepository:
    database = Database(folder=str(tmp_path), filename="qs.db")
    assert await database.execute("CREATE TABLE Servers (Guild INTEGER PRIMARY KEY)")
    assert await database.execute("INSERT INTO Servers VALUES (10), (11)")
    accounts = MemberGameAccountRepository(database)
    assert await database.execute(accounts.table)
    assert await database.execute_many(
        "INSERT INTO GameAccounts (Guild, Member, Account) VALUES (?, ?, ?)",
        tuple((10, member_id, f"Account-{member_id}") for member_id in range(2000)),
    )
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
        "GameAccounts",
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
            10, 20, 30, "2026-11-02", "UTC", (86400,) * 5, reset=reset
        )
        current = await restored.get(10, 20)
        assert current is not None
        assert current.ping_settings == settings
    await restored.configure(10, 21, 30, "2026-11-02", "UTC", (86400,) * 5)
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


def test_phase_starts_preserve_minutes() -> None:
    starts = phase_starts(
        "2026-11-01",
        (0, 2, 4, 6, 8),
        "UTC",
        minutes=(15, 25, 35, 45, 55),
    )
    assert starts[0] == int(parse_local_datetime("2026-11-01 00:15", "UTC").timestamp())
    assert starts[-1] == int(
        parse_local_datetime("2026-11-01 08:55", "UTC").timestamp()
    )


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


@pytest.mark.parametrize("minutes", [(0, 0, 0, 0, 60), (0, 0, 0, 0)])
def test_phase_starts_reject_invalid_minutes(minutes: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        phase_starts("2026-11-01", (0, 2, 4, 6, 8), "UTC", minutes=minutes)


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
async def test_member_signup_accounts_migrate_and_persist(
    repository: QsRepository,
) -> None:
    assert await repository.database.execute("DROP TABLE HsQsMembers")
    assert await repository.database.execute(
        """
        CREATE TABLE HsQsMembers (
            Guild INTEGER NOT NULL,
            Channel INTEGER NOT NULL,
            Phase INTEGER NOT NULL,
            Member INTEGER NOT NULL,
            GameAccount TEXT,
            PRIMARY KEY (Guild, Channel, Phase, Member),
            FOREIGN KEY (Guild, Channel, Phase)
                REFERENCES HsQsPhases (Guild, Channel, Phase) ON DELETE CASCADE
        ) WITHOUT ROWID
        """
    )
    assert await repository.database.execute(
        "INSERT INTO HsQsMembers VALUES (10, 20, 1, 100, NULL)"
    )
    assert await repository.ensure_schema()
    assert not await repository.database.fetch_all("PRAGMA foreign_key_check")
    columns = {
        row["name"]
        for row in await repository.database.fetch_all("PRAGMA table_info(HsQsMembers)")
    }
    assert "CreatedAt" in columns
    migrated = await repository.database.fetch_one(
        "SELECT CreatedAt FROM HsQsMembers "
        "WHERE Guild=10 AND Channel=20 AND Phase=1 AND Member=100"
    )
    assert migrated is not None and migrated["CreatedAt"] == 0
    assert await repository.member_signups(10, 20, 1) == (MemberSignup(100, None),)
    assert await repository.join(10, 20, 1, 100, "Account-100")
    assert await repository.member_signups(10, 20, 1) == (
        MemberSignup(100, None),
        MemberSignup(100, "Account-100"),
    )
    assert await repository.members(10, 20, 1) == (100, 100)
    assert not await repository.toggle(10, 20, 1, 100)
    assert await repository.member_signups(10, 20, 1) == (
        MemberSignup(100, "Account-100"),
    )
    assert await repository.remove_signup(10, 20, 1, 100, "Account-100")
    assert await repository.member_signups(10, 20, 1) == ()


@pytest.mark.asyncio
async def test_signup_order_uses_chronology_and_account_priority(
    repository: QsRepository,
) -> None:
    await repository.configure(
        10,
        20,
        30,
        "2026-11-01",
        "UTC",
        (1_000, 10_000, 20_000, 30_000, 40_000),
    )
    await repository.join(10, 20, 1, 100, "Account-100", created_at=10)
    await repository.join(10, 20, 2, 100, "Account-100", created_at=20)
    await repository.join(10, 20, 1, 103, "Account-103", created_at=15)
    await repository.join(10, 20, 2, 103, "Account-103", created_at=25)
    await repository.join(10, 20, 2, 101, "Account-101", created_at=30)
    await repository.join(10, 20, 2, 102, "Account-102", created_at=5)
    await repository.report(10, 20, 2, 102, "Account-102", "Player 102", 40)

    before_phase_one_ends = await repository.member_signups(10, 20, 2, now=5_000)
    assert before_phase_one_ends == (
        MemberSignup(102, "Account-102", True),
        MemberSignup(101, "Account-101"),
        MemberSignup(100, "Account-100"),
        MemberSignup(103, "Account-103"),
    )

    after_phase_one_ends = await repository.member_signups(10, 20, 2, now=8_201)
    assert after_phase_one_ends == (
        MemberSignup(102, "Account-102", True),
        MemberSignup(100, "Account-100"),
        MemberSignup(103, "Account-103"),
        MemberSignup(101, "Account-101"),
    )

    await repository.join(10, 20, 3, 102, "Account-102", created_at=40)
    await repository.join(10, 20, 3, 101, "Account-101", created_at=50)
    assert await repository.member_signups(10, 20, 3, now=5_000) == (
        MemberSignup(101, "Account-101"),
        MemberSignup(102, "Account-102", True),
    )


@pytest.mark.asyncio
async def test_destroyed_marker_matches_only_reported_main_account(
    repository: QsRepository,
) -> None:
    await repository.join(10, 20, 1, 100, None, created_at=10)
    await repository.join(10, 20, 1, 101, None, created_at=20)
    await repository.report(10, 20, 1, 100, None, "Player 100", 30)

    assert await repository.member_signups(10, 20, 1) == (
        MemberSignup(100, None, True),
        MemberSignup(101, None),
    )


@pytest.mark.asyncio
async def test_report_once_per_alias_and_base_across_phases(
    repository: QsRepository,
) -> None:
    assert await repository.database.execute(
        "INSERT INTO GameAccounts (Guild, Member, Account) VALUES (10, 100, 'Alt-100')"
    )
    await repository.report(10, 20, 1, 100, "Account-100", "Player", 123)
    with pytest.raises(DuplicateBaseReport):
        await repository.report(10, 20, 5, 100, "account-100", "Player", 124)
    await repository.report(10, 20, 2, 100, "Alt-100", "Player", 125)
    assert len(await repository.reports(10, 20)) == 2


@pytest.mark.asyncio
async def test_report_rejects_an_account_linked_to_another_member(
    repository: QsRepository,
) -> None:
    with pytest.raises(InvalidGameAccount):
        await repository.report(10, 20, 1, 100, "Account-101", "Player", 123)
    assert await repository.reports(10, 20) == ()


@pytest.mark.asyncio
async def test_display_name_report_is_independent_of_linked_accounts(
    repository: QsRepository,
) -> None:
    await repository.report(10, 20, 1, 100, None, "Player", 123)
    await repository.report(10, 20, 2, 100, "Account-100", "Player", 124)
    with pytest.raises(DuplicateBaseReport):
        await repository.report(10, 20, 3, 100, None, "New Name", 125)
    await repository.report(10, 20, 1, 9999, None, "No Alias", 124)
    reports = await repository.reports(10, 20)
    assert {(report.report_key, report.game_account) for report in reports} == {
        ("member:100", None),
        ("account:Account-100", "Account-100"),
        ("member:9999", None),
    }


@pytest.mark.asyncio
async def test_withdrawal_removes_only_the_selected_alias_report(
    repository: QsRepository,
) -> None:
    assert await repository.database.execute(
        "INSERT INTO GameAccounts (Guild, Member, Account) VALUES (10, 100, 'Alt-100')"
    )
    await repository.report(10, 20, 1, 100, "Account-100", "Player", 123)
    await repository.report(10, 20, 2, 100, "Alt-100", "Player", 124)
    assert await repository.withdraw_report(10, 20, 1, 100, "Account-100")
    remaining = await repository.reports(10, 20)
    assert len(remaining) == 1
    assert remaining[0].game_account == "Alt-100"


@pytest.mark.asyncio
async def test_concurrent_alias_reports_cannot_double_count(
    repository: QsRepository,
) -> None:
    results = await asyncio.gather(
        repository.report(10, 20, 1, 100, "Account-100", "Player", 123),
        repository.report(10, 20, 2, 100, "Account-100", "Player", 124),
        return_exceptions=True,
    )
    assert sum(isinstance(result, DuplicateBaseReport) for result in results) == 1
    assert len(await repository.reports(10, 20)) == 1


@pytest.mark.asyncio
async def test_total_bases_is_exactly_40(repository: QsRepository) -> None:
    for number in range(1, 41):
        member_id = number + 100
        await repository.report(
            10,
            20,
            number % 5 + 1,
            member_id,
            f"Account-{member_id}",
            "Player",
            number,
        )
    assert len(await repository.reports(10, 20)) == 40
    with pytest.raises(BaseLimitReached):
        await repository.report(10, 20, 1, 999, "Account-999", "Player", 0)


@pytest.mark.asyncio
async def test_configuration_update_retains_event_data(
    repository: QsRepository,
) -> None:
    assert await repository.toggle(10, 20, 1, 100)
    await repository.report(10, 20, 1, 100, "Account-100", "Player", 123)
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
    await repository.report(10, 20, 1, 100, "Account-100", "Player", 123)
    assert await repository.remove_member(10, 100, 20)
    assert await repository.members(10, 20, 1) == ()
    assert len(await repository.reports(10, 20)) == 1
    assert await repository.remove(10, 20)
    assert await repository.get(10, 20) is None
    assert await repository.phases(10, 20) == ()
    assert await repository.reports(10, 20) == ()


@pytest.mark.parametrize("duration", [1, 2, 3])
def test_supported_five_phase_durations(duration: int) -> None:
    starts = (1000,) * 5
    validate_schedule(1000, starts, (duration,) * 5)


@pytest.mark.parametrize(
    ("starts", "durations"),
    [
        ((1000,) * 4, (1,) * 4),
        ((1000,) * 6, (1,) * 6),
        ((1000,) * 5, (0,) * 5),
        ((1000,) * 5, (4,) * 5),
        ((999,) * 5, (1,) * 5),
        ((1000 + 86400 - 3600 + 1,) * 5, (1,) * 5),
        ((1000,) * 5, (1,) * 4),
    ],
)
def test_schedule_rejects_invalid_counts_durations_and_window(
    starts: tuple[int, ...], durations: tuple[int, ...]
) -> None:
    with pytest.raises(ValueError):
        validate_schedule(1000, starts, durations)


def test_phase_can_end_exactly_at_eruption_end() -> None:
    validate_schedule(1000, (1000 + 86400 - 10800,) * 5, (3,) * 5)


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
    starts = phase_starts("unused", (22, 23, 8, 12, 16), "UTC", eruption_start=start)
    assert starts[0] == int(parse_local_datetime("2026-11-02 22:00", "UTC").timestamp())
    with pytest.raises(ValueError):
        validate_schedule(start, starts, (1,) * 5)


@pytest.mark.parametrize("date", ["2026-03-28", "2026-10-24"])
def test_rolled_day_rejects_dst_missing_or_ambiguous_hour(date: str) -> None:
    start = int(parse_local_datetime(f"{date} 22:00", "Europe/Berlin").timestamp())
    with pytest.raises(ValueError):
        phase_starts(date, (22, 2, 8, 12, 16), "Europe/Berlin", eruption_start=start)


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
async def test_member_unique_reports_migrate_without_losing_existing_reports(
    repository: QsRepository,
) -> None:
    database = repository.database
    assert await database.execute("DROP TABLE HsQsBases")
    assert await database.execute(
        "CREATE TABLE HsQsBases (Guild INTEGER NOT NULL, Channel INTEGER NOT NULL, "
        "Phase INTEGER NOT NULL, Member INTEGER NOT NULL, DisplayName TEXT NOT NULL, "
        "CreatedAt INTEGER NOT NULL, PRIMARY KEY (Guild, Channel, Member), "
        "FOREIGN KEY (Guild, Channel, Phase) "
        "REFERENCES HsQsPhases (Guild, Channel, Phase) ON DELETE CASCADE) WITHOUT ROWID"
    )
    assert await database.execute(
        "INSERT INTO HsQsBases VALUES (10, 20, 1, 100, 'Old Player', 123)"
    )
    assert await repository.ensure_schema()
    reports = await repository.reports(10, 20)
    assert len(reports) == 1
    assert reports[0].display_name == "Old Player"
    assert reports[0].game_account is None
    assert reports[0].report_key == "member:100"
    await repository.report(10, 20, 2, 100, "Account-100", "Old Player", 124)
    assert len(await repository.reports(10, 20)) == 2


@pytest.mark.asyncio
async def test_account_unique_schema_migrates_alias_and_display_name_reports(
    repository: QsRepository,
) -> None:
    database = repository.database
    assert await database.execute("DROP TABLE HsQsBases")
    assert await database.execute(
        "CREATE TABLE HsQsBases (Guild INTEGER NOT NULL, Channel INTEGER NOT NULL, "
        "Phase INTEGER NOT NULL, Member INTEGER NOT NULL, Account TEXT COLLATE NOCASE "
        "NOT NULL, DisplayName TEXT NOT NULL, CreatedAt INTEGER NOT NULL, "
        "PRIMARY KEY (Guild, Channel, Account), FOREIGN KEY (Guild, Channel, Phase) "
        "REFERENCES HsQsPhases (Guild, Channel, Phase) ON DELETE CASCADE) WITHOUT ROWID"
    )
    assert await database.execute_many(
        "INSERT INTO HsQsBases VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            (10, 20, 1, 100, "Account-100", "Player 100", 123),
            (10, 20, 2, 101, "legacy:101", "Player 101", 124),
        ),
    )
    assert await repository.ensure_schema()
    reports = await repository.reports(10, 20)
    assert [(report.game_account, report.report_key) for report in reports] == [
        ("Account-100", "account:Account-100"),
        (None, "member:101"),
    ]


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
    assert reports[0].game_account is None
    assert reports[0].report_key == "member:100"
    columns = {
        row["name"] for row in await database.fetch_all("PRAGMA table_info(HsQsBases)")
    }
    assert "Base" not in columns and "Note" not in columns
    assert "DisplayName" in columns
    assert "Account" in columns
    assert "ReportKey" in columns
    assert not await database.fetch_all("PRAGMA foreign_key_check")
    await repository.report(10, 20, 2, 100, "Account-100", "Player", 124)
    await repository.report(10, 20, 2, 101, "Account-101", "Player Name", 124)
    assert len(await repository.reports(10, 20)) == 3


@pytest.mark.asyncio
async def test_concurrent_reports_cannot_exceed_forty(repository: QsRepository) -> None:
    for member_id in range(39):
        await repository.report(
            10, 20, 1, member_id, f"Account-{member_id}", "Player", member_id
        )
    results = await asyncio.gather(
        repository.report(10, 20, 1, 100, "Account-100", "A", 123),
        repository.report(10, 20, 1, 101, "Account-101", "B", 123),
        return_exceptions=True,
    )
    assert sum(isinstance(result, BaseLimitReached) for result in results) == 1
    assert len(await repository.reports(10, 20)) == 40
