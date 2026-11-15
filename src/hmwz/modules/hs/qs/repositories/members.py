"""Transactional persistence for Qs phase signups."""

from ..models import MemberSignup
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
                GameAccount TEXT NOT NULL DEFAULT '' COLLATE NOCASE,
                PRIMARY KEY (Guild, Channel, Phase, Member, GameAccount),
                FOREIGN KEY (Guild, Channel, Phase)
                    REFERENCES HsQsPhases (Guild, Channel, Phase) ON DELETE CASCADE
            ) WITHOUT ROWID
            """

    async def migrate_schema(self) -> bool:
        """Allow one signup per account while preserving legacy main-account rows."""
        columns = await self.database.fetch_all('PRAGMA table_info("HsQsMembers")')
        primary_key = tuple(
            row["name"]
            for row in sorted(columns, key=lambda row: row["pk"])
            if row["pk"]
        )
        account_column = next(row for row in columns if row["name"] == "GameAccount")
        if (
            primary_key == ("Guild", "Channel", "Phase", "Member", "GameAccount")
            and account_column["notnull"]
        ):
            return True
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute(
                """
                CREATE TABLE HsQsMembers_new (
                    Guild INTEGER NOT NULL,
                    Channel INTEGER NOT NULL,
                    Phase INTEGER NOT NULL,
                    Member INTEGER NOT NULL,
                    GameAccount TEXT NOT NULL DEFAULT '' COLLATE NOCASE,
                    PRIMARY KEY (Guild, Channel, Phase, Member, GameAccount),
                    FOREIGN KEY (Guild, Channel, Phase)
                        REFERENCES HsQsPhases (Guild, Channel, Phase)
                        ON DELETE CASCADE
                ) WITHOUT ROWID
                """
            )
            await connection.execute(
                """
                INSERT INTO HsQsMembers_new
                    (Guild, Channel, Phase, Member, GameAccount)
                SELECT Guild, Channel, Phase, Member, COALESCE(GameAccount, '')
                FROM HsQsMembers
                """
            )
            await connection.execute("DROP TABLE HsQsMembers")
            await connection.execute(
                "ALTER TABLE HsQsMembers_new RENAME TO HsQsMembers"
            )
            await connection.commit()
        return True

    async def get(
        self, guild_id: int, channel_id: int, phase_index: int
    ) -> tuple[int, ...]:
        """Return a phase's signed-up Discord members."""
        rows = await self.database.fetch_all(
            "SELECT Member FROM HsQsMembers "
            "WHERE Guild=? AND Channel=? AND Phase=? ORDER BY Member, GameAccount",
            (guild_id, channel_id, phase_index),
        )
        return tuple(row["Member"] for row in rows)

    async def get_signups(
        self, guild_id: int, channel_id: int, phase_index: int
    ) -> tuple[MemberSignup, ...]:
        """Return a phase's signups and selected game accounts."""
        rows = await self.database.fetch_all(
            "SELECT Member, GameAccount FROM HsQsMembers "
            "WHERE Guild=? AND Channel=? AND Phase=? "
            "ORDER BY Member, GameAccount COLLATE NOCASE",
            (guild_id, channel_id, phase_index),
        )
        return tuple(
            MemberSignup(row["Member"], row["GameAccount"] or None) for row in rows
        )

    async def toggle(
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        member_id: int,
        game_account: str | None = None,
    ) -> bool:
        """Atomically toggle one account's signup and return the new joined state."""
        account_key = game_account or ""
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            async with connection.execute(
                "SELECT 1 FROM HsQsMembers WHERE Guild=? AND Channel=? "
                "AND Phase=? AND Member=? AND GameAccount=?",
                (guild_id, channel_id, phase_index, member_id, account_key),
            ) as cursor:
                joined = await cursor.fetchone() is not None
            query = (
                "DELETE FROM HsQsMembers WHERE Guild=? AND Channel=? AND Phase=? "
                "AND Member=? AND GameAccount=?"
                if joined
                else "INSERT INTO HsQsMembers "
                "(Guild, Channel, Phase, Member, GameAccount) VALUES (?, ?, ?, ?, ?)"
            )
            await connection.execute(
                query,
                (guild_id, channel_id, phase_index, member_id, account_key),
            )
            await connection.commit()
        return not joined

    async def join(
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        member_id: int,
        game_account: str | None,
    ) -> bool:
        """Add one account signup without toggling off or replacing other accounts."""
        return await self.database.execute(
            """
            INSERT INTO HsQsMembers (Guild, Channel, Phase, Member, GameAccount)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (Guild, Channel, Phase, Member, GameAccount) DO NOTHING
            """,
            (guild_id, channel_id, phase_index, member_id, game_account or ""),
        )

    async def remove_signup(
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        member_id: int,
        game_account: str | None,
    ) -> bool:
        """Remove one account's signup without affecting the member's others."""
        return await self.database.execute(
            """
            DELETE FROM HsQsMembers
            WHERE Guild=? AND Channel=? AND Phase=? AND Member=? AND GameAccount=?
            """,
            (guild_id, channel_id, phase_index, member_id, game_account or ""),
        )

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
