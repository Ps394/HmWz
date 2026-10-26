from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.modules.queue.repositories import QueueRepository
from hmwz.sqlite_db import Database


def _guild(guild_id: int = 123) -> discord.Guild:
    return cast(discord.Guild, SimpleNamespace(id=guild_id, name="test guild"))


async def _create_eruption(
    repository: QueueRepository,
    *,
    guild: discord.Guild,
    channel_id: int = 456,
    starts_at: float | None = None,
    phases: tuple[tuple[float, float], ...] | None = None,
) -> int:
    now = time.time()
    eruption_start = now - 60 if starts_at is None else starts_at
    eruption_end = eruption_start + 24 * 60 * 60
    phase_list = phases or ((eruption_start, eruption_start + 3600),) * 3
    eruption_id = await repository.create_eruption(
        guild=guild,
        channel_id=channel_id,
        title="QS",
        description="Eruption",
        role_id=789,
        modal_prompt="Confirm your destruction",
        starts_at=eruption_start,
        ends_at=eruption_end,
        timezone_name="UTC",
        phases=phase_list,
        created_at=now,
    )
    assert isinstance(eruption_id, int)
    return eruption_id


@pytest.mark.asyncio
async def test_schema_preserves_legacy_queue_rows_and_mode_tables(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="queue-legacy.db")
    repository = QueueRepository(database)
    assert await database.execute(
        "CREATE TABLE Queue_Settings (Guild INTEGER, Channel INTEGER, "
        "Mode TEXT, Name TEXT)"
    )
    assert await database.execute(
        "CREATE TABLE Queue_Members (Guild INTEGER, Member INTEGER)"
    )
    assert await database.execute(
        "CREATE TABLE Queue_Seasons (Guild INTEGER, Channel INTEGER, Name TEXT)"
    )
    assert await database.execute(
        "INSERT INTO Queue_Settings (Guild, Channel, Mode, Name) "
        "VALUES (1, 3, 'seasons', 'Old queue')"
    )
    assert await database.execute(
        "INSERT INTO Queue_Members (Guild, Member) VALUES (1, 2)"
    )
    assert await database.execute(
        "INSERT INTO Queue_Seasons (Guild, Channel, Name) VALUES (1, 3, '08:00')"
    )

    assert await repository.ensure_schema()
    assert await repository.ensure_schema()
    eruption_id = await _create_eruption(
        repository,
        guild=_guild(1),
        channel_id=3,
    )
    legacy = await database.fetch_one(
        "SELECT Mode, Name FROM Queue_Settings WHERE Guild = 1 AND Channel = 3"
    )
    member = await database.fetch_one(
        "SELECT Member FROM Queue_Members WHERE Guild = 1"
    )
    season = await database.fetch_one("SELECT Name FROM Queue_Seasons WHERE Guild = 1")
    phase_settings = await database.fetch_one(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'Queue_QS_Phase_Settings'"
    )

    assert legacy is not None and legacy["Mode"] == "seasons"
    assert legacy["Name"] == "Old queue"
    assert eruption_id > 0
    assert member is not None and member["Member"] == 2
    assert season is not None and season["Name"] == "08:00"
    assert phase_settings is not None


@pytest.mark.asyncio
async def test_reminders_are_persisted_claimed_once_and_retried(
    tmp_path: Path,
) -> None:
    repository = QueueRepository(
        Database(folder=str(tmp_path), filename="queue-reminders.db")
    )
    assert await repository.ensure_schema()
    now = time.time()
    start = now + 7200
    eruption_id = await repository.create_eruption(
        guild=_guild(),
        channel_id=456,
        title="QS",
        description="",
        role_id=789,
        modal_prompt="Confirm",
        starts_at=start,
        ends_at=start + 86400,
        timezone_name="UTC",
        phases=((start + 3600, start + 7200),) * 3,
        created_at=now,
        phase_hours=(("08:00", 1), ("12:00", 1), ("16:00", 1)),
        reminder_settings=(True, 60, True, 60, True, 15),
    )
    assert isinstance(eruption_id, int)
    due = await repository.due_reminders(now + 3601)
    assert len(due) == 1
    reminder = due[0]
    assert reminder.kind == "eruption_start"
    assert await repository.claim_reminder(reminder, now + 3601)
    assert not await repository.claim_reminder(reminder, now + 3602)
    assert await repository.finish_reminder(
        reminder, success=False, retry_at=now + 3660
    )
    assert await repository.due_reminders(now + 3610) == ()
    retry = await repository.due_reminders(now + 3661)
    assert len(retry) == 1
    assert await repository.claim_reminder(retry[0], now + 3661)
    assert await repository.finish_reminder(retry[0], success=True, retry_at=now + 3700)
    assert await repository.due_reminders(now + 5000) == ()


