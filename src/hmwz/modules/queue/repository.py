from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import discord
from aiosqlite import Row

from hmwz import sqlite_db

from .rules import season_start_timestamp

_logger = logging.getLogger(__name__)

QueueMode = Literal["continuous", "stages", "seasons"]


@dataclass(frozen=True, slots=True)
class QueueConfiguration:
    guild_id: int
    channel_id: int
    title: str
    description: str
    min_players: int
    max_players: int
    mode: QueueMode
    confirmation_delay_minutes: int
    ping_participants: bool
    message_id: int | None
    season_start_date: str
    stage_prefix: str
    season_duration_hours: int


@dataclass(frozen=True, slots=True)
class QueueStage:
    index: int
    name: str


@dataclass(frozen=True, slots=True)
class QueueSeason:
    index: int
    name: str
    goal_limit: int
    goal_description: str
    goals_completed: int
    status: str
    thread_id: int | None
    message_id: int | None
    starts_at: float
    start_notified: bool
    duration_hours: int


@dataclass(frozen=True, slots=True)
class QueueRun:
    id: int
    guild_id: int
    channel_id: int
    stage_index: int | None
    season_index: int | None
    thread_id: int
    message_id: int
    started_at: float
    confirmation_available_at: float
    status: str


@dataclass(frozen=True, slots=True)
class RunParticipant:
    member_id: int
    confirmed_at: float | None


@dataclass(frozen=True, slots=True)
class GoalEntry:
    member_id: int
    text: str
    created_at: float
    task_index: int = 0


@dataclass(frozen=True, slots=True)
class SeasonTask:
    index: int
    label: str
    completion_limit: int
    completed: int


