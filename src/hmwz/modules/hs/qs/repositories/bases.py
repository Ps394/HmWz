"""Persistence for unique Qs destroyed-base reports."""

from hmwz.sqlite_db import Base

from ..models import BASE_TOTAL, BaseReport


class BaseLimitReached(ValueError):
    """The event already has reports for all forty destroyed bases."""


class DuplicateBaseReport(ValueError):
    """The in-game account has already reported a destroyed base for this event."""


class InvalidGameAccount(ValueError):
    """The selected in-game account is not linked to the reporting member."""


class BaseReportRepository(Base):
    """Enforce one destroyed-base report per account or display-name identity."""

    table_name = "HsQsBases"

    @property
    def table(self) -> str:
        """Return the account-based destroyed-base report schema."""
        return """
            CREATE TABLE IF NOT EXISTS HsQsBases (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Phase INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                ReportKey TEXT COLLATE NOCASE NOT NULL,
                Account TEXT COLLATE NOCASE,
                DisplayName TEXT NOT NULL,
                CreatedAt INTEGER NOT NULL,
                PRIMARY KEY (Guild, Channel, ReportKey),
                FOREIGN KEY (Guild, Channel, Phase)
                    REFERENCES HsQsPhases (Guild, Channel, Phase) ON DELETE CASCADE
            ) WITHOUT ROWID
            """

    async def migrate_schema(self) -> None:
        """Preserve existing reports while adding separate account/display identities."""
        async with self.database.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            async with connection.execute("PRAGMA table_info(HsQsBases)") as cursor:
                rows = await cursor.fetchall()
            columns = {row["name"] for row in rows}
            primary_key = tuple(
                row["name"]
                for row in sorted(rows, key=lambda row: row["pk"])
                if row["pk"]
            )
            if (
                "ReportKey" not in columns
                or "ReportKey" not in primary_key
                or "Base" in columns
            ):
                await connection.execute(
                    "ALTER TABLE HsQsBases RENAME TO HsQsBasesLegacy"
                )
                await connection.execute(self.table)
                if "Account" in columns:
                    account = (
                        "CASE WHEN Account LIKE 'legacy:%' THEN NULL ELSE Account END"
                    )
                    report_key = (
                        "CASE WHEN Account LIKE 'legacy:%' "
                        "THEN 'member:' || Member ELSE 'account:' || Account END"
                    )
                else:
                    account = "NULL"
                    report_key = "'member:' || Member"
                display_name = "DisplayName" if "DisplayName" in columns else "''"
                await connection.execute(
                    "INSERT INTO HsQsBases "
                    "(Guild, Channel, Phase, Member, ReportKey, Account, DisplayName, CreatedAt) "
                    f"SELECT Guild, Channel, Phase, Member, {report_key}, {account}, "
                    f"{display_name}, CreatedAt "
                    "FROM HsQsBasesLegacy"
                )
                await connection.execute("DROP TABLE HsQsBasesLegacy")
            await connection.commit()

    async def get(self, guild_id: int, channel_id: int) -> tuple[BaseReport, ...]:
        """Return reports in submission order."""
        rows = await self.database.fetch_all(
            "SELECT * FROM HsQsBases WHERE Guild=? AND Channel=? "
            "ORDER BY CreatedAt, Member, ReportKey",
            (guild_id, channel_id),
        )
        return tuple(
            BaseReport(
                member_id=row["Member"],
                phase_index=row["Phase"],
                display_name=row["DisplayName"],
                created_at=row["CreatedAt"],
                game_account=row["Account"],
                report_key=row["ReportKey"],
            )
            for row in rows
        )

    async def add(
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        member_id: int,
        game_account: str | None,
        display_name: str,
        created_at: int,
    ) -> None:
        """Save an account or display-name report once with ownership and limit checks."""
        limit_reached = False
        duplicate_report = False
        invalid_account = False
        report_key = (
            f"member:{member_id}" if game_account is None else f"account:{game_account}"
        )
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
                if game_account is not None:
                    async with connection.execute(
                        "SELECT 1 FROM GameAccounts "
                        "WHERE Guild=? AND Member=? AND Account=? COLLATE NOCASE",
                        (guild_id, member_id, game_account),
                    ) as cursor:
                        invalid_account = await cursor.fetchone() is None
                if not invalid_account:
                    async with connection.execute(
                        "SELECT 1 FROM HsQsBases WHERE Guild=? AND Channel=? "
                        "AND ReportKey=? COLLATE NOCASE",
                        (guild_id, channel_id, report_key),
                    ) as cursor:
                        duplicate_report = await cursor.fetchone() is not None
                if not duplicate_report and not invalid_account:
                    await connection.execute(
                        "INSERT INTO HsQsBases "
                        "(Guild, Channel, Phase, Member, ReportKey, Account, DisplayName, CreatedAt) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            guild_id,
                            channel_id,
                            phase_index,
                            member_id,
                            report_key,
                            game_account,
                            display_name,
                            created_at,
                        ),
                    )
            await connection.commit()
        if limit_reached:
            raise BaseLimitReached("All forty bases have already been reported.")
        if duplicate_report:
            raise DuplicateBaseReport("This identity has already reported a base.")
        if invalid_account:
            raise InvalidGameAccount("The account is not linked to this member.")

    async def withdraw(
        self,
        guild_id: int,
        channel_id: int,
        phase_index: int,
        member_id: int,
        game_account: str | None,
    ) -> bool:
        """Delete exactly one account or display-name report in the specified phase."""
        report_key = (
            f"member:{member_id}" if game_account is None else f"account:{game_account}"
        )
        async with self.database.connect() as connection:
            async with connection.execute(
                "DELETE FROM HsQsBases "
                "WHERE Guild=? AND Channel=? AND Phase=? AND Member=? "
                "AND ReportKey=? COLLATE NOCASE",
                (guild_id, channel_id, phase_index, member_id, report_key),
            ) as cursor:
                removed = cursor.rowcount == 1
            await connection.commit()
            return removed