@pytest.mark.asyncio
async def test_settings_changes_reschedule_only_enabled_reminders(
    tmp_path: Path,
) -> None:
    repository = QueueRepository(
        Database(folder=str(tmp_path), filename="queue-reminder-settings.db")
    )
    assert await repository.ensure_schema()
    now = time.time()
    start = now + 7200
    eruption_id = await repository.create_eruption(
        guild=_guild(),
        channel_id=456,
        title="QS",
        description="",
        role_id=789,
        modal_prompt="Confirm",
        starts_at=start,
        ends_at=start + 86400,
        timezone_name="UTC",
        phases=(
            (start + 3600, start + 7200),
            (start + 5 * 3600, start + 6 * 3600),
            (start + 9 * 3600, start + 10 * 3600),
        ),
        created_at=now,
        phase_hours=(("08:00", 1), ("12:00", 1), ("16:00", 1)),
        reminder_settings=(True, 60, True, 60, True, 15),
    )
    assert isinstance(eruption_id, int)
    config = await repository.get(guild=_guild(), channel_id=456)
    assert config is not None
    assert await repository.update_settings_for_eruption(
        guild=_guild(),
        configuration=config,
        title="QS",
        description="",
        role_id=789,
        modal_prompt="Confirm",
        timezone_name="UTC",
        phase_hours=(("08:00", 1), ("12:00", 1), ("16:00", 1)),
        remove_role_on_reset=True,
        reminder_settings=(False, 60, True, 45, False, 15),
        eruption_id=eruption_id,
        now=now,
    )
    rows = await repository.database.fetch_all(
        "SELECT Kind, Status FROM Queue_Reminders WHERE Eruption = ?",
        (eruption_id,),
    )
    assert {(row["Kind"], row["Status"]) for row in rows} == {
        ("eruption_end", "pending")
    }
    updated = await repository.get(guild=_guild(), channel_id=456)
    assert updated is not None and updated.remove_role_on_reset
    assert updated.eruption_end_reminder_minutes == 45


@pytest.mark.asyncio
async def test_reset_replaces_runtime_data_and_persists_next_start(
    tmp_path: Path,
) -> None:
    repository = QueueRepository(
        Database(folder=str(tmp_path), filename="queue-reset.db")
    )
    assert await repository.ensure_schema()
    now = time.time()
    old_start = now - 25 * 3600
    old_id = await _create_eruption(
        repository,
        guild=_guild(),
        starts_at=old_start,
        phases=(
            (old_start, old_start + 3600),
            (old_start + 4 * 3600, old_start + 5 * 3600),
            (old_start + 8 * 3600, old_start + 9 * 3600),
        ),
    )
    config = await repository.get(guild=_guild(), channel_id=456)
    assert config is not None
    new_start = now + 2 * 86400
    assert await repository.reset_eruption(
        guild=_guild(),
        configuration=config,
        old_eruption_id=old_id,
        starts_at=new_start,
        ends_at=new_start + 86400,
        phases=(
            (new_start + 8 * 3600, new_start + 9 * 3600),
            (new_start + 12 * 3600, new_start + 13 * 3600),
            (new_start + 16 * 3600, new_start + 17 * 3600),
        ),
        now=now,
    )
    assert await repository.get_eruption(guild=_guild(), eruption_id=old_id) is None
    current = await repository.get_latest_eruption(guild=_guild(), channel_id=456)
    assert current is not None and current.starts_at == new_start
    updated = await repository.get(guild=_guild(), channel_id=456)
    assert updated is not None and updated.next_start_at == new_start


@pytest.mark.asyncio
async def test_phase_signup_counts_unique_eruption_participants_and_caps_at_40(
    tmp_path: Path,
) -> None:
    repository = QueueRepository(
        Database(folder=str(tmp_path), filename="queue-capacity.db")
    )
    assert await repository.ensure_schema()
    guild = _guild()
    eruption_id = await _create_eruption(repository, guild=guild)
    phases = await repository.get_phases(eruption_id)
    assert len(phases) == 3

    results = await asyncio.gather(
        *(
            repository.join_phase(
                guild=guild,
                eruption_id=eruption_id,
                phase_id=phases[0].id,
                member_id=member_id,
                joined_at=time.time() + member_id / 1000,
                role_managed=False,
            )
            for member_id in range(1, 42)
        )
    )

    assert results.count("joined") == 40
    assert results.count("full") == 1
    assert len(await repository.get_eruption_participant_ids(eruption_id)) == 40

    assert (
        await repository.join_phase(
            guild=guild,
            eruption_id=eruption_id,
            phase_id=phases[1].id,
            member_id=1,
            joined_at=time.time() + 100,
            role_managed=False,
        )
        == "joined"
    )
    assert len(await repository.get_eruption_participant_ids(eruption_id)) == 40


