"""Persistence for unique Qs destroyed-base reports."""

from hmwz.sqlite_db import Base

from ..models import BASE_TOTAL, BaseReport


class BaseLimitReached(ValueError):
    """The event already has reports for all forty destroyed bases."""


class DuplicateBaseReport(ValueError):
    """The member has already reported a destroyed base for this event."""


class BaseReportRepository(Base):
    """Enforce one destroyed-base report per member."""

    table_name = "HsQsBases"

    @property
    def table(self) -> str:
        """Return the member-based destroyed-base report schema."""
        return """
            CREATE TABLE IF NOT EXISTS HsQsBases (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Phase INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                DisplayName TEXT NOT NULL,
                CreatedAt INTEGER NOT NULL,
                PRIMARY KEY (Guild, Channel, Member),
                FOREIGN KEY (Guild, Channel, Phase)
                    REFERENCES HsQsPhases (Guild, Channel, Phase) ON DELETE CASCADE
            ) WITHOUT ROWID
            """

    async def migrate_schema(self) -> None:
        """Preserve legacy reports while removing base numbers and comments."""
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            async with connection.execute("PRAGMA table_info(HsQsBases)") as cursor:
                columns = {row["name"] for row in await cursor.fetchall()}
            if "Base" in columns:
                await connection.execute(
                    "ALTER TABLE HsQsBases RENAME TO HsQsBasesLegacy"
                )
                await connection.execute(self.table)
                await connection.execute(
                    "INSERT INTO HsQsBases (Guild, Channel, Phase, Member, DisplayName, CreatedAt) "
                    "SELECT Guild, Channel, Phase, Member, '', CreatedAt FROM HsQsBasesLegacy"
                )
                await connection.execute("DROP TABLE HsQsBasesLegacy")
            await connection.commit()

    async def get(self, guild_id: int, channel_id: int) -> tuple[BaseReport, ...]:
        """Return reports in submission order."""
        rows = await self.database.fetch_all(
            "SELECT * FROM HsQsBases WHERE Guild=? AND Channel=? ORDER BY CreatedAt, Member",
            (guild_id, channel_id),
        )
        return tuple(
            BaseReport(
                row["Member"], row["Phase"], row["DisplayName"], row["CreatedAt"]
            )
            for row in rows
        )

    async def add(
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        member_id: int,
        display_name: str,
        created_at: int,
    ) -> None:
        """Save a player's report once, enforcing the forty-base limit atomically."""
        limit_reached = False
        duplicate_report = False
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            async with connection.execute(
                "SELECT COUNT(*) FROM HsQsBases WHERE Guild=? AND Channel=?",
                (guild_id, channel_id),
            ) as cursor:
                row = await cursor.fetchone()
            if row is not None and row[0] >= BASE_TOTAL:
                limit_reached = True
            else:
                async with connection.execute(
                    "SELECT 1 FROM HsQsBases WHERE Guild=? AND Channel=? AND Member=?",
                    (guild_id, channel_id, member_id),
                ) as cursor:
                    duplicate_report = await cursor.fetchone() is not None
                if not duplicate_report:
                    await connection.execute(
                        "INSERT INTO HsQsBases (Guild, Channel, Phase, Member, DisplayName, CreatedAt) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            guild_id,
                            channel_id,
                            phase_index,
                            member_id,
                            display_name,
                            created_at,
                        ),
                    )
            await connection.commit()
        if limit_reached:
            raise BaseLimitReached("All forty bases have already been reported.")
        if duplicate_report:
            raise DuplicateBaseReport("This member has already reported a base.")

    async def withdraw(
        self, guild_id: int, channel_id: int, phase_index: int, member_id: int
    ) -> bool:
        """Delete exactly one player's report in the specified phase."""
        async with self.database.connect() as connection:
            async with connection.execute(
                "DELETE FROM HsQsBases WHERE Guild=? AND Channel=? AND Phase=? AND Member=?",
                (guild_id, channel_id, phase_index, member_id),
            ) as cursor:
                removed = cursor.rowcount == 1
            await connection.commit()
            return removed
