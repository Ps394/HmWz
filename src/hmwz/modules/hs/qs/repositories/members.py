"""Transactional persistence for Qs phase signups."""

from __future__ import annotations

import time

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
                CreatedAt INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (Guild, Channel, Phase, Member, GameAccount),
                FOREIGN KEY (Guild, Channel, Phase)
                    REFERENCES HsQsPhases (Guild, Channel, Phase) ON DELETE CASCADE
            ) WITHOUT ROWID
            """

    async def migrate_schema(self) -> bool:
        """Allow one signup per account while preserving legacy main-account rows."""
        columns = await self.database.fetch_all('PRAGMA table_info("HsQsMembers")')
        column_names = {row["name"] for row in columns}
        primary_key = tuple(
            row["name"]
            for row in sorted(columns, key=lambda row: row["pk"])
            if row["pk"]
        )
        account_column = next(row for row in columns if row["name"] == "GameAccount")
        if (
            primary_key == ("Guild", "Channel", "Phase", "Member", "GameAccount")
            and account_column["notnull"]
            and "CreatedAt" in column_names
        ):
            return True
        created_at = "CreatedAt" if "CreatedAt" in column_names else "0"
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
                    CreatedAt INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (Guild, Channel, Phase, Member, GameAccount),
                    FOREIGN KEY (Guild, Channel, Phase)
                        REFERENCES HsQsPhases (Guild, Channel, Phase)
                        ON DELETE CASCADE
                ) WITHOUT ROWID
                """
            )
            await connection.execute(
                f"""
                INSERT INTO HsQsMembers_new
                    (Guild, Channel, Phase, Member, GameAccount, CreatedAt)
                SELECT Guild, Channel, Phase, Member, COALESCE(GameAccount, ''),
                    {created_at}
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
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        *,
        now: int | None = None,
    ) -> tuple[MemberSignup, ...]:
        """Return signups chronologically within account-priority groups."""
        current_time = int(time.time()) if now is None else now
        rows = await self.database.fetch_all(
            """
            WITH Prioritized AS (
                SELECT signup.Member,
                    signup.GameAccount,
                    signup.CreatedAt,
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM HsQsBases report
                            WHERE report.Guild=signup.Guild
                                AND report.Channel=signup.Channel
                                AND report.ReportKey=CASE
                                    WHEN signup.GameAccount=''
                                        THEN 'member:' || signup.Member
                                    ELSE 'account:' || signup.GameAccount
                                END COLLATE NOCASE
                                AND report.Phase < signup.Phase
                        ) THEN 999
                        ELSE (
                            SELECT COUNT(*)
                            FROM HsQsMembers account_signup
                            JOIN HsQsPhases phase
                                ON phase.Guild=account_signup.Guild
                                AND phase.Channel=account_signup.Channel
                                AND phase.Phase=account_signup.Phase
                            WHERE account_signup.Guild=signup.Guild
                                AND account_signup.Channel=signup.Channel
                                AND (
                                    (
                                        signup.GameAccount<>''
                                        AND account_signup.GameAccount=signup.GameAccount
                                            COLLATE NOCASE
                                    )
                                    OR (
                                        signup.GameAccount=''
                                        AND account_signup.GameAccount=''
                                        AND account_signup.Member=signup.Member
                                    )
                                )
                                AND (
                                    account_signup.Phase=?
                                    OR phase.StartsAt + phase.DurationHours * 3600 > ?
                                )
                        )
                    END AS Priority
                FROM HsQsMembers signup
                WHERE signup.Guild=? AND signup.Channel=? AND signup.Phase=?
            )
            SELECT Member, GameAccount,
                EXISTS (
                    SELECT 1
                    FROM HsQsBases report
                    WHERE report.Guild=?
                        AND report.Channel=?
                        AND report.ReportKey=CASE
                            WHEN GameAccount=''
                                THEN 'member:' || Member
                            ELSE 'account:' || GameAccount
                        END COLLATE NOCASE
                ) AS BaseDestroyed
            FROM Prioritized
            ORDER BY Priority, CreatedAt, Member, GameAccount COLLATE NOCASE
            """,
            (
                phase_index,
                current_time,
                guild_id,
                channel_id,
                phase_index,
                guild_id,
                channel_id,
            ),
        )
        return tuple(
            MemberSignup(
                row["Member"],
                row["GameAccount"] or None,
                bool(row["BaseDestroyed"]),
            )
            for row in rows
        )

    async def phases_for_signup(
        self,
        guild_id: int,
        channel_id: int,
        member_id: int,
        game_account: str | None,
    ) -> tuple[int, ...]:
        """Return every phase that contains the same in-game account identity."""
        account_key = game_account or ""
        rows = await self.database.fetch_all(
            """
            SELECT Phase
            FROM HsQsMembers
            WHERE Guild=? AND Channel=?
                AND (
                    (?<>'' AND GameAccount=? COLLATE NOCASE)
                    OR (?='' AND GameAccount='' AND Member=?)
                )
            ORDER BY Phase
            """,
            (
                guild_id,
                channel_id,
                account_key,
                account_key,
                account_key,
                member_id,
            ),
        )
        return tuple(row["Phase"] for row in rows)

    async def toggle(
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        member_id: int,
        game_account: str | None = None,
        *,
        created_at: int | None = None,
    ) -> bool:
        """Atomically toggle one account's signup and return the new joined state."""
        account_key = game_account or ""
        signup_time = time.time_ns() if created_at is None else created_at
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
                "(Guild, Channel, Phase, Member, GameAccount, CreatedAt) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            )
            await connection.execute(
                query,
                (
                    (guild_id, channel_id, phase_index, member_id, account_key)
                    if joined
                    else (
                        guild_id,
                        channel_id,
                        phase_index,
                        member_id,
                        account_key,
                        signup_time,
                    )
                ),
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
        *,
        created_at: int | None = None,
    ) -> bool:
        """Add one account signup without toggling off or replacing other accounts."""
        return await self.database.execute(
            """
            INSERT INTO HsQsMembers
                (Guild, Channel, Phase, Member, GameAccount, CreatedAt)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (Guild, Channel, Phase, Member, GameAccount) DO NOTHING
            """,
            (
                guild_id,
                channel_id,
                phase_index,
                member_id,
                game_account or "",
                time.time_ns() if created_at is None else created_at,
            ),
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
