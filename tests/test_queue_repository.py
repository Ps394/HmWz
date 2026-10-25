from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.modules.queue.repository import QueueRepository, SeasonTask
from hmwz.modules.queue.rules import (
    can_start_early,
    season_start_timestamp,
    valid_run_range,
)
from hmwz.modules.queue.views import QueueOverviewView
from hmwz.modules.queue.module import QueueModule
from hmwz.modules.queue.modes import create_queue_modes
from hmwz.sqlite_db import Database


def test_min_max_range_and_early_start_thresholds() -> None:
    assert not valid_run_range(0, 5)
    assert valid_run_range(3, 5)
    assert valid_run_range(5, 5)
    assert not valid_run_range(6, 5)
    assert can_start_early(3, min_players=3, max_players=5)
    assert can_start_early(4, min_players=3, max_players=5)
    assert not can_start_early(2, min_players=3, max_players=5)
    assert not can_start_early(5, min_players=3, max_players=5)


def test_season_start_timestamp_validates_date_hour_and_timezone() -> None:
    assert season_start_timestamp("2025-01-02", "08:00", "UTC") == 1735804800
    assert season_start_timestamp("2025-01-02", "08:00", "Not/AZone") is None
    assert season_start_timestamp("2025-02-30", "08:00", "UTC") is None
    assert season_start_timestamp("2025-01-02", "24:00", "UTC") is None
    assert season_start_timestamp("2025-03-30", "02:00", "Europe/Berlin") is None


