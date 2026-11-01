"""Transactional persistence for Qs phase signups."""

from hmwz.sqlite_db import Base


class MemberRepository(Base):
    """Store phase participation separately from destroyed-base history."""

    table_name = "HsQsMembers"

    @property
    def table(self) -> str:
        """Return the signup schema with cascading phase ownership."""
        return """
            CREATE TABLE IF NOT EXISTS HsQsMembers (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Phase INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                PRIMARY KEY (Guild, Channel, Phase, Member),
                FOREIGN KEY (Guild, Channel, Phase)
                    REFERENCES HsQsPhases (Guild, Channel, Phase) ON DELETE CASCADE
            ) WITHOUT ROWID
            """

    async def get(
        self, guild_id: int, channel_id: int, phase_index: int
    ) -> tuple[int, ...]:
        """Return a phase's signed-up Discord members."""
        rows = await self.database.fetch_all(
            "SELECT Member FROM HsQsMembers WHERE Guild=? AND Channel=? AND Phase=? "
            "ORDER BY Member",
            (guild_id, channel_id, phase_index),
        )
        return tuple(row["Member"] for row in rows)

    async def toggle(
        self, guild_id: int, channel_id: int, phase_index: int, member_id: int
    ) -> bool:
        """Atomically toggle participation and return the new joined state."""
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            async with connection.execute(
                "SELECT 1 FROM HsQsMembers WHERE Guild=? AND Channel=? "
                "AND Phase=? AND Member=?",
                (guild_id, channel_id, phase_index, member_id),
            ) as cursor:
                joined = await cursor.fetchone() is not None
            query = (
                "DELETE FROM HsQsMembers WHERE Guild=? AND Channel=? AND Phase=? AND Member=?"
                if joined
                else "INSERT INTO HsQsMembers (Guild, Channel, Phase, Member) VALUES (?, ?, ?, ?)"
            )
            await connection.execute(
                query, (guild_id, channel_id, phase_index, member_id)
            )
            await connection.commit()
        return not joined

    async def remove(
        self, guild_id: int, member_id: int, channel_id: int | None = None
    ) -> bool:
        """Remove signups but retain the member's historical base report."""
        return await self.database.execute(
            "DELETE FROM HsQsMembers WHERE Guild=? AND Member=?"
            + (" AND Channel=?" if channel_id is not None else ""),
            (guild_id, member_id, channel_id)
            if channel_id is not None
            else (guild_id, member_id),
        )