class QueueRepository(sqlite_db.Base):
    """Persist queue setup, waiting lists, runs, and season goals."""

    table_name = "Queue_Settings"
    members_table = "Queue_Members"
    runs_table = "Queue_Runs"
    participants_table = "Queue_Run_Members"
    stages_table = "Queue_Stages"
    seasons_table = "Queue_Seasons"
    season_members_table = "Queue_Season_Members"
    goals_table = "Queue_Goals"
    season_tasks_table = "Queue_Season_Tasks"
    task_completions_table = "Queue_Task_Completions"
    votes_table = "Queue_EarlyVotes"
    vote_members_table = "Queue_EarlyVote_Members"

    @property
    def tables(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Name TEXT NOT NULL DEFAULT '',
                MinPlayers INTEGER NOT NULL DEFAULT 1,
                MaxPlayers INTEGER NOT NULL DEFAULT 1,
                ConfirmationDelayMinutes INTEGER NOT NULL DEFAULT 30,
                PingParticipants INTEGER NOT NULL DEFAULT 0,
                Message INTEGER,
                Title TEXT NOT NULL DEFAULT '',
                Description TEXT NOT NULL DEFAULT '',
                Mode TEXT NOT NULL DEFAULT 'continuous',
                SeasonStartDate TEXT NOT NULL DEFAULT '',
                TimeZone TEXT NOT NULL DEFAULT 'Europe/Berlin',
                StagePrefix TEXT NOT NULL DEFAULT '',
                SeasonDurationHours INTEGER NOT NULL DEFAULT 24,
                PRIMARY KEY (Guild, Channel)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.members_table} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                JoinedAt REAL NOT NULL,
                StageIndex INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (Guild, Channel, Member)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.runs_table} (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                StageIndex INTEGER,
                SeasonIndex INTEGER,
                Thread INTEGER NOT NULL,
                Message INTEGER NOT NULL,
                StartedAt REAL NOT NULL,
                ConfirmationAvailableAt REAL NOT NULL,
                Status TEXT NOT NULL DEFAULT 'active'
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.participants_table} (
                Run INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                ConfirmedAt REAL,
                PRIMARY KEY (Run, Member)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.stages_table} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                StageIndex INTEGER NOT NULL,
                Name TEXT NOT NULL,
                PRIMARY KEY (Guild, Channel, StageIndex)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.seasons_table} (
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
                StartsAt REAL NOT NULL DEFAULT 0,
                StartNotified INTEGER NOT NULL DEFAULT 0,
                DurationHours INTEGER NOT NULL DEFAULT 24,
                PRIMARY KEY (Guild, Channel, SeasonIndex)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.goals_table} (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                SeasonIndex INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                Text TEXT NOT NULL,
                CreatedAt REAL NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.season_members_table} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                SeasonIndex INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                JoinedAt REAL NOT NULL,
                PRIMARY KEY (Guild, Channel, SeasonIndex, Member)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.season_tasks_table} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                TaskIndex INTEGER NOT NULL,
                Label TEXT NOT NULL,
                CompletionLimit INTEGER NOT NULL,
                PRIMARY KEY (Guild, Channel, TaskIndex)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.task_completions_table} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                TaskIndex INTEGER NOT NULL,
                SeasonIndex INTEGER NOT NULL,
                Text TEXT NOT NULL,
                CreatedAt REAL NOT NULL,
                PRIMARY KEY (Guild, Channel, Member)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.votes_table} (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                StageIndex INTEGER NOT NULL,
                Message INTEGER NOT NULL,
                Status TEXT NOT NULL DEFAULT 'open'
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.vote_members_table} (
                Vote INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                VoteValue INTEGER,
                PRIMARY KEY (Vote, Member)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE INDEX IF NOT EXISTS IX_Queue_Runs_Guild_Channel_Status
            ON {self.runs_table} (Guild, Channel, Status)
            """,
        )

    async def ensure_schema(self) -> bool:
        for statement in self.tables:
            if not await self.database.execute(statement):
                _logger.error("Failed to create queue schema.")
                return False
        migrations = (
            (
                self.table_name,
                (
                    ("Title", "TEXT NOT NULL DEFAULT ''"),
                    ("Description", "TEXT NOT NULL DEFAULT ''"),
                    ("Mode", "TEXT NOT NULL DEFAULT 'continuous'"),
                    ("PingParticipants", "INTEGER NOT NULL DEFAULT 0"),
                    ("SeasonStartDate", "TEXT NOT NULL DEFAULT ''"),
                    ("TimeZone", "TEXT NOT NULL DEFAULT 'Europe/Berlin'"),
                    ("StagePrefix", "TEXT NOT NULL DEFAULT ''"),
                    ("SeasonDurationHours", "INTEGER NOT NULL DEFAULT 24"),
                ),
            ),
            (self.members_table, (("StageIndex", "INTEGER NOT NULL DEFAULT 0"),)),
            (
                self.seasons_table,
                (
                    ("StartsAt", "REAL NOT NULL DEFAULT 0"),
                    ("StartNotified", "INTEGER NOT NULL DEFAULT 0"),
                    ("DurationHours", "INTEGER NOT NULL DEFAULT 24"),
                ),
            ),
            (
                self.runs_table,
                (
                    ("StageIndex", "INTEGER"),
                    ("SeasonIndex", "INTEGER"),
                ),
            ),
        )
        migrated_season_start_times = False
        for table_name, columns in migrations:
            rows = await self.database.fetch_all(f'PRAGMA table_info("{table_name}")')
            existing = {row["name"] for row in rows}
            for column_name, column_type in columns:
                if column_name not in existing and not await self.database.execute(
                    f'ALTER TABLE "{table_name}" '
                    f'ADD COLUMN "{column_name}" {column_type}'
                ):
                    _logger.error(
                        "Failed to migrate queue table %s column %s.",
                        table_name,
                        column_name,
                    )
                    return False
                if (
                    table_name == self.seasons_table
                    and column_name == "StartsAt"
                    and column_name not in existing
                ):
                    migrated_season_start_times = True
        if migrated_season_start_times and not await self.database.execute(
            f"""
            UPDATE {self.seasons_table}
            SET StartNotified = 1
            WHERE StartsAt = 0 AND Status IN ('active', 'completed')
            """
        ):
            return False
        if not await self.database.execute(
            f"""
            INSERT OR IGNORE INTO {self.task_completions_table}
                (Guild, Channel, Member, TaskIndex, SeasonIndex, Text, CreatedAt)
            SELECT old.Guild, old.Channel, old.Member, 0, old.SeasonIndex,
                   old.Text, old.CreatedAt
            FROM {self.goals_table} old
            WHERE old.Id = (
                SELECT MIN(first.Id) FROM {self.goals_table} first
                WHERE first.Guild = old.Guild AND first.Channel = old.Channel
                  AND first.Member = old.Member
            )
            """
        ):
            _logger.error("Failed to migrate existing season task completions.")
            return False
        removed_columns = (
            (self.table_name, "ReminderIntervalMinutes"),
            (self.participants_table, "LastRemindedAt"),
        )
        for table_name, column_name in removed_columns:
            rows = await self.database.fetch_all(f'PRAGMA table_info("{table_name}")')
            if column_name in {
                row["name"] for row in rows
            } and not await self.database.execute(
                f'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}"'
            ):
                _logger.error(
                    "Failed to remove obsolete queue column %s from %s.",
                    column_name,
                    table_name,
                )
                return False
        if not await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET Title = Name
            WHERE Title = '' AND Name != ''
            """
        ):
            return False
        if not await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET MaxPlayers = CASE
                    WHEN MaxPlayers < 1 THEN 1
                    WHEN MaxPlayers > 100 THEN 100
                    ELSE MaxPlayers
                END,
                MinPlayers = CASE
                    WHEN MinPlayers < 1 OR MinPlayers > MaxPlayers THEN 1
                    ELSE MinPlayers
                END
            """
        ):
            return False
        return True

    async def configure(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        title: str,
        description: str,
        min_players: int,
        max_players: int,
        mode: QueueMode,
        confirmation_delay_minutes: int,
        ping_participants: bool,
        season_start_date: str = "",
        timezone: str = "Europe/Berlin",
        stage_prefix: str = "",
        season_duration_hours: int = 24,
    ) -> bool:
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.table_name}
                    (Guild, Channel, Name, Title, Description, MinPlayers,
                     MaxPlayers, Mode, ConfirmationDelayMinutes, PingParticipants,
                     SeasonStartDate, TimeZone, StagePrefix, SeasonDurationHours)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (Guild, Channel) DO UPDATE SET
                    Name = excluded.Name,
                    Title = excluded.Title,
                    Description = excluded.Description,
                    MinPlayers = excluded.MinPlayers,
                    MaxPlayers = excluded.MaxPlayers,
                    Mode = excluded.Mode,
                    ConfirmationDelayMinutes = excluded.ConfirmationDelayMinutes,
                    PingParticipants = excluded.PingParticipants,
                    SeasonStartDate = excluded.SeasonStartDate,
                    TimeZone = excluded.TimeZone,
                    StagePrefix = excluded.StagePrefix,
                    SeasonDurationHours = excluded.SeasonDurationHours
                """,
                (
                    guild.id,
                    channel_id,
                    title,
                    title,
                    description,
                    min_players,
                    max_players,
                    mode,
                    confirmation_delay_minutes,
                    int(ping_participants),
                    season_start_date,
                    timezone,
                    stage_prefix,
                    season_duration_hours,
                ),
            )
        except Exception:
            _logger.exception(
                "%s Failed to configure queue in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def get(
        self, *, guild: discord.Guild, channel_id: int
    ) -> QueueConfiguration | None:
        try:
            row = await self.database.fetch_one(
                f"SELECT * FROM {self.table_name} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            )
            if row is None:
                return None
            mode = row["Mode"]
            if mode not in ("continuous", "stages", "seasons"):
                _logger.error(
                    "%s Queue in channel %s has an invalid mode %r.",
                    self.log_prefix(guild),
                    channel_id,
                    mode,
                )
                return None
            return QueueConfiguration(
                guild_id=row["Guild"],
                channel_id=row["Channel"],
                title=row["Title"] or row["Name"],
                description=row["Description"],
                min_players=row["MinPlayers"],
                max_players=row["MaxPlayers"],
                mode=mode,
                confirmation_delay_minutes=row["ConfirmationDelayMinutes"],
                ping_participants=bool(row["PingParticipants"]),
                message_id=row["Message"],
                season_start_date=row["SeasonStartDate"],
                stage_prefix=row["StagePrefix"],
                season_duration_hours=row["SeasonDurationHours"],
            )
        except Exception:
            _logger.exception(
                "%s Failed to get queue configuration for channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def get_all(self, *, guild: discord.Guild) -> tuple[QueueConfiguration, ...]:
        rows = await self.database.fetch_all(
            f"SELECT Channel FROM {self.table_name} WHERE Guild = ? ORDER BY Channel",
            (guild.id,),
        )
        configurations: list[QueueConfiguration] = []
        for row in rows:
            configuration = await self.get(guild=guild, channel_id=row["Channel"])
            if configuration is not None:
                configurations.append(configuration)
        return tuple(configurations)

    async def set_message(
        self, *, guild: discord.Guild, channel_id: int, message_id: int
    ) -> bool:
        return await self.database.execute(
            f"UPDATE {self.table_name} SET Message = ? WHERE Guild = ? AND Channel = ?",
            (message_id, guild.id, channel_id),
        )

    async def remove(self, *, guild: discord.Guild, channel_id: int) -> bool:
        deletes = (
            (
                f"DELETE FROM {self.goals_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.task_completions_table} "
                "WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.season_tasks_table} "
                "WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.seasons_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.season_members_table} "
                "WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.stages_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.members_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"""
                DELETE FROM {self.participants_table} WHERE Run IN (
                    SELECT Id FROM {self.runs_table}
                    WHERE Guild = ? AND Channel = ?
                )
                """,
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.runs_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"""
                DELETE FROM {self.vote_members_table} WHERE Vote IN (
                    SELECT Id FROM {self.votes_table}
                    WHERE Guild = ? AND Channel = ?
                )
                """,
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.votes_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.table_name} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
        )
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                for query, params in deletes:
                    await connection.execute(query, params)
                await connection.commit()
                return True
        except Exception:
            _logger.exception(
                "%s Failed to completely remove queue in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def clear_mode_data(self, *, guild: discord.Guild, channel_id: int) -> bool:
        deletes = (
            (
                f"DELETE FROM {self.task_completions_table} "
                "WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.season_tasks_table} "
                "WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.goals_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.season_members_table} "
                "WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.seasons_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.stages_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.members_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"""
                DELETE FROM {self.participants_table} WHERE Run IN (
                    SELECT Id FROM {self.runs_table}
                    WHERE Guild = ? AND Channel = ?
                )
                """,
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.runs_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
            (
                f"""
                DELETE FROM {self.vote_members_table} WHERE Vote IN (
                    SELECT Id FROM {self.votes_table}
                    WHERE Guild = ? AND Channel = ?
                )
                """,
                (guild.id, channel_id),
            ),
            (
                f"DELETE FROM {self.votes_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ),
        )
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                for statement, parameters in deletes:
                    await connection.execute(statement, parameters)
                await connection.commit()
                return True
        except Exception:
            _logger.exception(
                "%s Failed to clear mode data for queue in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def get_members(
        self, *, guild: discord.Guild, channel_id: int, stage_index: int = 0
    ) -> tuple[int, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Member FROM {self.members_table}
            WHERE Guild = ? AND Channel = ? AND StageIndex = ?
            ORDER BY JoinedAt, Member
            """,
            (guild.id, channel_id, stage_index),
        )
        return tuple(row["Member"] for row in rows)

    async def get_waiting_members(
        self, *, guild: discord.Guild, channel_id: int
    ) -> tuple[tuple[int, int], ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Member, StageIndex FROM {self.members_table}
            WHERE Guild = ? AND Channel = ? ORDER BY JoinedAt, Member
            """,
            (guild.id, channel_id),
        )
        return tuple((row["Member"], row["StageIndex"]) for row in rows)

    async def join(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        member_id: int,
        joined_at: float,
        stage_index: int = 0,
    ) -> bool:
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.members_table}
                    (Guild, Channel, Member, JoinedAt, StageIndex)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild.id, channel_id, member_id, joined_at, stage_index),
            )
        except Exception:
            _logger.exception(
                "%s Failed to add member %s to queue %s.",
                self.log_prefix(guild),
                member_id,
                channel_id,
            )
            return False

    async def leave(
        self, *, guild: discord.Guild, channel_id: int, member_id: int
    ) -> bool:
        return await self.database.execute(
            f"DELETE FROM {self.members_table} "
            "WHERE Guild = ? AND Channel = ? AND Member = ?",
            (guild.id, channel_id, member_id),
        )

    async def replace_stages(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        stages: tuple[str, ...],
    ) -> bool:
        if not await self.database.execute(
            f"DELETE FROM {self.stages_table} WHERE Guild = ? AND Channel = ?",
            (guild.id, channel_id),
        ):
            return False
        return await self.database.execute_many(
            f"""
            INSERT INTO {self.stages_table} (Guild, Channel, StageIndex, Name)
            VALUES (?, ?, ?, ?)
            """,
            tuple(
                (guild.id, channel_id, index, name) for index, name in enumerate(stages)
            ),
        )

    async def get_stages(
        self, *, guild: discord.Guild, channel_id: int
    ) -> tuple[QueueStage, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT StageIndex, Name FROM {self.stages_table}
            WHERE Guild = ? AND Channel = ? ORDER BY StageIndex
            """,
            (guild.id, channel_id),
        )
        return tuple(QueueStage(row["StageIndex"], row["Name"]) for row in rows)

    async def replace_seasons(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        seasons: tuple[str, ...],
        goal_limit: int,
        goal_description: str,
        start_date: str | None = None,
        timezone: str = "Europe/Berlin",
        duration_hours: int = 24,
    ) -> bool:
        if seasons and (
            len(seasons) > 6
            or duration_hours not in {12, 24, 36, 48, 60, 72}
            or not 1 <= goal_limit <= 10000
            or not goal_description.strip()
            or len(set(seasons)) != len(seasons)
            or any(
                len(hour) != 5
                or hour[2:] != ":00"
                or not hour[:2].isdigit()
                or not 0 <= int(hour[:2]) <= 23
                for hour in seasons
            )
        ):
            return False
        season_indexes = tuple(int(hour[:2]) for hour in seasons)
        scheduled_starts: dict[int, float] = {}
        for hour in seasons:
            timestamp = (
                season_start_timestamp(start_date, hour, timezone)
                if start_date is not None
                else 0.0
            )
            if timestamp is None:
                return False
            scheduled_starts[int(hour[:2])] = timestamp
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                if season_indexes:
                    placeholders = ", ".join("?" for _ in season_indexes)
                    retained_parameters = (guild.id, channel_id, *season_indexes)
                    await connection.execute(
                        f"""
                        DELETE FROM {self.goals_table}
                        WHERE Guild = ? AND Channel = ?
                          AND SeasonIndex NOT IN ({placeholders})
                        """,
                        retained_parameters,
                    )
                    await connection.execute(
                        f"""
                        DELETE FROM {self.seasons_table}
                        WHERE Guild = ? AND Channel = ?
                          AND SeasonIndex NOT IN ({placeholders})
                        """,
                        retained_parameters,
                    )
                else:
                    await connection.execute(
                        f"DELETE FROM {self.goals_table} WHERE Guild = ? AND Channel = ?",
                        (guild.id, channel_id),
                    )
                    await connection.execute(
                        f"DELETE FROM {self.seasons_table} WHERE Guild = ? AND Channel = ?",
                        (guild.id, channel_id),
                    )
                await connection.executemany(
                    f"""
                    INSERT INTO {self.seasons_table}
                        (Guild, Channel, SeasonIndex, Name, GoalLimit,
                         GoalDescription, StartsAt, DurationHours)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (Guild, Channel, SeasonIndex) DO UPDATE SET
                        Name = excluded.Name,
                        GoalLimit = excluded.GoalLimit,
                        GoalDescription = excluded.GoalDescription,
                        Status = CASE
                            WHEN StartsAt != excluded.StartsAt THEN 'pending'
                            ELSE Status
                        END,
                        StartNotified = CASE
                            WHEN StartsAt != excluded.StartsAt THEN 0
                            ELSE StartNotified
                        END,
                        StartsAt = excluded.StartsAt,
                        DurationHours = excluded.DurationHours
                    """,
                    tuple(
                        (
                            guild.id,
                            channel_id,
                            int(hour[:2]),
                            hour,
                            goal_limit,
                            goal_description,
                            scheduled_starts[int(hour[:2])],
                            duration_hours,
                        )
                        for hour in seasons
                    ),
                )
                await connection.commit()
                return True
        except Exception:
            _logger.exception(
                "%s Failed to replace season setup in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def replace_season_tasks(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        tasks: tuple[tuple[str, int], ...],
    ) -> bool:
        if len(tasks) > 25 or any(
            not label.strip()
            or len(label.strip()) > 100
            or "\n" in label
            or "\r" in label
            or not 1 <= limit <= 10000
            for label, limit in tasks
        ):
            return False
        if not tasks:
            return await self.database.execute(
                f"DELETE FROM {self.season_tasks_table} "
                "WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            )
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    f"DELETE FROM {self.season_tasks_table} "
                    "WHERE Guild = ? AND Channel = ?",
                    (guild.id, channel_id),
                )
                await connection.executemany(
                    f"""
                    INSERT INTO {self.season_tasks_table}
                        (Guild, Channel, TaskIndex, Label, CompletionLimit)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    tuple(
                        (
                            guild.id,
                            channel_id,
                            index,
                            label.strip(),
                            limit,
                        )
                        for index, (label, limit) in enumerate(tasks, 1)
                    ),
                )
                await connection.commit()
                return True
        except Exception:
            _logger.exception(
                "%s Failed to replace season tasks in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def get_season_tasks(
        self, *, guild: discord.Guild, channel_id: int
    ) -> tuple[SeasonTask, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT task.TaskIndex, task.Label, task.CompletionLimit,
               COUNT(completion.Member) AS Completed
            FROM {self.season_tasks_table} task
            LEFT JOIN {self.task_completions_table} completion
              ON completion.Guild = task.Guild
             AND completion.Channel = task.Channel
             AND completion.TaskIndex = task.TaskIndex
            WHERE task.Guild = ? AND task.Channel = ?
            GROUP BY task.TaskIndex, task.Label, task.CompletionLimit
            ORDER BY task.TaskIndex
            """,
            (guild.id, channel_id),
        )
        return tuple(
            SeasonTask(
                row["TaskIndex"],
                row["Label"],
                row["CompletionLimit"],
                row["Completed"],
            )
            for row in rows
        )

    async def get_seasons(
        self, *, guild: discord.Guild, channel_id: int
    ) -> tuple[QueueSeason, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT * FROM {self.seasons_table}
            WHERE Guild = ? AND Channel = ? ORDER BY SeasonIndex
            """,
            (guild.id, channel_id),
        )
        return tuple(self._season_from_row(row) for row in rows)

    async def set_season_thread(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        season_index: int,
        thread_id: int,
        message_id: int,
    ) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.seasons_table}
            SET Thread = ?, Message = ?
            WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
            """,
            (thread_id, message_id, guild.id, channel_id, season_index),
        )

    async def get_season_members(
        self, *, guild: discord.Guild, channel_id: int, season_index: int
    ) -> tuple[int, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Member FROM {self.season_members_table}
            WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
            ORDER BY JoinedAt, Member
            """,
            (guild.id, channel_id, season_index),
        )
        return tuple(row["Member"] for row in rows)

    async def has_season_members(
        self, *, guild: discord.Guild, channel_id: int
    ) -> bool:
        row = await self.database.fetch_one(
            f"SELECT 1 FROM {self.season_members_table} "
            "WHERE Guild = ? AND Channel = ? LIMIT 1",
            (guild.id, channel_id),
        )
        return row is not None

    async def join_season(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        season_index: int,
        member_id: int,
        joined_at: float,
    ) -> bool:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                season = await connection.execute_fetchall(
                    f"""
                    SELECT Status FROM {self.seasons_table}
                    WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
                    """,
                    (guild.id, channel_id, season_index),
                )
                if not season or season[0][0] == "completed":
                    await connection.rollback()
                    return False
                await connection.execute(
                    f"""
                    INSERT INTO {self.season_members_table}
                        (Guild, Channel, SeasonIndex, Member, JoinedAt)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (guild.id, channel_id, season_index, member_id, joined_at),
                )
                await connection.commit()
                return True
        except Exception:
            _logger.exception(
                "%s Failed to register member %s for season %s in channel %s.",
                self.log_prefix(guild),
                member_id,
                season_index,
                channel_id,
            )
            return False

    async def leave_season(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        season_index: int,
        member_id: int,
    ) -> bool:
        return await self.database.execute(
            f"""
            DELETE FROM {self.season_members_table}
            WHERE Guild = ? AND Channel = ? AND SeasonIndex = ? AND Member = ?
            """,
            (guild.id, channel_id, season_index, member_id),
        )

    async def get_due_seasons(
        self, *, guild: discord.Guild, now: float
    ) -> tuple[tuple[int, int], ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Channel, SeasonIndex FROM {self.seasons_table}
            WHERE Guild = ? AND Status = 'pending' AND StartsAt <= ?
            ORDER BY StartsAt, Channel, SeasonIndex
            """,
            (guild.id, now),
        )
        return tuple((row["Channel"], row["SeasonIndex"]) for row in rows)

    async def get_expired_seasons(
        self, *, guild: discord.Guild, now: float
    ) -> tuple[tuple[int, int], ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Channel, SeasonIndex FROM {self.seasons_table}
            WHERE Guild = ? AND Status = 'active'
              AND StartsAt + DurationHours * 3600 <= ?
            ORDER BY StartsAt, Channel, SeasonIndex
            """,
            (guild.id, now),
        )
        return tuple((row["Channel"], row["SeasonIndex"]) for row in rows)

    async def expire_season(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        season_index: int,
        now: float,
    ) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.seasons_table}
            SET Status = 'completed'
            WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
              AND Status = 'active' AND StartsAt + DurationHours * 3600 <= ?
            """,
            (guild.id, channel_id, season_index, now),
        )

    async def activate_season(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        season_index: int,
        now: float,
    ) -> bool:
        try:
            async with self.database.connect() as connection:
                cursor = await connection.execute(
                    f"""
                    UPDATE {self.seasons_table}
                    SET Status = 'active'
                    WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
                      AND Status = 'pending' AND StartsAt <= ?
                    """,
                    (guild.id, channel_id, season_index, now),
                )
                await connection.commit()
                return cursor.rowcount == 1
        except Exception:
            _logger.exception(
                "%s Failed to activate season %s in channel %s.",
                self.log_prefix(guild),
                season_index,
                channel_id,
            )
            return False

    async def get_unnotified_started_seasons(
        self, *, guild: discord.Guild, now: float
    ) -> tuple[tuple[int, int], ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Channel, SeasonIndex FROM {self.seasons_table}
            WHERE Guild = ? AND Status = 'active' AND StartNotified = 0
              AND StartsAt <= ?
            ORDER BY StartsAt, Channel, SeasonIndex
            """,
            (guild.id, now),
        )
        return tuple((row["Channel"], row["SeasonIndex"]) for row in rows)

    async def mark_season_start_notified(
        self, *, guild: discord.Guild, channel_id: int, season_index: int
    ) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.seasons_table} SET StartNotified = 1
            WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
            """,
            (guild.id, channel_id, season_index),
        )

    async def reset_season_queue(
        self, *, guild: discord.Guild, channel_id: int
    ) -> bool:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    f"""
                    DELETE FROM {self.participants_table}
                    WHERE Run IN (
                        SELECT Id FROM {self.runs_table}
                        WHERE Guild = ? AND Channel = ? AND SeasonIndex IS NOT NULL
                    )
                    """,
                    (guild.id, channel_id),
                )
                await connection.execute(
                    f"""
                    DELETE FROM {self.runs_table}
                    WHERE Guild = ? AND Channel = ? AND SeasonIndex IS NOT NULL
                    """,
                    (guild.id, channel_id),
                )
                await connection.execute(
                    f"DELETE FROM {self.goals_table} WHERE Guild = ? AND Channel = ?",
                    (guild.id, channel_id),
                )
                await connection.execute(
                    f"""
                    DELETE FROM {self.task_completions_table}
                    WHERE Guild = ? AND Channel = ?
                    """,
                    (guild.id, channel_id),
                )
                await connection.execute(
                    f"DELETE FROM {self.season_members_table} "
                    "WHERE Guild = ? AND Channel = ?",
                    (guild.id, channel_id),
                )
                await connection.execute(
                    f"""
                    UPDATE {self.seasons_table}
                    SET GoalsCompleted = 0, Status = 'pending',
                        StartNotified = 0, Message = NULL
                    WHERE Guild = ? AND Channel = ?
                    """,
                    (guild.id, channel_id),
                )
                await connection.execute(
                    f"DELETE FROM {self.members_table} WHERE Guild = ? AND Channel = ?",
                    (guild.id, channel_id),
                )
                await connection.commit()
                return True
        except Exception:
            _logger.exception(
                "%s Failed to reset season queue in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def get_season(
        self, *, guild: discord.Guild, channel_id: int, season_index: int
    ) -> QueueSeason | None:
        row = await self.database.fetch_one(
            f"""
            SELECT * FROM {self.seasons_table}
            WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
            """,
            (guild.id, channel_id, season_index),
        )
        return self._season_from_row(row) if row is not None else None

    async def get_next_season(
        self, *, guild: discord.Guild, channel_id: int
    ) -> QueueSeason | None:
        row = await self.database.fetch_one(
            f"""
            SELECT * FROM {self.seasons_table}
            WHERE Guild = ? AND Channel = ? AND Status = 'pending'
            ORDER BY SeasonIndex LIMIT 1
            """,
            (guild.id, channel_id),
        )
        return self._season_from_row(row) if row is not None else None

    @staticmethod
    def _season_from_row(row: Row) -> QueueSeason:
        return QueueSeason(
            index=row["SeasonIndex"],
            name=row["Name"],
            goal_limit=row["GoalLimit"],
            goal_description=row["GoalDescription"],
            goals_completed=row["GoalsCompleted"],
            status=row["Status"],
            thread_id=row["Thread"],
            message_id=row["Message"],
            starts_at=row["StartsAt"],
            start_notified=bool(row["StartNotified"]),
            duration_hours=row["DurationHours"],
        )

    async def record_task_completion(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        season_index: int,
        task_index: int,
        member_id: int,
        text: str,
        created_at: float,
    ) -> tuple[int, bool] | None:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                season = await connection.execute_fetchall(
                    f"""
                    SELECT Status, StartsAt, DurationHours
                    FROM {self.seasons_table}
                    WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
                    """,
                    (guild.id, channel_id, season_index),
                )
                if (
                    not season
                    or season[0][0] != "active"
                    or created_at < season[0][1]
                    or created_at >= season[0][1] + season[0][2] * 3600
                ):
                    await connection.rollback()
                    return None
                is_member = await connection.execute_fetchall(
                    f"""
                    SELECT 1 FROM {self.season_members_table}
                    WHERE Guild = ? AND Channel = ? AND SeasonIndex = ? AND Member = ?
                    """,
                    (guild.id, channel_id, season_index, member_id),
                )
                task = await connection.execute_fetchall(
                    f"""
                    SELECT CompletionLimit FROM {self.season_tasks_table}
                    WHERE Guild = ? AND Channel = ? AND TaskIndex = ?
                    """,
                    (guild.id, channel_id, task_index),
                )
                prior_completion = await connection.execute_fetchall(
                    f"""
                    SELECT 1 FROM {self.task_completions_table}
                    WHERE Guild = ? AND Channel = ? AND Member = ?
                    """,
                    (guild.id, channel_id, member_id),
                )
                task_count = await connection.execute_fetchall(
                    f"""
                    SELECT COUNT(*) FROM {self.task_completions_table}
                    WHERE Guild = ? AND Channel = ? AND TaskIndex = ?
                    """,
                    (guild.id, channel_id, task_index),
                )
                if (
                    not is_member
                    or not task
                    or prior_completion
                    or task_count[0][0] >= task[0][0]
                ):
                    await connection.rollback()
                    return None
                await connection.execute(
                    f"""
                    INSERT INTO {self.task_completions_table}
                        (Guild, Channel, Member, TaskIndex, SeasonIndex, Text, CreatedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild.id,
                        channel_id,
                        member_id,
                        task_index,
                        season_index,
                        text,
                        created_at,
                    ),
                )
                next_task_count = task_count[0][0] + 1
                remaining_tasks = await connection.execute_fetchall(
                    f"""
                    SELECT 1
                    FROM {self.season_tasks_table} task
                    LEFT JOIN (
                        SELECT TaskIndex, COUNT(*) AS Completed
                        FROM {self.task_completions_table}
                        WHERE Guild = ? AND Channel = ?
                        GROUP BY TaskIndex
                    ) completion ON completion.TaskIndex = task.TaskIndex
                    WHERE task.Guild = ? AND task.Channel = ?
                      AND COALESCE(completion.Completed, 0) < task.CompletionLimit
                    LIMIT 1
                    """,
                    (guild.id, channel_id, guild.id, channel_id),
                )
                queue_complete = not remaining_tasks
                await connection.execute(
                    f"""
                    UPDATE {self.seasons_table}
                    SET GoalsCompleted = (
                        SELECT COUNT(*) FROM {self.task_completions_table}
                        WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
                    ),
                    Status = CASE WHEN ? THEN 'completed' ELSE Status END
                    WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
                    """,
                    (
                        guild.id,
                        channel_id,
                        season_index,
                        int(queue_complete),
                        guild.id,
                        channel_id,
                        season_index,
                    ),
                )
                if queue_complete:
                    await connection.execute(
                        f"""
                        UPDATE {self.seasons_table}
                        SET Status = 'completed'
                        WHERE Guild = ? AND Channel = ? AND Status != 'completed'
                        """,
                        (guild.id, channel_id),
                    )
                await connection.commit()
                return next_task_count, queue_complete
        except Exception:
            _logger.exception(
                "%s Failed to record task %s completion for member %s in channel %s.",
                self.log_prefix(guild),
                task_index,
                member_id,
                channel_id,
            )
            return None

    async def get_task_completions(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        season_index: int,
    ) -> tuple[GoalEntry, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Member, Text, CreatedAt, TaskIndex
            FROM {self.task_completions_table}
            WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
            ORDER BY CreatedAt, Member
            """,
            (guild.id, channel_id, season_index),
        )
        return tuple(
            GoalEntry(
                row["Member"],
                row["Text"],
                row["CreatedAt"],
                row["TaskIndex"],
            )
            for row in rows
        )

    async def get_member_task_completion(
        self, *, guild: discord.Guild, channel_id: int, member_id: int
    ) -> GoalEntry | None:
        row = await self.database.fetch_one(
            f"""
            SELECT Member, Text, CreatedAt, TaskIndex
            FROM {self.task_completions_table}
            WHERE Guild = ? AND Channel = ? AND Member = ?
            """,
            (guild.id, channel_id, member_id),
        )
        if row is None:
            return None
        return GoalEntry(row["Member"], row["Text"], row["CreatedAt"], row["TaskIndex"])

    async def record_goal(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        season_index: int,
        member_id: int,
        text: str,
        created_at: float,
    ) -> tuple[int, bool] | None:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                row = await connection.execute_fetchall(
                    f"""
                    SELECT GoalsCompleted, GoalLimit, Status, StartsAt
                    FROM {self.seasons_table}
                    WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
                    """,
                    (guild.id, channel_id, season_index),
                )
                if not row or row[0][2] != "active" or created_at < row[0][3]:
                    return None
                next_count = row[0][0] + 1
                completed = next_count >= row[0][1]
                await connection.execute(
                    f"""
                    INSERT INTO {self.goals_table}
                        (Guild, Channel, SeasonIndex, Member, Text, CreatedAt)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild.id,
                        channel_id,
                        season_index,
                        member_id,
                        text,
                        created_at,
                    ),
                )
                await connection.execute(
                    f"""
                    UPDATE {self.seasons_table}
                    SET GoalsCompleted = ?, Status = ?
                    WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
                    """,
                    (
                        next_count,
                        "completed" if completed else "active",
                        guild.id,
                        channel_id,
                        season_index,
                    ),
                )
                await connection.commit()
                return next_count, completed
        except Exception:
            _logger.exception(
                "%s Failed to record a goal for season %s in channel %s.",
                self.log_prefix(guild),
                season_index,
                channel_id,
            )
            return None

    async def get_goals(
        self, *, guild: discord.Guild, channel_id: int, season_index: int
    ) -> tuple[GoalEntry, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Member, Text, CreatedAt FROM {self.goals_table}
            WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
            ORDER BY Id
            """,
            (guild.id, channel_id, season_index),
        )
        return tuple(
            GoalEntry(row["Member"], row["Text"], row["CreatedAt"]) for row in rows
        )

    async def create_run(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        stage_index: int | None,
        season_index: int | None,
        thread_id: int,
        message_id: int,
        members: tuple[int, ...],
        started_at: float,
        confirmation_available_at: float,
    ) -> int | None:
        try:
            async with self.database.connect() as connection:
                cursor = await connection.execute(
                    f"""
                    INSERT INTO {self.runs_table}
                        (Guild, Channel, StageIndex, SeasonIndex, Thread, Message,
                         StartedAt, ConfirmationAvailableAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild.id,
                        channel_id,
                        stage_index,
                        season_index,
                        thread_id,
                        message_id,
                        started_at,
                        confirmation_available_at,
                    ),
                )
                run_id = cursor.lastrowid
                if run_id is None:
                    raise RuntimeError("Database did not return a queue run ID.")
                await connection.executemany(
                    f"INSERT INTO {self.participants_table} (Run, Member) VALUES (?, ?)",
                    ((run_id, member_id) for member_id in members),
                )
                if season_index is not None:
                    cursor = await connection.execute(
                        f"""
                        UPDATE {self.seasons_table}
                        SET Status = 'active', Thread = ?, Message = ?
                        WHERE Guild = ? AND Channel = ? AND SeasonIndex = ?
                          AND Status IN ('pending', 'active') AND StartsAt <= ?
                        """,
                        (
                            thread_id,
                            message_id,
                            guild.id,
                            channel_id,
                            season_index,
                            started_at,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError(
                            f"Season {season_index} is not pending for this queue."
                        )
                await connection.executemany(
                    f"""
                    DELETE FROM {self.members_table}
                    WHERE Guild = ? AND Channel = ? AND Member = ?
                    """,
                    ((guild.id, channel_id, member_id) for member_id in members),
                )
                await connection.commit()
                return run_id
        except Exception:
            _logger.exception(
                "%s Failed to persist queue run in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    @staticmethod
    def _run_from_row(row: Row) -> QueueRun:
        return QueueRun(
            id=row["Id"],
            guild_id=row["Guild"],
            channel_id=row["Channel"],
            stage_index=row["StageIndex"],
            season_index=row["SeasonIndex"],
            thread_id=row["Thread"],
            message_id=row["Message"],
            started_at=row["StartedAt"],
            confirmation_available_at=row["ConfirmationAvailableAt"],
            status=row["Status"],
        )

    async def get_run(self, run_id: int) -> QueueRun | None:
        row = await self.database.fetch_one(
            f"SELECT * FROM {self.runs_table} WHERE Id = ?", (run_id,)
        )
        return self._run_from_row(row) if row is not None else None

    async def get_active_runs(self, *, guild: discord.Guild) -> tuple[QueueRun, ...]:
        rows = await self.database.fetch_all(
            f"SELECT * FROM {self.runs_table} WHERE Guild = ? AND Status = 'active'",
            (guild.id,),
        )
        return tuple(self._run_from_row(row) for row in rows)

    async def get_runs(
        self, *, guild: discord.Guild, channel_id: int
    ) -> tuple[QueueRun, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT * FROM {self.runs_table}
            WHERE Guild = ? AND Channel = ?
            ORDER BY Id
            """,
            (guild.id, channel_id),
        )
        return tuple(self._run_from_row(row) for row in rows)

    async def get_run_participants(self, run_id: int) -> tuple[RunParticipant, ...]:
        rows = await self.database.fetch_all(
            f"SELECT * FROM {self.participants_table} WHERE Run = ? ORDER BY Member",
            (run_id,),
        )
        return tuple(RunParticipant(row["Member"], row["ConfirmedAt"]) for row in rows)

    async def confirm(
        self, *, run_id: int, member_id: int, confirmed_at: float
    ) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.participants_table}
            SET ConfirmedAt = ?
            WHERE Run = ? AND Member = ? AND ConfirmedAt IS NULL
            """,
            (confirmed_at, run_id, member_id),
        )

    async def complete_run(self, run_id: int) -> bool:
        return await self.database.execute(
            f"UPDATE {self.runs_table} SET Status = 'completed' "
            "WHERE Id = ? AND Status = 'active'",
            (run_id,),
        )

    async def completed_count(self, *, guild: discord.Guild, channel_id: int) -> int:
        row = await self.database.fetch_one(
            f"""
            SELECT COUNT(*) FROM {self.runs_table}
            WHERE Guild = ? AND Channel = ? AND Status = 'completed'
            """,
            (guild.id, channel_id),
        )
        return int(row[0]) if row is not None else 0

    async def create_early_vote(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        stage_index: int,
        message_id: int,
        members: tuple[int, ...],
    ) -> int | None:
        try:
            async with self.database.connect() as connection:
                cursor = await connection.execute(
                    f"""
                    INSERT INTO {self.votes_table}
                        (Guild, Channel, StageIndex, Message)
                    VALUES (?, ?, ?, ?)
                    """,
                    (guild.id, channel_id, stage_index, message_id),
                )
                vote_id = cursor.lastrowid
                if vote_id is None:
                    raise RuntimeError("Database did not return an early vote ID.")
                await connection.executemany(
                    f"INSERT INTO {self.vote_members_table} (Vote, Member) VALUES (?, ?)",
                    ((vote_id, member_id) for member_id in members),
                )
                await connection.commit()
                return vote_id
        except Exception:
            _logger.exception(
                "%s Failed to create early-start vote in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def get_open_votes(
        self, *, guild: discord.Guild, channel_id: int | None = None
    ) -> tuple[tuple[int, int, int, int], ...]:
        query = (
            f"SELECT Id, Channel, StageIndex, Message FROM {self.votes_table} "
            "WHERE Guild = ? AND Status = 'open'"
        )
        params: tuple[int, ...] = (guild.id,)
        if channel_id is not None:
            query += " AND Channel = ?"
            params = (guild.id, channel_id)
        rows = await self.database.fetch_all(query, params)
        return tuple(
            (row["Id"], row["Channel"], row["StageIndex"], row["Message"])
            for row in rows
        )

    async def get_vote_members(
        self, vote_id: int
    ) -> tuple[tuple[int, int | None], ...]:
        rows = await self.database.fetch_all(
            f"SELECT Member, VoteValue FROM {self.vote_members_table} WHERE Vote = ?",
            (vote_id,),
        )
        return tuple((row["Member"], row["VoteValue"]) for row in rows)

    async def cast_vote(self, *, vote_id: int, member_id: int, vote_value: int) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.vote_members_table}
            SET VoteValue = ?
            WHERE Vote = ? AND Member = ? AND VoteValue IS NULL
            """,
            (vote_value, vote_id, member_id),
        )

    async def close_vote(self, *, vote_id: int, status: str) -> bool:
        return await self.database.execute(
            f"UPDATE {self.votes_table} SET Status = ? WHERE Id = ? AND Status = 'open'",
            (status, vote_id),
        )
