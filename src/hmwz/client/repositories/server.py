"""Persistence for Discord guild names."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db
from hmwz.utils.timezones import DEFAULT_GUILD_TIMEZONE, validate_iana_timezone


class ServerRepository(sqlite_db.Base):
    """
    Store Discord guilds in the database.

    The repository supports adding, updating, and removing guild records.
    """

    table_name = "Servers"

    def __init__(self, database: sqlite_db.Database):
        super().__init__(database)
        self.logger = logging.getLogger(__name__)

    @dataclass(frozen=True)
    class TableCols:
        """Column names used by the server table."""

        Guild: str = "Guild"
        Name: str = "Name"
        TimeZone: str = "TimeZone"

    @property
    def table(self) -> str:
        """
        Return the SQL statement that creates the server table.

        Returns:
            The table creation statement.
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER PRIMARY KEY,
            {self.TableCols.Name} TEXT,
            {self.TableCols.TimeZone} TEXT NOT NULL
                DEFAULT '{DEFAULT_GUILD_TIMEZONE}'
        ) WITHOUT ROWID
        """

    async def ensure_schema(self) -> bool:
        """Add the guild timezone column to databases created by older versions."""
        return await self.ensure_columns(
            (
                (
                    self.TableCols.TimeZone,
                    f"TEXT NOT NULL DEFAULT '{DEFAULT_GUILD_TIMEZONE}'",
                ),
            )
        )

    async def get_timezone(self, guild_id: int) -> str:
        """Return a guild's configured timezone or the shared default."""
        row = await self.database.fetch_one(
            f"SELECT {self.TableCols.TimeZone} FROM {self.table_name} "
            f"WHERE {self.TableCols.Guild} = ?",
            (guild_id,),
        )
        return (
            row[self.TableCols.TimeZone] if row is not None else DEFAULT_GUILD_TIMEZONE
        )

    async def set_timezone(self, guild: discord.Guild, timezone_name: str) -> bool:
        """Persist a validated IANA timezone for a guild."""
        timezone_name = validate_iana_timezone(timezone_name)
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.table_name}
                    ({self.TableCols.Guild}, {self.TableCols.Name}, {self.TableCols.TimeZone})
                VALUES (?, ?, ?)
                ON CONFLICT({self.TableCols.Guild}) DO UPDATE SET
                    {self.TableCols.Name} = excluded.{self.TableCols.Name},
                    {self.TableCols.TimeZone} = excluded.{self.TableCols.TimeZone}
                """,
                (guild.id, guild.name, timezone_name),
            )
        except Exception:
            self.logger.exception(
                "%s Failed to save guild timezone %s.",
                self.log_prefix(guild),
                timezone_name,
            )
            return False

    async def add(self, *, guild: discord.Guild) -> bool:
        """
        Insert a guild or update its stored name.

        Args:
            guild: The guild to insert or update.

        Returns:
            Whether the database operation succeeded.
        """
        try:
            query = f"""
                INSERT INTO {self.table_name} ({self.TableCols.Guild}, {self.TableCols.Name}) 
                VALUES (?, ?) 
                ON CONFLICT({self.TableCols.Guild}) DO UPDATE SET {self.TableCols.Name} = excluded.{self.TableCols.Name}
            """
            if not await self.database.execute(query, (guild.id, guild.name)):
                return False
            self.logger.debug(f"{self.log_prefix(guild)} Added/Updated server.")
            return True
        except Exception as e:
            self.logger.exception(
                f"{self.log_prefix(guild)} Failed to add/update server: {e}"
            )
            return False

    async def migrate_legacy_servers(self) -> bool:
        """Copy rows from the legacy singular ``Server`` table, if it exists.

        Returns:
            Whether the migration completed successfully.
        """
        try:
            legacy_table = await self.database.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("Server",),
            )
            if legacy_table is None:
                return True

            copied = await self.database.execute(
                f"""
                INSERT OR IGNORE INTO {self.table_name} ({self.TableCols.Guild}, {self.TableCols.Name})
                SELECT {self.TableCols.Guild}, {self.TableCols.Name}
                FROM Server
                """
            )
            if not copied:
                return False
            return await self.database.execute("DROP TABLE Server")
        except Exception as e:
            self.logger.exception(f"Failed to migrate legacy server rows: {e}")
            return False

    async def remove(self, *, guild: discord.Guild) -> bool:
        """
        Remove a guild from the database.

        Args:
            guild: The guild to remove.

        Returns:
            Whether the database operation succeeded.
        """
        try:
            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            return await self.database.execute(query, (guild.id,))
        except Exception as e:
            self.logger.exception(
                f"{self.log_prefix(guild)} Failed to remove server: {e}"
            )
            return False
