from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class MemberGameAccountRepository(sqlite_db.Base):
    """Stores game accounts linked to Discord members in each guild."""

    table_name = "WzGameAccounts"

    def __init__(self, database: sqlite_db.Database) -> None:
        super().__init__(database)

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            Guild INTEGER NOT NULL,
            Member INTEGER NOT NULL,
            Account TEXT COLLATE NOCASE NOT NULL,
            PRIMARY KEY (Guild, Member, Account),
            UNIQUE (Guild, Account)
        ) WITHOUT ROWID
        """

    @dataclass(frozen=True, slots=True)
    class _Data:
        guild_id: int
        member: int
        account: str

    type Records = tuple[_Data, ...] | None

    async def add(self, *, guild: discord.Guild, member: int, account: str) -> bool:
        account = account.strip()
        if not account:
            return False
        try:
            executed = await self.database.execute(
                f"""
                INSERT INTO {self.table_name} (Guild, Member, Account)
                VALUES (?, ?, ?)
                """,
                (guild.id, member, account),
            )
            if executed:
                _logger.info(
                    "%s Added game account %r for member %s.",
                    self.log_prefix(guild),
                    account,
                    member,
                )
            return executed
        except Exception:
            _logger.exception(
                "%s Failed to add game account %r for member %s.",
                self.log_prefix(guild),
                account,
                member,
            )
            return False

    async def get(
        self,
        *,
        guild: discord.Guild,
        member: int | None = None,
        account: str | None = None,
    ) -> Records:
        try:
            query = (
                f"SELECT Guild, Member, Account FROM {self.table_name} WHERE Guild = ?"
            )
            params: list[int | str] = [guild.id]
            if member is not None:
                query += " AND Member = ?"
                params.append(member)
            if account is not None:
                query += " AND Account = ? COLLATE NOCASE"
                params.append(account)
            query += " ORDER BY Account COLLATE NOCASE"
            rows = await self.database.fetch_all(query, tuple(params))
            if not rows:
                return None
            return tuple(
                self._Data(
                    guild_id=row["Guild"],
                    member=row["Member"],
                    account=row["Account"],
                )
                for row in rows
            )
        except Exception:
            _logger.exception(
                "%s Failed to get game accounts for member %s.",
                self.log_prefix(guild),
                member,
            )
            return None

    async def remove(self, *, guild: discord.Guild, member: int, account: str) -> bool:
        try:
            removed = await self.database.execute(
                f"""
                DELETE FROM {self.table_name}
                WHERE Guild = ? AND Member = ? AND Account = ? COLLATE NOCASE
                """,
                (guild.id, member, account),
            )
            if removed:
                _logger.info(
                    "%s Removed game account %r for member %s.",
                    self.log_prefix(guild),
                    account,
                    member,
                )
            return removed
        except Exception:
            _logger.exception(
                "%s Failed to remove game account %r for member %s.",
                self.log_prefix(guild),
                account,
                member,
            )
            return False

    async def remove_member(self, *, guild: discord.Guild, member: int) -> bool:
        """Remove every linked game account for a member."""
        try:
            return await self.database.execute(
                f"DELETE FROM {self.table_name} WHERE Guild = ? AND Member = ?",
                (guild.id, member),
            )
        except Exception:
            _logger.exception(
                "%s Failed to remove game accounts for member %s.",
                self.log_prefix(guild),
                member,
            )
            return False

    async def remove_guild(self, *, guild: discord.Guild) -> bool:
        """Remove every linked game account for a guild."""
        try:
            return await self.database.execute(
                f"DELETE FROM {self.table_name} WHERE Guild = ?",
                (guild.id,),
            )
        except Exception:
            _logger.exception(
                "%s Failed to remove all game accounts.", self.log_prefix(guild)
            )
            return False
