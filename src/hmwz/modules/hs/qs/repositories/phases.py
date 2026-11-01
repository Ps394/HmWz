"""Persistence for Qs phase schedules and Discord threads."""

from hmwz.sqlite_db import Base

from ..models import Phase


class PhaseRepository(Base):
    """Store the configured phases belonging to a channel event."""

    table_name = "HsQsPhases"

    @property
    def table(self) -> str:
        """Return the phase schema with cascading event ownership."""
        return """
            CREATE TABLE IF NOT EXISTS HsQsPhases (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Phase INTEGER NOT NULL CHECK (Phase BETWEEN 1 AND 5),
                StartsAt INTEGER NOT NULL,
                Thread INTEGER,
                Message INTEGER,
                MembersMessage INTEGER,
                DurationHours INTEGER NOT NULL DEFAULT 2 CHECK (DurationHours BETWEEN 1 AND 3),
                GoalNotified INTEGER NOT NULL DEFAULT 0,
                StartNotified INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (Guild, Channel, Phase),
                FOREIGN KEY (Guild, Channel) REFERENCES HsQsEvents (Guild, Channel)
                    ON DELETE CASCADE
            ) WITHOUT ROWID
            """

    async def get(self, guild_id: int, channel_id: int) -> tuple[Phase, ...]:
        """Return all configured phases in display order."""
        rows = await self.database.fetch_all(
            "SELECT * FROM HsQsPhases WHERE Guild=? AND Channel=? ORDER BY Phase",
            (guild_id, channel_id),
        )
        return tuple(
            Phase(
                row["Phase"],
                row["StartsAt"],
                row["Thread"],
                row["Message"],
                row["DurationHours"],
                bool(row["GoalNotified"]),
                row["MembersMessage"],
                bool(row["StartNotified"]),
            )
            for row in rows
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
        return await self.database.execute(
            "UPDATE HsQsPhases SET MembersMessage=CASE WHEN Thread=? THEN MembersMessage ELSE NULL END, "
            "Thread=?, Message=? "
            "WHERE Guild=? AND Channel=? AND Phase=?",
            (thread_id, thread_id, message_id, guild_id, channel_id, phase_index),
        )

    async def save_members_message(
        self, guild_id: int, channel_id: int, phase_index: int, message_id: int
    ) -> bool:
        """Persist the separate participant overview for a phase."""
        return await self.database.execute(
            "UPDATE HsQsPhases SET MembersMessage=? WHERE Guild=? AND Channel=? AND Phase=?",
            (message_id, guild_id, channel_id, phase_index),
        )
