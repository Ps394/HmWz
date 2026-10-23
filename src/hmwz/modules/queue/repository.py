from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QueueConfiguration:
    guild_id: int
    channel_id: int
    name: str
    min_players: int
    max_players: int
    confirmation_delay_minutes: int
    reminder_interval_minutes: int
    message_id: int | None


@dataclass(frozen=True, slots=True)
class QueueRun:
    id: int
    guild_id: int
    channel_id: int
    thread_id: int
    message_id: int
    started_at: float
    confirmation_available_at: float
    status: str


@dataclass(frozen=True, slots=True)
class RunParticipant:
    member_id: int
    confirmed_at: float | None
    last_reminded_at: float | None


class QueueRepository(sqlite_db.Base):
    """Persist queue configuration, waiting members, runs, and confirmations."""

    table_name = "Queue_Settings"
    members_table = "Queue_Members"
    runs_table = "Queue_Runs"
    participants_table = "Queue_Run_Members"

    @property
    def tables(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Name TEXT NOT NULL,
                MinPlayers INTEGER NOT NULL DEFAULT 0,
                MaxPlayers INTEGER NOT NULL,
                ConfirmationDelayMinutes INTEGER NOT NULL,
                ReminderIntervalMinutes INTEGER NOT NULL,
                Message INTEGER,
                PRIMARY KEY (Guild, Channel)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.members_table} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                JoinedAt REAL NOT NULL,
                PRIMARY KEY (Guild, Channel, Member)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.runs_table} (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
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
                LastRemindedAt REAL,
                PRIMARY KEY (Run, Member)
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
        return True

    async def configure(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        name: str,
        min_players: int,
        max_players: int,
        confirmation_delay_minutes: int,
        reminder_interval_minutes: int,
    ) -> bool:
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.table_name}
                    (Guild, Channel, Name, MinPlayers, MaxPlayers,
                     ConfirmationDelayMinutes, ReminderIntervalMinutes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (Guild, Channel) DO UPDATE SET
                    Name = excluded.Name,
                    MinPlayers = excluded.MinPlayers,
                    MaxPlayers = excluded.MaxPlayers,
                    ConfirmationDelayMinutes = excluded.ConfirmationDelayMinutes,
                    ReminderIntervalMinutes = excluded.ReminderIntervalMinutes
                """,
                (
                    guild.id,
                    channel_id,
                    name,
                    min_players,
                    max_players,
                    confirmation_delay_minutes,
                    reminder_interval_minutes,
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
            return QueueConfiguration(
                guild_id=row["Guild"],
                channel_id=row["Channel"],
                name=row["Name"],
                min_players=row["MinPlayers"],
                max_players=row["MaxPlayers"],
                confirmation_delay_minutes=row["ConfirmationDelayMinutes"],
                reminder_interval_minutes=row["ReminderIntervalMinutes"],
                message_id=row["Message"],
            )
        except Exception:
            _logger.exception(
                "%s Failed to get queue configuration for channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def get_all(self, *, guild: discord.Guild) -> tuple[QueueConfiguration, ...]:
        try:
            rows = await self.database.fetch_all(
                f"SELECT * FROM {self.table_name} WHERE Guild = ? ORDER BY Channel",
                (guild.id,),
            )
            return tuple(
                QueueConfiguration(
                    guild_id=row["Guild"],
                    channel_id=row["Channel"],
                    name=row["Name"],
                    min_players=row["MinPlayers"],
                    max_players=row["MaxPlayers"],
                    confirmation_delay_minutes=row["ConfirmationDelayMinutes"],
                    reminder_interval_minutes=row["ReminderIntervalMinutes"],
                    message_id=row["Message"],
                )
                for row in rows
            )
        except Exception:
            _logger.exception("%s Failed to list queues.", self.log_prefix(guild))
            return ()

    async def set_message(
        self, *, guild: discord.Guild, channel_id: int, message_id: int
    ) -> bool:
        return await self.database.execute(
            f"UPDATE {self.table_name} SET Message = ? WHERE Guild = ? AND Channel = ?",
            (message_id, guild.id, channel_id),
        )

    async def remove(self, *, guild: discord.Guild, channel_id: int) -> bool:
        try:
            if not await self.database.execute(
                f"DELETE FROM {self.members_table} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ):
                return False
            return await self.database.execute(
                f"DELETE FROM {self.table_name} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to remove queue in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def get_members(
        self, *, guild: discord.Guild, channel_id: int
    ) -> tuple[int, ...]:
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT Member FROM {self.members_table}
                WHERE Guild = ? AND Channel = ? ORDER BY JoinedAt, Member
                """,
                (guild.id, channel_id),
            )
            return tuple(row["Member"] for row in rows)
        except Exception:
            _logger.exception(
                "%s Failed to list queue members in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return ()

    async def join(
        self, *, guild: discord.Guild, channel_id: int, member_id: int, joined_at: float
    ) -> bool:
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.members_table} (Guild, Channel, Member, JoinedAt)
                VALUES (?, ?, ?, ?)
                """,
                (guild.id, channel_id, member_id, joined_at),
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
            f"""
            DELETE FROM {self.members_table}
            WHERE Guild = ? AND Channel = ? AND Member = ?
            """,
            (guild.id, channel_id, member_id),
        )

    async def create_run(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
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
                        (Guild, Channel, Thread, Message, StartedAt,
                         ConfirmationAvailableAt)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild.id,
                        channel_id,
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

    async def get_run(self, run_id: int) -> QueueRun | None:
        row = await self.database.fetch_one(
            f"SELECT * FROM {self.runs_table} WHERE Id = ?", (run_id,)
        )
        if row is None:
            return None
        return QueueRun(
            id=row["Id"],
            guild_id=row["Guild"],
            channel_id=row["Channel"],
            thread_id=row["Thread"],
            message_id=row["Message"],
            started_at=row["StartedAt"],
            confirmation_available_at=row["ConfirmationAvailableAt"],
            status=row["Status"],
        )

    async def get_active_runs(self, *, guild: discord.Guild) -> tuple[QueueRun, ...]:
        rows = await self.database.fetch_all(
            f"SELECT * FROM {self.runs_table} WHERE Guild = ? AND Status = 'active'",
            (guild.id,),
        )
        return tuple(
            QueueRun(
                id=row["Id"],
                guild_id=row["Guild"],
                channel_id=row["Channel"],
                thread_id=row["Thread"],
                message_id=row["Message"],
                started_at=row["StartedAt"],
                confirmation_available_at=row["ConfirmationAvailableAt"],
                status=row["Status"],
            )
            for row in rows
        )

    async def get_run_participants(self, run_id: int) -> tuple[RunParticipant, ...]:
        rows = await self.database.fetch_all(
            f"SELECT * FROM {self.participants_table} WHERE Run = ? ORDER BY Member",
            (run_id,),
        )
        return tuple(
            RunParticipant(
                member_id=row["Member"],
                confirmed_at=row["ConfirmedAt"],
                last_reminded_at=row["LastRemindedAt"],
            )
            for row in rows
        )

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

    async def mark_reminded(
        self, *, run_id: int, member_id: int, reminded_at: float
    ) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.participants_table}
            SET LastRemindedAt = ?
            WHERE Run = ? AND Member = ? AND ConfirmedAt IS NULL
            """,
            (reminded_at, run_id, member_id),
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
