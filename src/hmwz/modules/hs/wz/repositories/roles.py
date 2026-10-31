"""Persistence for WZ roles, separate from registration roles."""

from __future__ import annotations

import logging
import sqlite3

import discord

from hmwz import sqlite_db

from ..models import Role

_logger = logging.getLogger(__name__)


class RoleRepository(sqlite_db.Base):
    """Store WZ roles per guild without accessing registration data."""

    table_name = "HsWzRoles"

    @property
    def table(self) -> str:
        """Return the schema for guild-scoped WZ roles."""
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            Guild INTEGER NOT NULL,
            Role INTEGER NOT NULL,
            PRIMARY KEY (Guild, Role),
            FOREIGN KEY (Guild) REFERENCES Servers(Guild)
        ) WITHOUT ROWID
        """

    async def migrate_schema(self) -> bool:
        """Remove obsolete permanence metadata while preserving role settings."""
        if not await self.database.execute(self.table):
            return False
        return await self.drop_columns(("Permanent",))

    async def get(self, *, guild: discord.Guild) -> tuple[Role, ...] | None:
        """Return the guild's configured WZ roles."""
        rows = await self.database.fetch_all(
            f"SELECT Role FROM {self.table_name} WHERE Guild = ? ORDER BY Role",
            (guild.id,),
        )
        return (
            tuple(
                Role(
                    guild_id=guild.id,
                    role=row["Role"],
                )
                for row in rows
            )
            or None
        )

    async def add(self, *, guild: discord.Guild, role: int) -> bool:
        """Add a role without exceeding the guild's atomic 25-role limit."""
        if not await self.database.execute(
            f"""
            INSERT OR IGNORE INTO {self.table_name} (Guild, Role)
            SELECT ?, ?
            WHERE (SELECT COUNT(*) FROM {self.table_name} WHERE Guild = ?) < ?
            """,
            (guild.id, role, guild.id, Role.MAX_PER_GUILD),
        ):
            return False
        row = await self.database.fetch_one(
            f"SELECT 1 FROM {self.table_name} WHERE Guild = ? AND Role = ?",
            (guild.id, role),
        )
        if row is None:
            _logger.warning(
                "%s Cannot add WZ role %s: guild limit reached.",
                self.log_prefix(guild),
                role,
            )
            return False
        return True

    async def remove(
        self,
        *,
        guild: discord.Guild,
        role: int | None = None,
        roles: list[int] | None = None,
    ) -> bool:
        """Remove selected WZ roles, or all WZ roles for a leaving guild."""
        if role is not None and roles is not None:
            raise ValueError("Specify either role or roles, not both.")
        if roles == []:
            return True
        selected = [role] if role is not None else roles
        query = f"DELETE FROM {self.table_name} WHERE Guild = ?"
        params: tuple[int, ...] = (guild.id,)
        if selected is not None:
            query += f" AND Role IN ({', '.join('?' for _ in selected)})"
            params += tuple(selected)
        try:
            return await self.database.execute(query, params)
        except sqlite3.Error:
            _logger.exception("%s Failed to remove WZ roles.", self.log_prefix(guild))
            return False
