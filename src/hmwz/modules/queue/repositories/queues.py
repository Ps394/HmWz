from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from aiosqlite import Connection, Row

from hmwz import sqlite_db

from ..models import (
    BaseDestruction,
    Eruption,
    QueueCleanupItem,
    QueueCleanupJob,
    PhaseParticipant,
    QueueConfiguration,
    QueuePhase,
    QueueReminder,
)

_logger = logging.getLogger(__name__)


class QueueRepository(sqlite_db.Base):
    """Persist QS eruption schedules, phase signups, and destruction records."""

    table_name = "Queue_QS_Phase_Settings"
    eruptions_table = "Queue_Eruptions"
    phases_table = "Queue_Phases"
    participants_table = "Queue_Eruption_Members"
    phase_members_table = "Queue_Phase_Members"
    destructions_table = "Queue_Base_Destructions"

    @property
    def tables(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Title TEXT NOT NULL DEFAULT '',
                Description TEXT NOT NULL DEFAULT '',
                RoleId INTEGER NOT NULL,
                Message INTEGER,
                DestructionMessage INTEGER,
                DestructionPrompt TEXT NOT NULL,
                TimeZone TEXT NOT NULL DEFAULT 'Europe/Berlin',
                NextStartAt REAL,
                PhaseHours TEXT NOT NULL DEFAULT '[]',
                RemoveRoleOnReset INTEGER NOT NULL DEFAULT 0,
                EruptionStartReminderEnabled INTEGER NOT NULL DEFAULT 0,
                EruptionStartReminderMinutes INTEGER NOT NULL DEFAULT 60,
                EruptionEndReminderEnabled INTEGER NOT NULL DEFAULT 0,
                EruptionEndReminderMinutes INTEGER NOT NULL DEFAULT 60,
                PhaseStartReminderEnabled INTEGER NOT NULL DEFAULT 0,
                PhaseStartReminderMinutes INTEGER NOT NULL DEFAULT 15,
                PRIMARY KEY (Guild, Channel)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.eruptions_table} (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                StartsAt REAL NOT NULL,
                EndsAt REAL NOT NULL,
                TimeZone TEXT NOT NULL,
                CreatedAt REAL NOT NULL,
                CleanupJob INTEGER UNIQUE
            )
            """,
            f"""
            CREATE INDEX IF NOT EXISTS IX_Queue_Eruptions_Guild_Channel_End
            ON {self.eruptions_table} (Guild, Channel, EndsAt)
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.phases_table} (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Eruption INTEGER NOT NULL,
                PhaseIndex INTEGER NOT NULL,
                StartsAt REAL NOT NULL,
                EndsAt REAL NOT NULL,
                Thread INTEGER,
                Message INTEGER,
                UNIQUE (Eruption, PhaseIndex),
                FOREIGN KEY (Eruption) REFERENCES {self.eruptions_table}(Id)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.participants_table} (
                Eruption INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                JoinedAt REAL NOT NULL,
                RoleManaged INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (Eruption, Member),
                FOREIGN KEY (Eruption) REFERENCES {self.eruptions_table}(Id)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.phase_members_table} (
                Eruption INTEGER NOT NULL,
                Phase INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                JoinedAt REAL NOT NULL,
                PRIMARY KEY (Phase, Member),
                FOREIGN KEY (Eruption) REFERENCES {self.eruptions_table}(Id),
                FOREIGN KEY (Phase) REFERENCES {self.phases_table}(Id)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE INDEX IF NOT EXISTS IX_Queue_Phase_Members_Eruption_Member
            ON {self.phase_members_table} (Eruption, Member)
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.destructions_table} (
                Eruption INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                Phase INTEGER NOT NULL,
                ConfirmedAt REAL NOT NULL,
                Details TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (Eruption, Member),
                FOREIGN KEY (Eruption) REFERENCES {self.eruptions_table}(Id),
                FOREIGN KEY (Phase) REFERENCES {self.phases_table}(Id)
            ) WITHOUT ROWID
            """,
            """
            CREATE TABLE IF NOT EXISTS Queue_Reminders (
                Eruption INTEGER NOT NULL,
                Phase INTEGER NOT NULL DEFAULT 0,
                Kind TEXT NOT NULL,
                DueAt REAL NOT NULL,
                EventAt REAL NOT NULL,
                Status TEXT NOT NULL DEFAULT 'pending',
                Attempts INTEGER NOT NULL DEFAULT 0,
                LeaseUntil REAL,
                PRIMARY KEY (Eruption, Phase, Kind)
            ) WITHOUT ROWID
            """,
            """
            CREATE TABLE IF NOT EXISTS Queue_Cleanup_Jobs (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Operation TEXT NOT NULL CHECK (Operation IN ('reset', 'remove')),
                Status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (Status IN ('pending', 'partial', 'completed')),
                Payload TEXT NOT NULL,
                CreatedAt REAL NOT NULL,
                UpdatedAt REAL NOT NULL
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS UX_Queue_Cleanup_Open
            ON Queue_Cleanup_Jobs (Guild, Channel)
            WHERE Status IN ('pending', 'partial')
            """,
            """
            CREATE TABLE IF NOT EXISTS Queue_Cleanup_Items (
                JobId INTEGER NOT NULL,
                Kind TEXT NOT NULL,
                ParentId INTEGER,
                ResourceId INTEGER NOT NULL,
                Status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (Status IN ('pending', 'completed')),
                Attempts INTEGER NOT NULL DEFAULT 0,
                LastError TEXT,
                PRIMARY KEY (JobId, Kind, ResourceId),
                FOREIGN KEY (JobId) REFERENCES Queue_Cleanup_Jobs(Id)
                    ON DELETE CASCADE
            ) WITHOUT ROWID
            """,
        )

    async def ensure_schema(self) -> bool:
        for statement in self.tables:
            if not await self.database.execute(statement):
                _logger.error("Failed to create QS phase queue schema.")
                return False
        columns = (
            ("TimeZone", "TEXT NOT NULL DEFAULT 'Europe/Berlin'"),
            ("NextStartAt", "REAL"),
            ("PhaseHours", "TEXT NOT NULL DEFAULT '[]'"),
            ("RemoveRoleOnReset", "INTEGER NOT NULL DEFAULT 0"),
            ("EruptionStartReminderEnabled", "INTEGER NOT NULL DEFAULT 0"),
            ("EruptionStartReminderMinutes", "INTEGER NOT NULL DEFAULT 60"),
            ("EruptionEndReminderEnabled", "INTEGER NOT NULL DEFAULT 0"),
            ("EruptionEndReminderMinutes", "INTEGER NOT NULL DEFAULT 60"),
            ("PhaseStartReminderEnabled", "INTEGER NOT NULL DEFAULT 0"),
            ("PhaseStartReminderMinutes", "INTEGER NOT NULL DEFAULT 15"),
        )
        existing = await self.database.fetch_all(
            f'PRAGMA table_info("{self.table_name}")'
        )
        names = {row["name"] for row in existing}
        for name, declaration in columns:
            if name not in names and not await self.database.execute(
                f"ALTER TABLE {self.table_name} ADD COLUMN {name} {declaration}"
            ):
                return False
        eruption_columns = await self.database.fetch_all(
            f'PRAGMA table_info("{self.eruptions_table}")'
        )
        if "CleanupJob" not in {row["name"] for row in eruption_columns}:
            if not await self.database.execute(
                f"ALTER TABLE {self.eruptions_table} ADD COLUMN CleanupJob INTEGER"
            ):
                return False
        cleanup_columns = await self.database.fetch_all(
            'PRAGMA table_info("Queue_Cleanup_Items")'
        )
        cleanup_column_names = {row["name"] for row in cleanup_columns}
        if "ParentId" not in cleanup_column_names and not await self.database.execute(
            "ALTER TABLE Queue_Cleanup_Items ADD COLUMN ParentId INTEGER"
        ):
            return False
        if "LastError" in cleanup_column_names:
            await self.database.execute(
                "UPDATE Queue_Cleanup_Items SET LastError = NULL "
                "WHERE typeof(LastError) = 'integer'"
            )
        if not await self.database.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS UX_{self.eruptions_table}_CleanupJob
            ON {self.eruptions_table} (CleanupJob)
            """
        ):
            return False
        rows = await self.database.fetch_all(
            f'PRAGMA table_info("{self.participants_table}")'
        )
        if "RoleManaged" not in {row["name"] for row in rows}:
            if not await self.database.execute(
                f"""
                ALTER TABLE {self.participants_table}
                ADD COLUMN RoleManaged INTEGER NOT NULL DEFAULT 0
                """
            ):
                return False
        if not await self._backfill_phase_templates():
            return False
        return True

    async def _backfill_phase_templates(self) -> bool:
        rows = await self.database.fetch_all(
            f"""
            SELECT Guild, Channel FROM {self.table_name}
            WHERE PhaseHours = '[]'
            """
        )
        for config in rows:
            eruption = await self.database.fetch_one(
                f"""
                SELECT Id, TimeZone FROM {self.eruptions_table}
                WHERE Guild = ? AND Channel = ?
                ORDER BY StartsAt DESC LIMIT 1
                """,
                (config["Guild"], config["Channel"]),
            )
            if eruption is None:
                continue
            phase_rows = await self.database.fetch_all(
                f"""
                SELECT StartsAt, EndsAt FROM {self.phases_table}
                WHERE Eruption = ? ORDER BY PhaseIndex
                """,
                (eruption["Id"],),
            )
            try:
                zone = ZoneInfo(eruption["TimeZone"])
                template: list[tuple[str, int]] = []
                for phase in phase_rows:
                    start = datetime.fromtimestamp(
                        phase["StartsAt"], timezone.utc
                    ).astimezone(zone)
                    duration = int(round((phase["EndsAt"] - phase["StartsAt"]) / 3600))
                    if start.minute != 0 or duration not in (1, 2, 3):
                        template = []
                        break
                    template.append((start.strftime("%H:%M"), duration))
            except (ValueError, ZoneInfoNotFoundError, OSError):
                continue
            if len(template) >= 3 and not await self.database.execute(
                f"""
                UPDATE {self.table_name} SET PhaseHours = ?, TimeZone = ?
                WHERE Guild = ? AND Channel = ?
                """,
                (
                    json.dumps(template),
                    eruption["TimeZone"],
                    config["Guild"],
                    config["Channel"],
                ),
            ):
                return False
        return True

    async def get(
        self, *, guild: discord.Guild, channel_id: int
    ) -> QueueConfiguration | None:
        row = await self.database.fetch_one(
            f"""
            SELECT * FROM {self.table_name}
            WHERE Guild = ? AND Channel = ?
            """,
            (guild.id, channel_id),
        )
        return self._configuration_from_row(row) if row is not None else None

    async def get_all(self, *, guild: discord.Guild) -> tuple[QueueConfiguration, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT * FROM {self.table_name}
            WHERE Guild = ?
            """,
            (guild.id,),
        )
        return tuple(self._configuration_from_row(row) for row in rows)

    @staticmethod
    def _configuration_from_row(row: Row) -> QueueConfiguration:
        return QueueConfiguration(
            guild_id=row["Guild"],
            channel_id=row["Channel"],
            title=row["Title"],
            description=row["Description"],
            role_id=row["RoleId"] or 0,
            modal_prompt=row["DestructionPrompt"],
            message_id=row["Message"],
            destruction_message_id=row["DestructionMessage"],
            mode="qs_phases",
            timezone=row["TimeZone"],
            next_start_at=row["NextStartAt"],
            phase_hours=tuple(
                (str(hour), int(duration))
                for hour, duration in json.loads(row["PhaseHours"])
            ),
            remove_role_on_reset=bool(row["RemoveRoleOnReset"]),
            eruption_start_reminder_enabled=bool(row["EruptionStartReminderEnabled"]),
            eruption_start_reminder_minutes=row["EruptionStartReminderMinutes"],
            eruption_end_reminder_enabled=bool(row["EruptionEndReminderEnabled"]),
            eruption_end_reminder_minutes=row["EruptionEndReminderMinutes"],
            phase_start_reminder_enabled=bool(row["PhaseStartReminderEnabled"]),
            phase_start_reminder_minutes=row["PhaseStartReminderMinutes"],
        )

    async def create_eruption(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        title: str,
        description: str,
        role_id: int,
        modal_prompt: str,
        starts_at: float,
        ends_at: float,
        timezone_name: str,
        phases: tuple[tuple[float, float], ...],
        created_at: float,
        phase_hours: tuple[tuple[str, int], ...] = (),
        remove_role_on_reset: bool = False,
        reminder_settings: tuple[bool, int, bool, int, bool, int] = (
            False,
            60,
            False,
            60,
            False,
            15,
        ),
    ) -> int | Literal["active_exists", "error"]:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                active = await connection.execute(
                    f"""
                    SELECT 1 FROM {self.eruptions_table}
                    WHERE Guild = ? AND Channel = ? AND EndsAt > ?
                    LIMIT 1
                    """,
                    (guild.id, channel_id, created_at),
                )
                if await active.fetchone() is not None:
                    await connection.rollback()
                    return "active_exists"
                await connection.execute(
                    f"""
                    INSERT INTO {self.table_name}
                        (Guild, Channel, Title, Description, RoleId, DestructionPrompt,
                         TimeZone, NextStartAt, PhaseHours, RemoveRoleOnReset,
                         EruptionStartReminderEnabled, EruptionStartReminderMinutes,
                         EruptionEndReminderEnabled, EruptionEndReminderMinutes,
                         PhaseStartReminderEnabled, PhaseStartReminderMinutes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (Guild, Channel) DO UPDATE SET
                        Title = excluded.Title,
                        Description = excluded.Description,
                        RoleId = excluded.RoleId,
                        DestructionPrompt = excluded.DestructionPrompt,
                        TimeZone = excluded.TimeZone,
                        NextStartAt = excluded.NextStartAt,
                        PhaseHours = excluded.PhaseHours,
                        RemoveRoleOnReset = excluded.RemoveRoleOnReset,
                        EruptionStartReminderEnabled = excluded.EruptionStartReminderEnabled,
                        EruptionStartReminderMinutes = excluded.EruptionStartReminderMinutes,
                        EruptionEndReminderEnabled = excluded.EruptionEndReminderEnabled,
                        EruptionEndReminderMinutes = excluded.EruptionEndReminderMinutes,
                        PhaseStartReminderEnabled = excluded.PhaseStartReminderEnabled,
                        PhaseStartReminderMinutes = excluded.PhaseStartReminderMinutes
                    """,
                    (
                        guild.id,
                        channel_id,
                        title,
                        description,
                        role_id,
                        modal_prompt,
                        timezone_name,
                        starts_at,
                        json.dumps(phase_hours),
                        int(remove_role_on_reset),
                        int(reminder_settings[0]),
                        reminder_settings[1],
                        int(reminder_settings[2]),
                        reminder_settings[3],
                        int(reminder_settings[4]),
                        reminder_settings[5],
                    ),
                )
                cursor = await connection.execute(
                    f"""
                    INSERT INTO {self.eruptions_table}
                        (Guild, Channel, StartsAt, EndsAt, TimeZone, CreatedAt)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild.id,
                        channel_id,
                        starts_at,
                        ends_at,
                        timezone_name,
                        created_at,
                    ),
                )
                eruption_id = cursor.lastrowid
                if eruption_id is None:
                    raise RuntimeError("SQLite did not return the new eruption ID.")
                await connection.executemany(
                    f"""
                    INSERT INTO {self.phases_table}
                        (Eruption, PhaseIndex, StartsAt, EndsAt)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        (eruption_id, index, phase_start, phase_end)
                        for index, (phase_start, phase_end) in enumerate(phases, 1)
                    ),
                )
                await self._insert_reminders(
                    connection,
                    eruption_id,
                    starts_at,
                    ends_at,
                    phases,
                    created_at,
                    reminder_settings,
                )
                await connection.commit()
                return eruption_id
        except Exception:
            _logger.exception(
                "%s Failed to create an eruption in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return "error"

    @staticmethod
    async def _insert_reminders(
        connection: Connection,
        eruption_id: int,
        starts_at: float,
        ends_at: float,
        phases: tuple[tuple[float, float], ...],
        now: float,
        settings: tuple[bool, int, bool, int, bool, int],
    ) -> None:
        (
            start_enabled,
            start_minutes,
            end_enabled,
            end_minutes,
            phase_enabled,
            phase_minutes,
        ) = settings
        reminders: list[tuple[int, str, float, float, str]] = []
        if start_enabled:
            reminders.append(
                (
                    0,
                    "eruption_start",
                    starts_at - start_minutes * 60,
                    starts_at,
                    "pending",
                )
            )
        if end_enabled:
            reminders.append(
                (0, "eruption_end", ends_at - end_minutes * 60, ends_at, "pending")
            )
        if phase_enabled:
            for index, (phase_start, _) in enumerate(phases, 1):
                reminders.append(
                    (
                        index,
                        "phase_start",
                        phase_start - phase_minutes * 60,
                        phase_start,
                        "pending",
                    )
                )
        for phase_index, kind, due_at, event_at, status in reminders:
            if due_at <= now or due_at >= event_at:
                status = "skipped"
            await connection.execute(
                """
                INSERT INTO Queue_Reminders
                    (Eruption, Phase, Kind, DueAt, EventAt, Status)
            VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (Eruption, Phase, Kind) DO UPDATE SET
                    DueAt = excluded.DueAt,
                    EventAt = excluded.EventAt,
                    Status = excluded.Status,
                    LeaseUntil = NULL
                WHERE Queue_Reminders.Status NOT IN ('sent', 'sending')
            """,
                (eruption_id, phase_index, kind, due_at, event_at, status),
            )

    async def get_latest_eruption(
        self, *, guild: discord.Guild, channel_id: int
    ) -> Eruption | None:
        row = await self.database.fetch_one(
            f"""
            SELECT Id, Guild, Channel, StartsAt, EndsAt, TimeZone
            FROM {self.eruptions_table}
            WHERE Guild = ? AND Channel = ?
            ORDER BY StartsAt DESC LIMIT 1
            """,
            (guild.id, channel_id),
        )
        return self._eruption_from_row(row) if row is not None else None

    async def get_eruption_by_cleanup_job(
        self, *, guild: discord.Guild, channel_id: int, cleanup_job_id: int
    ) -> Eruption | None:
        row = await self.database.fetch_one(
            f"""
            SELECT Id, Guild, Channel, StartsAt, EndsAt, TimeZone
            FROM {self.eruptions_table}
            WHERE Guild = ? AND Channel = ? AND CleanupJob = ?
            """,
            (guild.id, channel_id, cleanup_job_id),
        )
        return self._eruption_from_row(row) if row is not None else None

    async def update_settings_for_eruption(
        self,
        *,
        guild: discord.Guild,
        configuration: QueueConfiguration,
        title: str,
        description: str,
        role_id: int,
        modal_prompt: str,
        timezone_name: str,
        phase_hours: tuple[tuple[str, int], ...],
        remove_role_on_reset: bool,
        reminder_settings: tuple[bool, int, bool, int, bool, int],
        eruption_id: int,
        now: float,
    ) -> bool:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    f"""
                    SELECT StartsAt, EndsAt FROM {self.eruptions_table}
                    WHERE Id = ? AND Guild = ? AND Channel = ?
                    """,
                    (eruption_id, guild.id, configuration.channel_id),
                ) as cursor:
                    eruption = await cursor.fetchone()
                if eruption is None:
                    await connection.rollback()
                    return False
                await connection.execute(
                    f"""
                    UPDATE {self.table_name}
                    SET Title = ?, Description = ?, RoleId = ?,
                        DestructionPrompt = ?, TimeZone = ?, PhaseHours = ?,
                        RemoveRoleOnReset = ?,
                        EruptionStartReminderEnabled = ?,
                        EruptionStartReminderMinutes = ?,
                        EruptionEndReminderEnabled = ?,
                        EruptionEndReminderMinutes = ?,
                        PhaseStartReminderEnabled = ?,
                        PhaseStartReminderMinutes = ?
                    WHERE Guild = ? AND Channel = ?
                    """,
                    (
                        title,
                        description,
                        role_id,
                        modal_prompt,
                        timezone_name,
                        json.dumps(phase_hours),
                        int(remove_role_on_reset),
                        int(reminder_settings[0]),
                        reminder_settings[1],
                        int(reminder_settings[2]),
                        reminder_settings[3],
                        int(reminder_settings[4]),
                        reminder_settings[5],
                        guild.id,
                        configuration.channel_id,
                    ),
                )
                await connection.execute(
                    f"""
                    UPDATE {self.eruptions_table} SET TimeZone = ?
                    WHERE Id = ? AND Guild = ? AND Channel = ?
                    """,
                    (
                        timezone_name,
                        eruption_id,
                        guild.id,
                        configuration.channel_id,
                    ),
                )
                await connection.execute(
                    """
                    DELETE FROM Queue_Reminders
                    WHERE Eruption = ? AND Status IN ('pending', 'skipped')
                    """,
                    (eruption_id,),
                )
                async with connection.execute(
                    f"""
                    SELECT StartsAt, EndsAt FROM {self.phases_table}
                    WHERE Eruption = ? ORDER BY PhaseIndex
                    """,
                    (eruption_id,),
                ) as cursor:
                    phases = tuple(await cursor.fetchall())
                await self._insert_reminders(
                    connection,
                    eruption_id,
                    eruption["StartsAt"],
                    eruption["EndsAt"],
                    tuple((phase["StartsAt"], phase["EndsAt"]) for phase in phases),
                    now,
                    reminder_settings,
                )
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "%s Failed to update QS settings in channel %s.",
                self.log_prefix(guild),
                configuration.channel_id,
            )
            return False

    async def get_eruption_participants(self, eruption_id: int) -> tuple[int, ...]:
        rows = await self.database.fetch_all(
            f"SELECT Member FROM {self.participants_table} WHERE Eruption = ?",
            (eruption_id,),
        )
        return tuple(row["Member"] for row in rows)

    async def get_cleanup_job(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        operation: str | None = None,
        open_only: bool = True,
    ) -> QueueCleanupJob | None:
        clauses = ["Guild = ?", "Channel = ?"]
        params: list[object] = [guild.id, channel_id]
        if operation is not None:
            clauses.append("Operation = ?")
            params.append(operation)
        if open_only:
            clauses.append("Status IN ('pending', 'partial')")
        row = await self.database.fetch_one(
            "SELECT Id, Guild, Channel, Operation, Status, Payload "
            "FROM Queue_Cleanup_Jobs WHERE "
            + " AND ".join(clauses)
            + " ORDER BY Id DESC LIMIT 1",
            tuple(params),
        )
        return (
            QueueCleanupJob(
                id=row["Id"],
                guild_id=row["Guild"],
                channel_id=row["Channel"],
                operation=row["Operation"],
                status=row["Status"],
                payload=row["Payload"],
            )
            if row is not None
            else None
        )

    async def get_open_cleanup_jobs(
        self, *, guild: discord.Guild
    ) -> tuple[QueueCleanupJob, ...]:
        rows = await self.database.fetch_all(
            """
            SELECT Id, Guild, Channel, Operation, Status, Payload
            FROM Queue_Cleanup_Jobs
            WHERE Guild = ? AND Status IN ('pending', 'partial')
            ORDER BY Id
            """,
            (guild.id,),
        )
        return tuple(
            QueueCleanupJob(
                id=row["Id"],
                guild_id=row["Guild"],
                channel_id=row["Channel"],
                operation=row["Operation"],
                status=row["Status"],
                payload=row["Payload"],
            )
            for row in rows
        )

    async def get_cleanup_items(self, job_id: int) -> tuple[QueueCleanupItem, ...]:
        rows = await self.database.fetch_all(
            """
            SELECT Kind, ParentId, ResourceId, Status, Attempts, LastError
            FROM Queue_Cleanup_Items WHERE JobId = ?
            ORDER BY CASE Kind
                WHEN 'role_scan' THEN 0
                WHEN 'role_member' THEN 1
                WHEN 'queue_message' THEN 2
                WHEN 'phase_message' THEN 3
                ELSE 4
            END, ResourceId
            """,
            (job_id,),
        )
        return tuple(
            QueueCleanupItem(
                kind=row["Kind"],
                parent_id=row["ParentId"],
                resource_id=row["ResourceId"],
                status=row["Status"],
                attempts=row["Attempts"],
                last_error=row["LastError"],
            )
            for row in rows
        )

    async def _insert_cleanup_items(
        self,
        connection: Connection,
        job_id: int,
        items: tuple[tuple[str, int | None, int], ...],
    ) -> None:
        await connection.executemany(
            """
            INSERT OR IGNORE INTO Queue_Cleanup_Items
                (JobId, Kind, ParentId, ResourceId)
            VALUES (?, ?, ?, ?)
            """,
            (
                (job_id, kind, parent_id, resource_id)
                for kind, parent_id, resource_id in items
            ),
        )

    async def add_cleanup_items(
        self, job_id: int, items: tuple[tuple[str, int | None, int], ...]
    ) -> bool:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                await self._insert_cleanup_items(connection, job_id, items)
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "Failed to persist QS cleanup resources for job %s.", job_id
            )
            return False

    async def update_cleanup_item(
        self,
        *,
        job_id: int,
        kind: str,
        parent_id: int | None,
        resource_id: int,
        completed: bool,
        error: str | None = None,
    ) -> bool:
        try:
            async with self.database.connect() as connection:
                await connection.execute(
                    """
                    UPDATE Queue_Cleanup_Items
                    SET Status = ?, Attempts = Attempts + 1, LastError = ?
                    WHERE JobId = ? AND Kind = ? AND ParentId IS ? AND ResourceId = ?
                    """,
                    (
                        "completed" if completed else "pending",
                        error,
                        job_id,
                        kind,
                        parent_id,
                        resource_id,
                    ),
                )
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "Failed to persist QS cleanup progress for job %s, resource %s/%s.",
                job_id,
                kind,
                resource_id,
            )
            return False

    async def update_cleanup_job_status(self, job_id: int, status: str) -> bool:
        if status not in {"pending", "partial", "completed"}:
            raise ValueError(f"Unsupported cleanup status: {status}")
        return await self.database.execute(
            """
            UPDATE Queue_Cleanup_Jobs SET Status = ?, UpdatedAt = ?
            WHERE Id = ?
            """,
            (status, discord.utils.utcnow().timestamp(), job_id),
        )

    async def prepare_reset_cleanup(
        self,
        *,
        guild: discord.Guild,
        configuration: QueueConfiguration,
        eruption_id: int,
        starts_at: float,
        ends_at: float,
        phases: tuple[tuple[float, float], ...],
        timezone_name: str,
        now: float,
    ) -> int | None:
        existing = await self.get_cleanup_job(
            guild=guild, channel_id=configuration.channel_id
        )
        if existing is not None:
            return existing.id if existing.operation == "reset" else None

        payload = json.dumps(
            {
                "eruption_id": eruption_id,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "phases": phases,
                "timezone": timezone_name,
            }
        )
        items: list[tuple[str, int | None, int]] = []
        for message_id in (
            configuration.message_id,
            configuration.destruction_message_id,
        ):
            if message_id is not None:
                items.append(("queue_message", configuration.channel_id, message_id))
        phase_rows = await self.database.fetch_all(
            f"""
            SELECT Thread, Message FROM {self.phases_table}
            WHERE Eruption = ?
            """,
            (eruption_id,),
        )
        for row in phase_rows:
            thread_id = row["Thread"]
            if row["Message"] is not None and thread_id is not None:
                items.append(("phase_message", thread_id, row["Message"]))
            if thread_id is not None:
                items.append(("thread", None, thread_id))
        if configuration.remove_role_on_reset:
            items.append(("role_scan", None, configuration.role_id))

        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                existing_row = await connection.execute(
                    """
                    SELECT Id, Operation FROM Queue_Cleanup_Jobs
                    WHERE Guild = ? AND Channel = ?
                      AND Status IN ('pending', 'partial')
                    ORDER BY Id DESC LIMIT 1
                    """,
                    (guild.id, configuration.channel_id),
                )
                existing_result = await existing_row.fetchone()
                if existing_result is not None:
                    await connection.rollback()
                    return (
                        existing_result["Id"]
                        if existing_result["Operation"] == "reset"
                        else None
                    )
                old_cursor = await connection.execute(
                    f"""
                    SELECT EndsAt FROM {self.eruptions_table}
                    WHERE Id = ? AND Guild = ? AND Channel = ?
                    """,
                    (eruption_id, guild.id, configuration.channel_id),
                )
                old_eruption = await old_cursor.fetchone()
                if old_eruption is None or old_eruption["EndsAt"] > now:
                    await connection.rollback()
                    return None
                cursor = await connection.execute(
                    """
                    INSERT INTO Queue_Cleanup_Jobs
                        (Guild, Channel, Operation, Payload, CreatedAt, UpdatedAt)
                    VALUES (?, ?, 'reset', ?, ?, ?)
                    """,
                    (
                        guild.id,
                        configuration.channel_id,
                        payload,
                        now,
                        now,
                    ),
                )
                job_id = cursor.lastrowid
                if job_id is None:
                    raise RuntimeError("SQLite did not return the cleanup job ID.")
                await self._insert_cleanup_items(connection, job_id, tuple(items))
                await connection.commit()
            return job_id
        except Exception:
            _logger.exception(
                "%s Failed to prepare QS reset cleanup in channel %s.",
                self.log_prefix(guild),
                configuration.channel_id,
            )
            return None

    async def prepare_remove_cleanup(
        self, *, guild: discord.Guild, channel_id: int, now: float
    ) -> int | None:
        existing = await self.get_cleanup_job(
            guild=guild, channel_id=channel_id, operation="remove"
        )
        if existing is not None:
            return existing.id
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                config_cursor = await connection.execute(
                    f"""
                    SELECT RoleId, Message, DestructionMessage
                    FROM {self.table_name} WHERE Guild = ? AND Channel = ?
                    """,
                    (guild.id, channel_id),
                )
                config = await config_cursor.fetchone()
                if config is None:
                    await connection.rollback()
                    return None
                eruption_cursor = await connection.execute(
                    f"SELECT Id FROM {self.eruptions_table} "
                    "WHERE Guild = ? AND Channel = ?",
                    (guild.id, channel_id),
                )
                eruption_rows = await eruption_cursor.fetchall()
                eruption_ids = tuple(row["Id"] for row in eruption_rows)
                items: list[tuple[str, int | None, int]] = []
                for message_id in (config["Message"], config["DestructionMessage"]):
                    if message_id is not None:
                        items.append(("queue_message", channel_id, message_id))
                if eruption_ids:
                    placeholders = ",".join("?" for _ in eruption_ids)
                    phase_cursor = await connection.execute(
                        f"""
                        SELECT Thread, Message FROM {self.phases_table}
                        WHERE Eruption IN ({placeholders})
                        """,
                        eruption_ids,
                    )
                    for phase in await phase_cursor.fetchall():
                        thread_id = phase["Thread"]
                        if phase["Message"] is not None and thread_id is not None:
                            items.append(("phase_message", thread_id, phase["Message"]))
                        if thread_id is not None:
                            items.append(("thread", None, thread_id))
                cursor = await connection.execute(
                    """
                    INSERT INTO Queue_Cleanup_Jobs
                        (Guild, Channel, Operation, Payload, CreatedAt, UpdatedAt)
                    VALUES (?, ?, 'remove', ?, ?, ?)
                    """,
                    (
                        guild.id,
                        channel_id,
                        json.dumps({"role_id": config["RoleId"]}),
                        now,
                        now,
                    ),
                )
                job_id = cursor.lastrowid
                if job_id is None:
                    raise RuntimeError("SQLite did not return the cleanup job ID.")
                await self._insert_cleanup_items(connection, job_id, tuple(items))
                for eruption_id in eruption_ids:
                    await connection.execute(
                        "DELETE FROM Queue_Reminders WHERE Eruption = ?",
                        (eruption_id,),
                    )
                    for table in (
                        self.destructions_table,
                        self.phase_members_table,
                        self.participants_table,
                        self.phases_table,
                    ):
                        await connection.execute(
                            f"DELETE FROM {table} WHERE Eruption = ?",
                            (eruption_id,),
                        )
                await connection.execute(
                    f"DELETE FROM {self.eruptions_table} "
                    "WHERE Guild = ? AND Channel = ?",
                    (guild.id, channel_id),
                )
                await connection.execute(
                    f"DELETE FROM {self.table_name} WHERE Guild = ? AND Channel = ?",
                    (guild.id, channel_id),
                )
                await connection.commit()
            return job_id
        except Exception:
            _logger.exception(
                "%s Failed to persist QS removal cleanup in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def reset_eruption(
        self,
        *,
        guild: discord.Guild,
        configuration: QueueConfiguration,
        cleanup_job_id: int,
        old_eruption_id: int,
        starts_at: float,
        ends_at: float,
        phases: tuple[tuple[float, float], ...],
        timezone_name: str,
        now: float,
    ) -> bool:
        settings = (
            configuration.eruption_start_reminder_enabled,
            configuration.eruption_start_reminder_minutes,
            configuration.eruption_end_reminder_enabled,
            configuration.eruption_end_reminder_minutes,
            configuration.phase_start_reminder_enabled,
            configuration.phase_start_reminder_minutes,
        )
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    f"""
                    SELECT Id FROM {self.eruptions_table}
                    WHERE CleanupJob = ? AND Guild = ? AND Channel = ?
                    """,
                    (cleanup_job_id, guild.id, configuration.channel_id),
                ) as cursor:
                    existing_new = await cursor.fetchone()
                if existing_new is not None:
                    await connection.commit()
                    return True
                async with connection.execute(
                    """
                    SELECT 1 FROM Queue_Cleanup_Jobs
                    WHERE Id = ? AND Guild = ? AND Channel = ?
                      AND Operation = 'reset'
                    """,
                    (cleanup_job_id, guild.id, configuration.channel_id),
                ) as cursor:
                    job_exists = await cursor.fetchone()
                if job_exists is None:
                    await connection.rollback()
                    return False
                async with connection.execute(
                    """
                    SELECT 1 FROM Queue_Cleanup_Items
                    WHERE JobId = ? AND Status != 'completed'
                    LIMIT 1
                    """,
                    (cleanup_job_id,),
                ) as cursor:
                    open_items = await cursor.fetchone()
                if open_items is not None:
                    await connection.rollback()
                    return False
                async with connection.execute(
                    f"""
                    SELECT EndsAt FROM {self.eruptions_table}
                    WHERE Id = ? AND Guild = ? AND Channel = ?
                    """,
                    (old_eruption_id, guild.id, configuration.channel_id),
                ) as cursor:
                    old = await cursor.fetchone()
                if old is None or old["EndsAt"] > now:
                    await connection.rollback()
                    return False
                await connection.execute(
                    "DELETE FROM Queue_Reminders WHERE Eruption = ?",
                    (old_eruption_id,),
                )
                for table in (
                    self.destructions_table,
                    self.phase_members_table,
                    self.participants_table,
                    self.phases_table,
                ):
                    await connection.execute(
                        f"DELETE FROM {table} WHERE Eruption = ?",
                        (old_eruption_id,),
                    )
                await connection.execute(
                    f"DELETE FROM {self.eruptions_table} WHERE Id = ?",
                    (old_eruption_id,),
                )
                cursor = await connection.execute(
                    f"""
                    INSERT INTO {self.eruptions_table}
                        (Guild, Channel, StartsAt, EndsAt, TimeZone, CreatedAt,
                         CleanupJob)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild.id,
                        configuration.channel_id,
                        starts_at,
                        ends_at,
                        timezone_name,
                        now,
                        cleanup_job_id,
                    ),
                )
                new_id = cursor.lastrowid
                if new_id is None:
                    raise RuntimeError("SQLite did not return the new eruption ID.")
                await connection.executemany(
                    f"INSERT INTO {self.phases_table} (Eruption, PhaseIndex, StartsAt, EndsAt) VALUES (?, ?, ?, ?)",
                    (
                        (new_id, index, start, end)
                        for index, (start, end) in enumerate(phases, 1)
                    ),
                )
                await connection.execute(
                    f"""
                    UPDATE {self.table_name}
                    SET NextStartAt = ?, TimeZone = ?,
                        Message = NULL, DestructionMessage = NULL
                    WHERE Guild = ? AND Channel = ?
                    """,
                    (
                        starts_at,
                        timezone_name,
                        guild.id,
                        configuration.channel_id,
                    ),
                )
                await self._insert_reminders(
                    connection, new_id, starts_at, ends_at, phases, now, settings
                )
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "%s Failed to reset QS eruption in channel %s.",
                self.log_prefix(guild),
                configuration.channel_id,
            )
            return False

    async def due_reminders(self, now: float) -> tuple[QueueReminder, ...]:
        rows = await self.database.fetch_all(
            """
            SELECT Eruption, Phase, Kind, DueAt, EventAt, Attempts
            FROM Queue_Reminders
            WHERE (Status = 'pending' AND DueAt <= ?)
               OR (Status = 'sending' AND LeaseUntil <= ?)
            ORDER BY DueAt LIMIT 25
            """,
            (now, now),
        )
        return tuple(
            QueueReminder(
                eruption_id=row["Eruption"],
                phase_id=row["Phase"] or None,
                kind=row["Kind"],
                due_at=row["DueAt"],
                event_at=row["EventAt"],
                attempts=row["Attempts"],
            )
            for row in rows
        )

    async def claim_reminder(self, reminder: QueueReminder, now: float) -> bool:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                cursor = await connection.execute(
                    """
                    UPDATE Queue_Reminders
                    SET Status = 'sending', LeaseUntil = ?, Attempts = Attempts + 1
                    WHERE Eruption = ? AND Phase = ? AND Kind = ?
                      AND ((Status = 'pending' AND DueAt <= ?)
                        OR (Status = 'sending' AND LeaseUntil <= ?))
                    """,
                    (
                        now + 120,
                        reminder.eruption_id,
                        reminder.phase_id or 0,
                        reminder.kind,
                        now,
                        now,
                    ),
                )
                claimed = cursor.rowcount == 1
                await connection.commit()
                return claimed
        except Exception:
            _logger.exception(
                "Failed to claim QS reminder %s for eruption %s.",
                reminder.kind,
                reminder.eruption_id,
            )
            return False

    async def finish_reminder(
        self, reminder: QueueReminder, *, success: bool, retry_at: float
    ) -> bool:
        return await self.database.execute(
            """
            UPDATE Queue_Reminders
            SET Status = ?, DueAt = ?, LeaseUntil = NULL
            WHERE Eruption = ? AND Phase = ? AND Kind = ? AND Status = 'sending'
            """,
            (
                "sent" if success else "pending",
                reminder.due_at if success else retry_at,
                reminder.eruption_id,
                reminder.phase_id or 0,
                reminder.kind,
            ),
        )

    async def skip_reminder(self, reminder: QueueReminder) -> bool:
        return await self.database.execute(
            """
            UPDATE Queue_Reminders
            SET Status = 'skipped', LeaseUntil = NULL
            WHERE Eruption = ? AND Phase = ? AND Kind = ? AND Status = 'sending'
            """,
            (
                reminder.eruption_id,
                reminder.phase_id or 0,
                reminder.kind,
            ),
        )

    async def phase_participants(self, phase_id: int) -> tuple[int, ...]:
        rows = await self.database.fetch_all(
            f"SELECT Member FROM {self.phase_members_table} WHERE Phase = ? ORDER BY JoinedAt, Member",
            (phase_id,),
        )
        return tuple(row["Member"] for row in rows)

    async def get_eruption(
        self, *, guild: discord.Guild, eruption_id: int
    ) -> Eruption | None:
        row = await self.database.fetch_one(
            f"""
            SELECT Id, Guild, Channel, StartsAt, EndsAt, TimeZone
            FROM {self.eruptions_table}
            WHERE Guild = ? AND Id = ?
            """,
            (guild.id, eruption_id),
        )
        return self._eruption_from_row(row) if row is not None else None

    async def get_current_eruption(
        self, *, guild: discord.Guild, channel_id: int, now: float
    ) -> Eruption | None:
        row = await self.database.fetch_one(
            f"""
            SELECT Id, Guild, Channel, StartsAt, EndsAt, TimeZone
            FROM {self.eruptions_table}
            WHERE Guild = ? AND Channel = ? AND EndsAt > ?
            ORDER BY StartsAt DESC LIMIT 1
            """,
            (guild.id, channel_id, now),
        )
        return self._eruption_from_row(row) if row is not None else None

    async def get_channel_eruptions(
        self, *, guild: discord.Guild, channel_id: int
    ) -> tuple[Eruption, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Id, Guild, Channel, StartsAt, EndsAt, TimeZone
            FROM {self.eruptions_table}
            WHERE Guild = ? AND Channel = ?
            ORDER BY StartsAt DESC
            """,
            (guild.id, channel_id),
        )
        return tuple(self._eruption_from_row(row) for row in rows)

    @staticmethod
    def _eruption_from_row(row: Row) -> Eruption:
        return Eruption(
            id=row["Id"],
            guild_id=row["Guild"],
            channel_id=row["Channel"],
            starts_at=row["StartsAt"],
            ends_at=row["EndsAt"],
            timezone=row["TimeZone"],
        )

    async def get_phases(self, eruption_id: int) -> tuple[QueuePhase, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Id, Eruption, PhaseIndex, StartsAt, EndsAt, Thread, Message
            FROM {self.phases_table}
            WHERE Eruption = ? ORDER BY PhaseIndex
            """,
            (eruption_id,),
        )
        return tuple(self._phase_from_row(row) for row in rows)

    @staticmethod
    def _phase_from_row(row: Row) -> QueuePhase:
        return QueuePhase(
            id=row["Id"],
            eruption_id=row["Eruption"],
            index=row["PhaseIndex"],
            starts_at=row["StartsAt"],
            ends_at=row["EndsAt"],
            thread_id=row["Thread"],
            message_id=row["Message"],
        )

    async def set_main_messages(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        overview_message_id: int,
        destruction_message_id: int,
    ) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET Message = ?, DestructionMessage = ?
            WHERE Guild = ? AND Channel = ?
            """,
            (
                overview_message_id,
                destruction_message_id,
                guild.id,
                channel_id,
            ),
        )

    async def set_phase_messages(
        self, *, phase_id: int, thread_id: int, message_id: int
    ) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.phases_table} SET Thread = ?, Message = ? WHERE Id = ?
            """,
            (thread_id, message_id, phase_id),
        )

    async def join_phase(
        self,
        *,
        guild: discord.Guild,
        eruption_id: int,
        phase_id: int,
        member_id: int,
        joined_at: float,
        role_managed: bool,
    ) -> str:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    f"""
                    SELECT StartsAt, EndsAt FROM {self.eruptions_table}
                    WHERE Id = ? AND Guild = ?
                    """,
                    (eruption_id, guild.id),
                ) as cursor:
                    eruption = await cursor.fetchone()
                async with connection.execute(
                    f"""
                    SELECT StartsAt, EndsAt FROM {self.phases_table}
                    WHERE Id = ? AND Eruption = ?
                    """,
                    (phase_id, eruption_id),
                ) as cursor:
                    phase = await cursor.fetchone()
                if eruption is None or phase is None or joined_at >= eruption["EndsAt"]:
                    await connection.rollback()
                    return "closed"
                async with connection.execute(
                    f"""
                    SELECT 1 FROM {self.phase_members_table}
                    WHERE Eruption = ? AND Phase = ? AND Member = ?
                    """,
                    (eruption_id, phase_id, member_id),
                ) as cursor:
                    existing = await cursor.fetchone()
                if existing is not None:
                    await connection.execute(
                        f"""
                        DELETE FROM {self.phase_members_table}
                        WHERE Eruption = ? AND Phase = ? AND Member = ?
                        """,
                        (eruption_id, phase_id, member_id),
                    )
                    async with connection.execute(
                        f"""
                        SELECT 1 FROM {self.phase_members_table}
                        WHERE Eruption = ? AND Member = ? LIMIT 1
                        """,
                        (eruption_id, member_id),
                    ) as cursor:
                        remaining = await cursor.fetchone()
                    if remaining is None:
                        managed_role = await connection.execute(
                            f"SELECT RoleManaged FROM {self.participants_table} "
                            "WHERE Eruption = ? AND Member = ?",
                            (eruption_id, member_id),
                        )
                        managed_row = await managed_role.fetchone()
                        async with connection.execute(
                            f"SELECT 1 FROM {self.destructions_table} "
                            "WHERE Eruption = ? AND Member = ?",
                            (eruption_id, member_id),
                        ) as cursor:
                            destruction = await cursor.fetchone()
                        if destruction is None:
                            await connection.execute(
                                f"DELETE FROM {self.participants_table} "
                                "WHERE Eruption = ? AND Member = ?",
                                (eruption_id, member_id),
                            )
                        await connection.commit()
                        return (
                            "left_final_role_managed"
                            if managed_row is not None and managed_row["RoleManaged"]
                            else "left_final"
                        )
                    await connection.commit()
                    return "left"
                if joined_at >= phase["EndsAt"]:
                    await connection.rollback()
                    return "phase_closed"
                async with connection.execute(
                    f"SELECT 1 FROM {self.participants_table} "
                    "WHERE Eruption = ? AND Member = ?",
                    (eruption_id, member_id),
                ) as cursor:
                    participant = await cursor.fetchone()
                if participant is None:
                    async with connection.execute(
                        f"SELECT COUNT(*) FROM {self.participants_table} "
                        "WHERE Eruption = ?",
                        (eruption_id,),
                    ) as cursor:
                        count_row = await cursor.fetchone()
                    if count_row[0] >= 40:
                        await connection.rollback()
                        return "full"
                    await connection.execute(
                        f"INSERT INTO {self.participants_table} "
                        "(Eruption, Member, JoinedAt, RoleManaged) "
                        "VALUES (?, ?, ?, ?)",
                        (eruption_id, member_id, joined_at, int(role_managed)),
                    )
                elif role_managed:
                    await connection.execute(
                        f"""
                        UPDATE {self.participants_table}
                        SET RoleManaged = 1
                        WHERE Eruption = ? AND Member = ?
                        """,
                        (eruption_id, member_id),
                    )
                await connection.execute(
                    f"""
                    INSERT INTO {self.phase_members_table}
                        (Eruption, Phase, Member, JoinedAt)
                    VALUES (?, ?, ?, ?)
                    """,
                    (eruption_id, phase_id, member_id, joined_at),
                )
                await connection.commit()
                return "joined"
        except Exception:
            _logger.exception(
                "%s Failed to toggle phase signup for member %s.",
                self.log_prefix(guild),
                member_id,
            )
            return "error"

    async def get_phase_members(
        self, *, eruption_id: int, phase_id: int
    ) -> tuple[PhaseParticipant, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Member, JoinedAt FROM {self.phase_members_table}
            WHERE Eruption = ? AND Phase = ? ORDER BY JoinedAt, Member
            """,
            (eruption_id, phase_id),
        )
        return tuple(
            PhaseParticipant(member_id=row["Member"], joined_at=row["JoinedAt"])
            for row in rows
        )

    async def get_eruption_participant_ids(self, eruption_id: int) -> tuple[int, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Member FROM {self.participants_table}
            WHERE Eruption = ? ORDER BY JoinedAt, Member
            """,
            (eruption_id,),
        )
        return tuple(row["Member"] for row in rows)

    async def get_eruption_counts(self, eruption_id: int) -> tuple[int, int]:
        participants = await self.database.fetch_one(
            f"SELECT COUNT(*) AS Count FROM {self.participants_table} "
            "WHERE Eruption = ?",
            (eruption_id,),
        )
        destructions = await self.database.fetch_one(
            f"SELECT COUNT(*) AS Count FROM {self.destructions_table} "
            "WHERE Eruption = ?",
            (eruption_id,),
        )
        return (
            participants["Count"] if participants is not None else 0,
            destructions["Count"] if destructions is not None else 0,
        )

    async def get_phase(self, phase_id: int) -> QueuePhase | None:
        row = await self.database.fetch_one(
            f"""
            SELECT Id, Eruption, PhaseIndex, StartsAt, EndsAt, Thread, Message
            FROM {self.phases_table} WHERE Id = ?
            """,
            (phase_id,),
        )
        return self._phase_from_row(row) if row is not None else None

    async def get_member_phase_ids(
        self, *, eruption_id: int, member_id: int
    ) -> tuple[int, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Phase FROM {self.phase_members_table}
            WHERE Eruption = ? AND Member = ?
            """,
            (eruption_id, member_id),
        )
        return tuple(row["Phase"] for row in rows)

    async def record_destruction(
        self,
        *,
        guild: discord.Guild,
        eruption_id: int,
        phase_id: int,
        member_id: int,
        confirmed_at: float,
        details: str,
    ) -> str:
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    f"""
                    SELECT 1
                    FROM {self.phase_members_table} member
                    JOIN {self.phases_table} phase
                      ON phase.Id = member.Phase
                    JOIN {self.eruptions_table} eruption ON eruption.Id = member.Eruption
                    WHERE member.Eruption = ? AND member.Phase = ?
                      AND member.Member = ? AND eruption.Guild = ?
                      AND phase.StartsAt <= ? AND phase.EndsAt > ?
                    """,
                    (
                        eruption_id,
                        phase_id,
                        member_id,
                        guild.id,
                        confirmed_at,
                        confirmed_at,
                    ),
                ) as cursor:
                    eligible = await cursor.fetchone()
                if eligible is None:
                    await connection.rollback()
                    return "ineligible"
                async with connection.execute(
                    f"SELECT 1 FROM {self.destructions_table} "
                    "WHERE Eruption = ? AND Member = ?",
                    (eruption_id, member_id),
                ) as cursor:
                    existing = await cursor.fetchone()
                if existing is not None:
                    await connection.rollback()
                    return "already_confirmed"
                await connection.execute(
                    f"""
                    INSERT INTO {self.destructions_table}
                        (Eruption, Member, Phase, ConfirmedAt, Details)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (eruption_id, member_id, phase_id, confirmed_at, details),
                )
                await connection.commit()
                return "confirmed"
        except Exception:
            _logger.exception(
                "%s Failed to record base destruction for member %s.",
                self.log_prefix(guild),
                member_id,
            )
            return "error"

    async def get_destructions(self, eruption_id: int) -> tuple[BaseDestruction, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Member, Phase, ConfirmedAt, Details
            FROM {self.destructions_table}
            WHERE Eruption = ? ORDER BY ConfirmedAt, Member
            """,
            (eruption_id,),
        )
        return tuple(
            BaseDestruction(
                member_id=row["Member"],
                phase_id=row["Phase"],
                confirmed_at=row["ConfirmedAt"],
                details=row["Details"],
            )
            for row in rows
        )
