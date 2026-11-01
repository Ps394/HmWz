"""Transactional storage owned exclusively by the Qs module."""

from __future__ import annotations

from hmwz.sqlite_db import Base, Database

from ..models import BaseReport, Configuration, Phase, validate_schedule
from .bases import BaseReportRepository
from .members import MemberRepository
from .phases import PhaseRepository


class QsRepository(Base):
    """Persist channel events, phase signups and one report per member."""

    table_name = "HsQsEvents"

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self._phases = PhaseRepository(database)
        self._members = MemberRepository(database)
        self._bases = BaseReportRepository(database)

    @property
    def table(self) -> str:
        """Return the channel event schema."""
        return """
            CREATE TABLE IF NOT EXISTS HsQsEvents (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Role INTEGER NOT NULL,
                Date TEXT NOT NULL,
                Timezone TEXT NOT NULL,
                Message INTEGER,
                BasesMessage INTEGER,
                EruptionStart INTEGER NOT NULL DEFAULT 0,
                StartNotified INTEGER NOT NULL DEFAULT 0,
                EndNotified INTEGER NOT NULL DEFAULT 0,
                State TEXT NOT NULL DEFAULT 'active',
                PRIMARY KEY (Guild, Channel),
                FOREIGN KEY (Guild) REFERENCES Servers (Guild) ON DELETE CASCADE
            ) WITHOUT ROWID
            """

    async def ensure_schema(self) -> bool:
        """Create independent Qs tables in foreign-key dependency order."""
        for repository in (self, self._phases, self._members, self._bases):
            if not await self.database.execute(repository.table):
                return False
        await self._bases.migrate_schema()
        if not await self.ensure_columns(
            (
                ("EruptionStart", "INTEGER NOT NULL DEFAULT 0"),
                ("StartNotified", "INTEGER NOT NULL DEFAULT 0"),
                ("EndNotified", "INTEGER NOT NULL DEFAULT 0"),
                ("State", "TEXT NOT NULL DEFAULT 'active'"),
            )
        ):
            return False
        if not await self._phases.ensure_columns(
            (
                ("DurationHours", "INTEGER NOT NULL DEFAULT 2"),
                ("GoalNotified", "INTEGER NOT NULL DEFAULT 0"),
                ("MembersMessage", "INTEGER"),
                ("StartNotified", "INTEGER NOT NULL DEFAULT 0"),
            )
        ):
            return False
        if not await self.database.execute(
            "UPDATE HsQsEvents SET EruptionStart=(SELECT MIN(StartsAt) FROM HsQsPhases "
            "WHERE HsQsPhases.Guild=HsQsEvents.Guild AND HsQsPhases.Channel=HsQsEvents.Channel) "
            "WHERE EruptionStart=0 AND EXISTS (SELECT 1 FROM HsQsPhases "
            "WHERE HsQsPhases.Guild=HsQsEvents.Guild AND HsQsPhases.Channel=HsQsEvents.Channel)"
        ):
            return False
        return True

    async def configure(
        self,
        guild_id: int,
        channel_id: int,
        role_id: int,
        date: str,
        timezone: str,
        starts: tuple[int, ...],
        *,
        eruption_start: int | None = None,
        durations: tuple[int, ...] | None = None,
        reset: bool = False,
    ) -> None:
        """Create or update an event atomically, preserving signups and reports."""
        durations = durations if durations is not None else (2,) * len(starts)
        eruption_start = (
            eruption_start if eruption_start is not None else min(starts, default=0)
        )
        validate_schedule(eruption_start, starts, durations)
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute(
                """INSERT INTO HsQsEvents (Guild, Channel, Role, Date, Timezone, EruptionStart)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (Guild, Channel) DO UPDATE SET
                    Role=excluded.Role, Date=excluded.Date, Timezone=excluded.Timezone,
                    StartNotified=CASE WHEN EruptionStart=excluded.EruptionStart THEN StartNotified ELSE 0 END,
                    EndNotified=CASE WHEN EruptionStart=excluded.EruptionStart THEN EndNotified ELSE 0 END,
                    EruptionStart=excluded.EruptionStart""",
                (guild_id, channel_id, role_id, date, timezone, eruption_start),
            )
            if reset:
                await connection.execute(
                    "DELETE FROM HsQsMembers WHERE Guild=? AND Channel=?",
                    (guild_id, channel_id),
                )
                await connection.execute(
                    "DELETE FROM HsQsBases WHERE Guild=? AND Channel=?",
                    (guild_id, channel_id),
                )
                await connection.execute(
                    "UPDATE HsQsEvents SET Message=NULL, BasesMessage=NULL, StartNotified=0, "
                    "EndNotified=0, State='active' WHERE Guild=? AND Channel=?",
                    (guild_id, channel_id),
                )
                await connection.execute(
                    "UPDATE HsQsPhases SET Message=NULL, MembersMessage=NULL, GoalNotified=0, StartNotified=0 WHERE Guild=? AND Channel=?",
                    (guild_id, channel_id),
                )
            await connection.execute(
                "DELETE FROM HsQsPhases WHERE Guild=? AND Channel=? AND Phase>?",
                (guild_id, channel_id, len(starts)),
            )
            await connection.executemany(
                """INSERT INTO HsQsPhases (Guild, Channel, Phase, StartsAt, DurationHours)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (Guild, Channel, Phase) DO UPDATE SET
                    StartNotified=CASE WHEN StartsAt=excluded.StartsAt THEN StartNotified ELSE 0 END,
                    StartsAt=excluded.StartsAt, DurationHours=excluded.DurationHours""",
                [
                    (guild_id, channel_id, index, start, duration)
                    for index, (start, duration) in enumerate(
                        zip(starts, durations, strict=True), 1
                    )
                ],
            )
            await connection.commit()

    async def get(self, guild_id: int, channel_id: int) -> Configuration | None:
        """Return one event configuration, if present."""
        row = await self.database.fetch_one(
            "SELECT * FROM HsQsEvents WHERE Guild=? AND Channel=?",
            (guild_id, channel_id),
        )
        return (
            Configuration(
                row["Channel"],
                row["Role"],
                row["Date"],
                row["Timezone"],
                row["Message"],
                row["BasesMessage"],
                row["EruptionStart"],
                bool(row["StartNotified"]),
                bool(row["EndNotified"]),
                row["State"],
            )
            if row is not None
            else None
        )

    async def all(self, guild_id: int) -> tuple[Configuration, ...]:
        """Return this guild's channel configurations."""
        rows = await self.database.fetch_all(
            "SELECT * FROM HsQsEvents WHERE Guild=? ORDER BY Channel", (guild_id,)
        )
        return tuple(
            Configuration(
                row["Channel"],
                row["Role"],
                row["Date"],
                row["Timezone"],
                row["Message"],
                row["BasesMessage"],
                row["EruptionStart"],
                bool(row["StartNotified"]),
                bool(row["EndNotified"]),
                row["State"],
            )
            for row in rows
        )

    async def phases(self, guild_id: int, channel_id: int) -> tuple[Phase, ...]:
        """Return all configured phases in display order."""
        return await self._phases.get(guild_id, channel_id)

    async def save_messages(
        self, guild_id: int, channel_id: int, message_id: int, bases_message_id: int
    ) -> bool:
        """Save the overview and destroyed-base listing message IDs."""
        return await self.database.execute(
            "UPDATE HsQsEvents SET Message=?, BasesMessage=? WHERE Guild=? AND Channel=?",
            (message_id, bases_message_id, guild_id, channel_id),
        )

    async def save_thread(
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        thread_id: int,
        message_id: int | None,
    ) -> bool:
        """Persist a thread immediately, even before its message can be sent."""
        return await self._phases.save_thread(
            guild_id, channel_id, phase_index, thread_id, message_id
        )

    async def members(
        self, guild_id: int, channel_id: int, phase_index: int
    ) -> tuple[int, ...]:
        """Return a phase's signed-up Discord members."""
        return await self._members.get(guild_id, channel_id, phase_index)

    async def save_members_message(
        self, guild_id: int, channel_id: int, phase_index: int, message_id: int
    ) -> bool:
        """Save a phase's separate participant overview message ID."""
        return await self._phases.save_members_message(
            guild_id, channel_id, phase_index, message_id
        )

    async def toggle(
        self, guild_id: int, channel_id: int, phase_index: int, member_id: int
    ) -> bool:
        """Atomically toggle phase participation and return the new joined state."""
        return await self._members.toggle(guild_id, channel_id, phase_index, member_id)

    async def reports(self, guild_id: int, channel_id: int) -> tuple[BaseReport, ...]:
        """Return all player reports in submission order."""
        return await self._bases.get(guild_id, channel_id)

    async def withdraw_report(
        self, guild_id: int, channel_id: int, phase_index: int, member_id: int
    ) -> bool:
        """Remove a player's report only from the specified event and phase."""
        return await self._bases.withdraw(guild_id, channel_id, phase_index, member_id)

    async def report(
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        member_id: int,
        display_name: str,
        created_at: int,
    ) -> None:
        """Insert one report per player, enforcing the forty-base limit."""
        await self._bases.add(
            guild_id, channel_id, phase_index, member_id, display_name, created_at
        )

    async def remove(self, guild_id: int, channel_id: int | None = None) -> bool:
        """Remove event settings and their dependent data, never other modules."""
        return await self.database.execute(
            "DELETE FROM HsQsEvents WHERE Guild=?"
            + (" AND Channel=?" if channel_id is not None else ""),
            (guild_id, channel_id) if channel_id is not None else (guild_id,),
        )

    async def remove_member(
        self, guild_id: int, member_id: int, channel_id: int | None = None
    ) -> bool:
        """Remove signups but retain the member's historical destroyed-base report."""
        return await self._members.remove(guild_id, member_id, channel_id)

    async def set_state(self, guild_id: int, channel_id: int, state: str) -> bool:
        """Persist maintenance state so deletion events cannot restore old messages."""
        if state not in ("active", "resetting", "removing"):
            raise ValueError("Unknown Qs maintenance state.")
        return await self.database.execute(
            "UPDATE HsQsEvents SET State=? WHERE Guild=? AND Channel=?",
            (state, guild_id, channel_id),
        )

    async def notified(
        self, guild_id: int, channel_id: int, event: str, phase_index: int | None = None
    ) -> bool:
        """Persist delivery or intentional skipping of a notification."""
        if event in ("goal", "phase_start") and phase_index is not None:
            column = "GoalNotified" if event == "goal" else "StartNotified"
            return await self.database.execute(
                f"UPDATE HsQsPhases SET {column}=1 WHERE Guild=? AND Channel=? AND Phase=?",
                (guild_id, channel_id, phase_index),
            )
        if event not in ("start", "end"):
            raise ValueError("Unknown Qs notification.")
        column = "StartNotified" if event == "start" else "EndNotified"
        return await self.database.execute(
            f"UPDATE HsQsEvents SET {column}=1 WHERE Guild=? AND Channel=?",
            (guild_id, channel_id),
        )