@pytest.mark.asyncio
async def test_season_start_gates_runs_and_goals_until_scheduled_time(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="season-start.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=654, name="test guild"))
    start = season_start_timestamp("2025-01-02", "08:00", "UTC")
    assert start is not None

    assert await repository.ensure_schema()
    assert await repository.configure(
        guild=guild,
        channel_id=321,
        title="Season queue",
        description="Scheduled season.",
        min_players=1,
        max_players=2,
        mode="seasons",
        confirmation_delay_minutes=0,
        ping_participants=True,
        season_start_date="2025-01-02",
        timezone="UTC",
    )
    assert await repository.replace_seasons(
        guild=guild,
        channel_id=321,
        seasons=("08:00",),
        goal_limit=2,
        goal_description="Complete goals.",
        start_date="2025-01-02",
        timezone="UTC",
    )
    season = await repository.get_next_season(guild=guild, channel_id=321)
    assert season is not None and season.starts_at == start
    assert await repository.get_due_seasons(guild=guild, now=start - 1) == ()
    assert await repository.join_season(
        guild=guild,
        channel_id=321,
        season_index=season.index,
        member_id=42,
        joined_at=start - 100,
    )
    assert not await repository.activate_season(
        guild=guild,
        channel_id=321,
        season_index=season.index,
        now=start - 1,
    )
    assert (
        await repository.create_run(
            guild=guild,
            channel_id=321,
            stage_index=None,
            season_index=season.index,
            thread_id=789,
            message_id=987,
            members=(42,),
            started_at=start - 1,
            confirmation_available_at=start - 1,
        )
        is None
    )
    assert await repository.get_runs(guild=guild, channel_id=321) == ()
    assert await repository.activate_season(
        guild=guild,
        channel_id=321,
        season_index=season.index,
        now=start,
    )
    assert await repository.get_unnotified_started_seasons(guild=guild, now=start) == (
        (321, season.index),
    )
    assert (
        await repository.record_goal(
            guild=guild,
            channel_id=321,
            season_index=season.index,
            member_id=42,
            text="Too early.",
            created_at=start - 1,
        )
        is None
    )
    assert await repository.record_goal(
        guild=guild,
        channel_id=321,
        season_index=season.index,
        member_id=42,
        text="On time.",
        created_at=start,
    ) == (1, False)
    assert await repository.mark_season_start_notified(
        guild=guild,
        channel_id=321,
        season_index=season.index,
    )
    assert await repository.get_unnotified_started_seasons(guild=guild, now=start) == ()


@pytest.mark.asyncio
async def test_early_start_button_is_available_only_for_staged_queues() -> None:
    module = cast(
        QueueModule,
        SimpleNamespace(guild=SimpleNamespace()),
    )

    staged_view = QueueOverviewView(module, 456, mode="stages")
    continuous_view = QueueOverviewView(module, 456, mode="continuous")

    assert any(
        getattr(item, "custom_id", None) == "queue:vote:456"
        for item in staged_view.children
    )
    assert all(
        getattr(item, "custom_id", None) != "queue:vote:456"
        for item in continuous_view.children
    )


@pytest.mark.asyncio
async def test_stage_configuration_and_unanimous_vote_persist(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="stages.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))

    assert await repository.ensure_schema()
    assert await repository.configure(
        guild=guild,
        channel_id=456,
        title="Evening Run",
        description="Join an evening group.",
        min_players=2,
        max_players=4,
        mode="stages",
        confirmation_delay_minutes=30,
        ping_participants=False,
    )
    assert await repository.replace_stages(
        guild=guild,
        channel_id=456,
        stages=("Bronze", "Silver"),
    )
    assert [
        stage.name for stage in await repository.get_stages(guild=guild, channel_id=456)
    ] == ["Bronze", "Silver"]
    configuration = await repository.get(guild=guild, channel_id=456)
    assert configuration is not None
    assert configuration.min_players == 2
    assert configuration.max_players == 4
    assert configuration.mode == "stages"
    assert not configuration.ping_participants

    assert await repository.join(
        guild=guild,
        channel_id=456,
        member_id=11,
        joined_at=10.0,
        stage_index=0,
    )
    assert await repository.join(
        guild=guild,
        channel_id=456,
        member_id=12,
        joined_at=11.0,
        stage_index=0,
    )
    vote_id = await repository.create_early_vote(
        guild=guild,
        channel_id=456,
        stage_index=0,
        message_id=999,
        members=(11, 12),
    )
    assert vote_id is not None
    assert await repository.cast_vote(vote_id=vote_id, member_id=11, vote_value=1)
    assert await repository.cast_vote(vote_id=vote_id, member_id=12, vote_value=1)
    assert await repository.get_vote_members(vote_id) == ((11, 1), (12, 1))
    assert await repository.close_vote(vote_id=vote_id, status="accepted")
    assert await repository.get_open_votes(guild=guild) == ()


@pytest.mark.asyncio
async def test_run_confirmation_and_season_goals_are_persisted(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="season.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=321, name="test guild"))

    assert await repository.ensure_schema()
    assert await repository.configure(
        guild=guild,
        channel_id=654,
        title="Campaign",
        description="Campaign queue",
        min_players=2,
        max_players=2,
        mode="seasons",
        confirmation_delay_minutes=0,
        ping_participants=True,
    )
    configuration = await repository.get(guild=guild, channel_id=654)
    assert configuration is not None and configuration.ping_participants
    assert await repository.replace_seasons(
        guild=guild,
        channel_id=654,
        seasons=("08:00",),
        goal_limit=2,
        goal_description="Reach two objectives.",
    )
    season = await repository.get_next_season(guild=guild, channel_id=654)
    assert season is not None
    assert season.name == "08:00"
    assert season.goal_limit == 2
    assert season.goal_description == "Reach two objectives."
    run_id = await repository.create_run(
        guild=guild,
        channel_id=654,
        stage_index=None,
        season_index=season.index,
        thread_id=789,
        message_id=987,
        members=(21, 22),
        started_at=100.0,
        confirmation_available_at=100.0,
    )
    assert run_id is not None
    run = await repository.get_run(run_id)
    assert run is not None
    assert run.season_index == season.index
    assert await repository.record_goal(
        guild=guild,
        channel_id=654,
        season_index=season.index,
        member_id=21,
        text="First objective.",
        created_at=200.0,
    ) == (1, False)
    assert await repository.replace_seasons(
        guild=guild,
        channel_id=654,
        seasons=("08:00", "09:00"),
        goal_limit=3,
        goal_description="Use one shared objective label.",
    )
    seasons = await repository.get_seasons(guild=guild, channel_id=654)
    assert [item.name for item in seasons] == ["08:00", "09:00"]
    assert {(item.goal_limit, item.goal_description) for item in seasons} == {
        (3, "Use one shared objective label.")
    }
    updated_season = await repository.get_season(
        guild=guild, channel_id=654, season_index=season.index
    )
    assert updated_season is not None
    assert updated_season.goals_completed == 1
    assert updated_season.status == "active"
    assert await repository.record_goal(
        guild=guild,
        channel_id=654,
        season_index=season.index,
        member_id=22,
        text="Second objective.",
        created_at=300.0,
    ) == (2, False)
    assert await repository.record_goal(
        guild=guild,
        channel_id=654,
        season_index=season.index,
        member_id=22,
        text="Third objective.",
        created_at=350.0,
    ) == (3, True)
    assert (
        await repository.record_goal(
            guild=guild,
            channel_id=654,
            season_index=season.index,
            member_id=22,
            text="An extra objective.",
            created_at=400.0,
        )
        is None
    )
    saved_season = await repository.get_season(
        guild=guild,
        channel_id=654,
        season_index=season.index,
    )
    assert saved_season is not None
    assert saved_season.status == "completed"
    assert saved_season.thread_id == 789
    assert saved_season.message_id == 987
    assert saved_season.goals_completed == 3
    assert (
        len(
            await repository.get_goals(
                guild=guild, channel_id=654, season_index=season.index
            )
        )
        == 3
    )


@pytest.mark.asyncio
async def test_remove_deletes_all_queue_data_without_affecting_other_queues(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="remove-queue.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=789, name="test guild"))

    assert await repository.ensure_schema()
    for channel_id in (456, 654):
        assert await repository.configure(
            guild=guild,
            channel_id=channel_id,
            title=f"Queue {channel_id}",
            description="Queue description",
            min_players=1,
            max_players=2,
            mode="seasons",
            confirmation_delay_minutes=0,
            ping_participants=False,
        )

    assert await repository.replace_stages(
        guild=guild, channel_id=456, stages=("Bronze",)
    )
    assert await repository.replace_seasons(
        guild=guild,
        channel_id=456,
        seasons=("00:00", "12:00"),
        goal_limit=2,
        goal_description="Complete objectives.",
    )
    assert await repository.join(
        guild=guild,
        channel_id=456,
        member_id=11,
        joined_at=10.0,
        stage_index=0,
    )
    season = await repository.get_next_season(guild=guild, channel_id=456)
    assert season is not None
    run_id = await repository.create_run(
        guild=guild,
        channel_id=456,
        stage_index=0,
        season_index=season.index,
        thread_id=111,
        message_id=222,
        members=(12, 13),
        started_at=100.0,
        confirmation_available_at=100.0,
    )
    assert run_id is not None
    assert await repository.record_goal(
        guild=guild,
        channel_id=456,
        season_index=season.index,
        member_id=12,
        text="First objective.",
        created_at=200.0,
    ) == (1, False)
    assert await repository.complete_run(run_id)
    runs = await repository.get_runs(guild=guild, channel_id=456)
    assert len(runs) == 1 and runs[0].id == run_id
    vote_id = await repository.create_early_vote(
        guild=guild,
        channel_id=456,
        stage_index=0,
        message_id=333,
        members=(11, 12),
    )
    assert vote_id is not None

    assert await repository.completed_count(guild=guild, channel_id=456) == 1
    assert await repository.remove(guild=guild, channel_id=456)
    assert await repository.completed_count(guild=guild, channel_id=456) == 0
    assert await repository.get(guild=guild, channel_id=456) is None
    assert await repository.get_run(run_id) is None
    assert await repository.get_run_participants(run_id) == ()
    assert await repository.get_vote_members(vote_id) == ()
    for table in (
        repository.goals_table,
        repository.seasons_table,
        repository.stages_table,
        repository.members_table,
        repository.runs_table,
        repository.votes_table,
    ):
        row = await database.fetch_one(
            f"SELECT COUNT(*) FROM {table} WHERE Guild = ? AND Channel = ?",
            (guild.id, 456),
        )
        assert row is not None and row[0] == 0
    for table, foreign_key, parent_id in (
        (repository.participants_table, "Run", run_id),
        (repository.vote_members_table, "Vote", vote_id),
    ):
        row = await database.fetch_one(
            f"SELECT COUNT(*) FROM {table} WHERE {foreign_key} = ?", (parent_id,)
        )
        assert row is not None and row[0] == 0

    untouched_queue = await repository.get(guild=guild, channel_id=654)
    assert untouched_queue is not None


@pytest.mark.asyncio
async def test_season_memberships_are_independent_and_reset_keeps_threads(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="season-members.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=987, name="test guild"))

    assert await repository.ensure_schema()
    assert await repository.configure(
        guild=guild,
        channel_id=654,
        title="Season queue",
        description="Join multiple seasons.",
        min_players=1,
        max_players=2,
        mode="seasons",
        confirmation_delay_minutes=0,
        ping_participants=False,
    )
    assert await repository.replace_seasons(
        guild=guild,
        channel_id=654,
        seasons=("08:00", "09:00"),
        goal_limit=3,
        goal_description="Complete goals.",
    )

    for season_index in (8, 9):
        assert await repository.join_season(
            guild=guild,
            channel_id=654,
            season_index=season_index,
            member_id=42,
            joined_at=float(season_index),
        )
        assert await repository.set_season_thread(
            guild=guild,
            channel_id=654,
            season_index=season_index,
            thread_id=1000 + season_index,
            message_id=2000 + season_index,
        )
    assert await repository.get_season_members(
        guild=guild, channel_id=654, season_index=8
    ) == (42,)
    assert await repository.get_season_members(
        guild=guild, channel_id=654, season_index=9
    ) == (42,)
    assert await repository.has_season_members(guild=guild, channel_id=654)
    assert await repository.activate_season(
        guild=guild,
        channel_id=654,
        season_index=8,
        now=100.0,
    )
    assert await repository.record_goal(
        guild=guild,
        channel_id=654,
        season_index=8,
        member_id=42,
        text="First goal.",
        created_at=100.0,
    ) == (1, False)
    assert await repository.replace_season_tasks(
        guild=guild,
        channel_id=654,
        tasks=(("Complete goals", 2),),
    )
    assert await repository.record_task_completion(
        guild=guild,
        channel_id=654,
        season_index=8,
        task_index=1,
        member_id=42,
        text="Task done",
        created_at=100.0,
    ) == (1, False)

    assert await repository.reset_season_queue(guild=guild, channel_id=654)

    for season_index in (8, 9):
        season = await repository.get_season(
            guild=guild, channel_id=654, season_index=season_index
        )
        assert season is not None
        assert season.goals_completed == 0
        assert season.status == "pending"
        assert season.thread_id == 1000 + season_index
        assert (
            await repository.get_season_members(
                guild=guild, channel_id=654, season_index=season_index
            )
            == ()
        )
    assert not await repository.has_season_members(guild=guild, channel_id=654)
    assert await repository.get_goals(guild=guild, channel_id=654, season_index=8) == ()
    assert (
        await repository.get_member_task_completion(
            guild=guild, channel_id=654, member_id=42
        )
        is None
    )
    assert await repository.get_season_tasks(guild=guild, channel_id=654) == (
        SeasonTask(1, "Complete goals", 2, 0),
    )


@pytest.mark.asyncio
async def test_replace_seasons_rejects_more_than_six_seasons(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="too-many-seasons.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=777, name="test guild"))

    assert await repository.ensure_schema()
    assert not await repository.replace_seasons(
        guild=guild,
        channel_id=654,
        seasons=tuple(f"{hour:02}:00" for hour in range(7)),
        goal_limit=1,
        goal_description="Complete a goal.",
    )


@pytest.mark.asyncio
async def test_existing_queue_schema_is_migrated(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="legacy-queue.db")
    assert await database.execute(
        """
        CREATE TABLE Queue_Settings (
            Guild INTEGER NOT NULL,
            Channel INTEGER NOT NULL,
            Name TEXT NOT NULL,
            MinPlayers INTEGER NOT NULL,
            MaxPlayers INTEGER NOT NULL,
            ConfirmationDelayMinutes INTEGER NOT NULL,
            ReminderIntervalMinutes INTEGER NOT NULL,
            Message INTEGER,
            PRIMARY KEY (Guild, Channel)
        ) WITHOUT ROWID
        """
    )
    assert await database.execute(
        """
        INSERT INTO Queue_Settings
            (Guild, Channel, Name, MinPlayers, MaxPlayers,
             ConfirmationDelayMinutes, ReminderIntervalMinutes)
        VALUES (123, 456, 'Legacy queue', 0, 5, 30, 15)
        """
    )
    assert await database.execute(
        """
        CREATE TABLE Queue_Members (
            Guild INTEGER NOT NULL,
            Channel INTEGER NOT NULL,
            Member INTEGER NOT NULL,
            JoinedAt REAL NOT NULL,
            PRIMARY KEY (Guild, Channel, Member)
        ) WITHOUT ROWID
        """
    )
    assert await database.execute(
        """
        CREATE TABLE Queue_Runs (
            Id INTEGER PRIMARY KEY AUTOINCREMENT,
            Guild INTEGER NOT NULL,
            Channel INTEGER NOT NULL,
            Thread INTEGER NOT NULL,
            Message INTEGER NOT NULL,
            StartedAt REAL NOT NULL,
            ConfirmationAvailableAt REAL NOT NULL,
            Status TEXT NOT NULL DEFAULT 'active'
        )
        """
    )
    assert await database.execute(
        """
        CREATE TABLE Queue_Run_Members (
            Run INTEGER NOT NULL,
            Member INTEGER NOT NULL,
            ConfirmedAt REAL,
            LastRemindedAt REAL,
            PRIMARY KEY (Run, Member)
        ) WITHOUT ROWID
        """
    )
    assert await database.execute(
        """
        CREATE TABLE Queue_Seasons (
            Guild INTEGER NOT NULL,
            Channel INTEGER NOT NULL,
            SeasonIndex INTEGER NOT NULL,
            Name TEXT NOT NULL,
            GoalLimit INTEGER NOT NULL,
            GoalDescription TEXT NOT NULL,
            GoalsCompleted INTEGER NOT NULL DEFAULT 0,
            Status TEXT NOT NULL DEFAULT 'pending',
            Thread INTEGER,
            Message INTEGER,
            PRIMARY KEY (Guild, Channel, SeasonIndex)
        ) WITHOUT ROWID
        """
    )
    assert await database.execute(
        """
        INSERT INTO Queue_Seasons
            (Guild, Channel, SeasonIndex, Name, GoalLimit, GoalDescription, Status)
        VALUES (123, 456, 8, '08:00', 3, 'Legacy goals', 'active')
        """
    )
    repository = QueueRepository(database)
    assert await repository.ensure_schema()
    settings_columns = {
        row["name"]
        for row in await database.fetch_all('PRAGMA table_info("Queue_Settings")')
    }
    assert {"Title", "Description", "Mode"} <= settings_columns
    assert "PingParticipants" in settings_columns
    assert "ReminderIntervalMinutes" not in settings_columns
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))
    migrated = await repository.get(guild=guild, channel_id=456)
    assert migrated is not None
    assert migrated.title == "Legacy queue"
    assert migrated.min_players == 1
    assert not migrated.ping_participants
    migrated_season = await repository.get_season(
        guild=guild, channel_id=456, season_index=8
    )
    assert migrated_season is not None and migrated_season.start_notified
    member_columns = {
        row["name"]
        for row in await database.fetch_all('PRAGMA table_info("Queue_Members")')
    }
    assert "StageIndex" in member_columns
    run_columns = {
        row["name"]
        for row in await database.fetch_all('PRAGMA table_info("Queue_Runs")')
    }
    assert {"StageIndex", "SeasonIndex"} <= run_columns
    participant_columns = {
        row["name"]
        for row in await database.fetch_all('PRAGMA table_info("Queue_Run_Members")')
    }
    assert "LastRemindedAt" not in participant_columns


@pytest.mark.asyncio
async def test_queue_mode_strategies_join_and_leave_their_own_pool(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="queue-modes.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=111, name="test guild"))
    modes = create_queue_modes()

    assert await repository.ensure_schema()
    for channel_id, mode in enumerate(("continuous", "stages", "seasons"), 1):
        assert await repository.configure(
            guild=guild,
            channel_id=channel_id,
            title=f"Queue {mode}",
            description="",
            min_players=1,
            max_players=2,
            mode=mode,
            confirmation_delay_minutes=0,
            ping_participants=False,
        )
        if mode == "stages":
            assert await repository.replace_stages(
                guild=guild, channel_id=channel_id, stages=("Level 1", "Level 2")
            )
            pool_index = 1
        elif mode == "seasons":
            assert await repository.replace_seasons(
                guild=guild,
                channel_id=channel_id,
                seasons=("08:00",),
                goal_limit=1,
                goal_description="Legacy value",
            )
            pool_index = 8
        else:
            pool_index = 0

        strategy = modes[mode]
        assert await strategy.join(
            repository, guild, channel_id, 42, pool_index, float(channel_id)
        )
        pools = await strategy.get_pools(repository, guild, channel_id, max_players=2)
        selected_pool = next(pool for pool in pools if pool.index == pool_index)
        assert selected_pool.members == (42,)
        assert await strategy.leave(repository, guild, channel_id, 42, pool_index)
        pools = await strategy.get_pools(repository, guild, channel_id, max_players=2)
        selected_pool = next(pool for pool in pools if pool.index == pool_index)
        assert selected_pool.members == ()


@pytest.mark.asyncio
async def test_season_task_limits_and_member_uniqueness_span_all_threads(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="season-task-limits.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=222, name="test guild"))
    channel_id = 333

    assert await repository.ensure_schema()
    assert await repository.configure(
        guild=guild,
        channel_id=channel_id,
        title="Season queue",
        description="",
        min_players=1,
        max_players=2,
        mode="seasons",
        confirmation_delay_minutes=0,
        ping_participants=False,
        season_start_date="1970-01-01",
        timezone="UTC",
        season_duration_hours=12,
    )
    assert await repository.replace_seasons(
        guild=guild,
        channel_id=channel_id,
        seasons=("00:00", "01:00"),
        goal_limit=1,
        goal_description="Legacy value",
        start_date="1970-01-01",
        timezone="UTC",
        duration_hours=12,
    )
    assert await repository.replace_season_tasks(
        guild=guild,
        channel_id=channel_id,
        tasks=(("Secure target", 1), ("Hold area", 2)),
    )
    for member_id, season_index in ((42, 0), (42, 1), (43, 0), (44, 1)):
        assert await repository.join_season(
            guild=guild,
            channel_id=channel_id,
            season_index=season_index,
            member_id=member_id,
            joined_at=member_id,
        )
    assert await repository.activate_season(
        guild=guild, channel_id=channel_id, season_index=0, now=100
    )
    assert await repository.activate_season(
        guild=guild, channel_id=channel_id, season_index=1, now=3700
    )

    assert await repository.record_task_completion(
        guild=guild,
        channel_id=channel_id,
        season_index=0,
        task_index=1,
        member_id=42,
        text="done",
        created_at=100,
    ) == (1, False)
    assert (
        await repository.record_task_completion(
            guild=guild,
            channel_id=channel_id,
            season_index=1,
            task_index=2,
            member_id=42,
            text="second thread",
            created_at=3700,
        )
        is None
    )
    assert (
        await repository.record_task_completion(
            guild=guild,
            channel_id=channel_id,
            season_index=0,
            task_index=1,
            member_id=43,
            text="full task",
            created_at=100,
        )
        is None
    )
    assert await repository.record_task_completion(
        guild=guild,
        channel_id=channel_id,
        season_index=0,
        task_index=2,
        member_id=43,
        text="done",
        created_at=100,
    ) == (1, False)
    assert await repository.record_task_completion(
        guild=guild,
        channel_id=channel_id,
        season_index=1,
        task_index=2,
        member_id=44,
        text="done",
        created_at=3700,
    ) == (2, True)
    assert all(
        season.status == "completed"
        for season in await repository.get_seasons(guild=guild, channel_id=channel_id)
    )
    assert [
        (task.label, task.completed, task.completion_limit)
        for task in await repository.get_season_tasks(
            guild=guild, channel_id=channel_id
        )
    ] == [("Secure target", 1, 1), ("Hold area", 2, 2)]


@pytest.mark.asyncio
async def test_season_duration_expires_active_season(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="season-duration.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=444, name="test guild"))

    assert await repository.ensure_schema()
    assert await repository.configure(
        guild=guild,
        channel_id=555,
        title="Season queue",
        description="",
        min_players=1,
        max_players=2,
        mode="seasons",
        confirmation_delay_minutes=0,
        ping_participants=False,
        season_start_date="1970-01-01",
        timezone="UTC",
        season_duration_hours=12,
    )
    assert await repository.replace_seasons(
        guild=guild,
        channel_id=555,
        seasons=("00:00",),
        goal_limit=1,
        goal_description="Legacy value",
        start_date="1970-01-01",
        timezone="UTC",
        duration_hours=12,
    )
    assert await repository.activate_season(
        guild=guild, channel_id=555, season_index=0, now=100
    )
    assert await repository.get_expired_seasons(guild=guild, now=43199) == ()
    assert await repository.get_expired_seasons(guild=guild, now=43200) == ((555, 0),)
    assert await repository.expire_season(
        guild=guild, channel_id=555, season_index=0, now=43200
    )
    season = await repository.get_season(guild=guild, channel_id=555, season_index=0)
    assert season is not None and season.duration_hours == 12
    assert season.status == "completed"


@pytest.mark.asyncio
async def test_clear_mode_data_preserves_shared_queue_configuration(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="clear-mode-data.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=666, name="test guild"))

    assert await repository.ensure_schema()
    assert await repository.configure(
        guild=guild,
        channel_id=777,
        title="Shared title",
        description="Shared description",
        min_players=2,
        max_players=4,
        mode="stages",
        confirmation_delay_minutes=15,
        ping_participants=True,
    )
    assert await repository.replace_stages(
        guild=guild, channel_id=777, stages=("Stage 1",)
    )
    assert await repository.join(
        guild=guild,
        channel_id=777,
        member_id=42,
        joined_at=1,
        stage_index=0,
    )
    run_id = await repository.create_run(
        guild=guild,
        channel_id=777,
        stage_index=0,
        season_index=None,
        thread_id=888,
        message_id=999,
        members=(42,),
        started_at=10,
        confirmation_available_at=10,
    )
    assert run_id is not None

    assert await repository.clear_mode_data(guild=guild, channel_id=777)

    configuration = await repository.get(guild=guild, channel_id=777)
    assert configuration is not None
    assert configuration.title == "Shared title"
    assert configuration.description == "Shared description"
    assert configuration.ping_participants
    assert await repository.get_waiting_members(guild=guild, channel_id=777) == ()
    assert await repository.get_stages(guild=guild, channel_id=777) == ()
    assert await repository.get_runs(guild=guild, channel_id=777) == ()
    assert await repository.get_run_participants(run_id) == ()