@pytest.mark.asyncio
async def test_later_eruption_has_independent_phase_signups(
    tmp_path: Path,
) -> None:
    repository = QueueRepository(
        Database(folder=str(tmp_path), filename="queue-next-eruption.db")
    )
    assert await repository.ensure_schema()
    guild = _guild()
    now = time.time()
    previous_id = await _create_eruption(
        repository,
        guild=guild,
        starts_at=now - 25 * 60 * 60,
        phases=(
            (now - 25 * 60 * 60, now - 24 * 60 * 60),
            (now - 23 * 60 * 60, now - 22 * 60 * 60),
            (now - 21 * 60 * 60, now - 20 * 60 * 60),
        ),
    )
    next_id = await _create_eruption(
        repository,
        guild=guild,
        starts_at=now + 60,
        phases=(
            (now + 60, now + 3600),
            (now + 7200, now + 10800),
            (now + 14400, now + 18000),
        ),
    )
    next_phase = (await repository.get_phases(next_id))[0]

    assert previous_id != next_id
    assert await repository.get_eruption_participant_ids(next_id) == ()
    assert (
        await repository.join_phase(
            guild=guild,
            eruption_id=next_id,
            phase_id=next_phase.id,
            member_id=42,
            joined_at=now,
            role_managed=False,
        )
        == "joined"
    )
    assert await repository.get_eruption_participant_ids(previous_id) == ()
    assert await repository.get_eruption_participant_ids(next_id) == (42,)


@pytest.mark.asyncio
async def test_destruction_is_atomic_and_limited_to_one_per_eruption(
    tmp_path: Path,
) -> None:
    repository = QueueRepository(
        Database(folder=str(tmp_path), filename="queue-destruction.db")
    )
    assert await repository.ensure_schema()
    guild = _guild()
    now = time.time()
    eruption_id = await _create_eruption(
        repository,
        guild=guild,
        phases=((now - 300, now + 300),) * 3,
    )
    phase = (await repository.get_phases(eruption_id))[0]
    assert (
        await repository.join_phase(
            guild=guild,
            eruption_id=eruption_id,
            phase_id=phase.id,
            member_id=42,
            joined_at=now,
            role_managed=False,
        )
        == "joined"
    )

    results = await asyncio.gather(
        *(
            repository.record_destruction(
                guild=guild,
                eruption_id=eruption_id,
                phase_id=phase.id,
                member_id=42,
                confirmed_at=time.time(),
                details="confirmed",
            )
            for _ in range(2)
        )
    )

    assert results.count("confirmed") == 1
    assert results.count("already_confirmed") == 1
    assert len(await repository.get_destructions(eruption_id)) == 1


@pytest.mark.asyncio
async def test_destroying_in_another_phase_does_not_allow_a_second_confirmation(
    tmp_path: Path,
) -> None:
    repository = QueueRepository(
        Database(folder=str(tmp_path), filename="queue-phase-destruction.db")
    )
    assert await repository.ensure_schema()
    guild = _guild()
    now = time.time()
    eruption_id = await _create_eruption(
        repository,
        guild=guild,
        phases=((now - 300, now + 300), (now - 200, now + 400), (now, now + 500)),
    )
    first, second, _ = await repository.get_phases(eruption_id)
    for phase in (first, second):
        assert (
            await repository.join_phase(
                guild=guild,
                eruption_id=eruption_id,
                phase_id=phase.id,
                member_id=17,
                joined_at=now,
                role_managed=False,
            )
            == "joined"
        )
    assert (
        await repository.record_destruction(
            guild=guild,
            eruption_id=eruption_id,
            phase_id=first.id,
            member_id=17,
            confirmed_at=time.time(),
            details="first",
        )
        == "confirmed"
    )
    assert (
        await repository.record_destruction(
            guild=guild,
            eruption_id=eruption_id,
            phase_id=second.id,
            member_id=17,
            confirmed_at=time.time(),
            details="second",
        )
        == "already_confirmed"
    )


@pytest.mark.asyncio
async def test_role_is_only_removed_when_managed_by_queue_and_last_phase_left(
    tmp_path: Path,
) -> None:
    repository = QueueRepository(
        Database(folder=str(tmp_path), filename="queue-role.db")
    )
    assert await repository.ensure_schema()
    guild = _guild()
    eruption_id = await _create_eruption(repository, guild=guild)
    first, second, _ = await repository.get_phases(eruption_id)
    assert (
        await repository.join_phase(
            guild=guild,
            eruption_id=eruption_id,
            phase_id=first.id,
            member_id=100,
            joined_at=time.time(),
            role_managed=True,
        )
        == "joined"
    )
    assert (
        await repository.join_phase(
            guild=guild,
            eruption_id=eruption_id,
            phase_id=second.id,
            member_id=100,
            joined_at=time.time() + 1,
            role_managed=False,
        )
        == "joined"
    )
    assert (
        await repository.join_phase(
            guild=guild,
            eruption_id=eruption_id,
            phase_id=first.id,
            member_id=100,
            joined_at=time.time() + 2,
            role_managed=False,
        )
        == "left"
    )
    assert (
        await repository.join_phase(
            guild=guild,
            eruption_id=eruption_id,
            phase_id=second.id,
            member_id=100,
            joined_at=time.time() + 3,
            role_managed=False,
        )
        == "left_final_role_managed"
    )
