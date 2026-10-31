"""Asynchronous SQLite access and shared repository helpers."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import ClassVar, Sequence, cast

import aiosqlite
from discord import Guild

_logger = logging.getLogger(__name__)


class Base:
    """
    Base class for repositories with shared database and logging helpers.

    Subclasses define ``table_name`` and implement the ``table`` property.

    Args:
        database: Database used by the repository.
    """

    table_name: ClassVar[str]

    def __init__(self, database: Database):
        """Initialize the repository with its database.

        Args:
            database: Database used for repository operations.
        """
        self.database: Database = database

    @classmethod
    def log_prefix(cls, guild: Guild | None = None) -> str:
        """
        Format a guild name and ID prefix for log messages.

        Args:
            guild: Optional guild to include in the prefix.

        Returns:
            The formatted prefix, or an empty string when no guild is provided.
        """
        if guild:
            return f"{guild.name} ({guild.id}) - "
        return ""

    @property
    def table(self) -> str:
        """Return the SQL statement that creates this repository's table.

        Raises:
            NotImplementedError: Subclasses must provide their table definition.
        """
        raise NotImplementedError('Subclasses must implement the "table" property.')

    async def count_all(self) -> int:
        """Return the number of records in this repository's table.

        Returns:
            The record count, or zero if the query fails.
        """
        try:
            query = f"SELECT COUNT(*) FROM {self.table_name}"
            row = await self.database.fetch_one(query)
            _logger.info(
                f"{self.log_prefix()}Counted entries in {self.table_name} table."
            )
            return row[0] if row else 0
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix()}Failed to count entries in {self.table_name} table: {e}"
            )
            return 0

    async def member_log_name(self, guild: Guild, member_id: int) -> str:
        """Return a known Discord username and display name for a member log."""
        names = await self.member_names(guild, member_id)
        if names is not None:
            return f"{names[0]} / {names[1]} ({member_id})"
        return f"unknown member ({member_id})"

    async def member_names(
        self, guild: Guild, member_id: int
    ) -> tuple[str, str] | None:
        """Return the known username and display name for a guild member."""
        member = guild.get_member(member_id)
        if member is not None:
            return member.name, member.display_name
        return None

    async def channel_log_name(self, guild: Guild, channel_id: int) -> str:
        """Return a known Discord channel name for a channel log."""
        name = await self.channel_name(guild, channel_id)
        if name is not None:
            return f"{name} ({channel_id})"
        return f"unknown channel ({channel_id})"

    async def channel_name(self, guild: Guild, channel_id: int) -> str | None:
        """Return the known name for a guild channel."""
        channel = guild.get_channel_or_thread(channel_id)
        return channel.name if channel is not None else None

    async def role_log_name(self, guild: Guild, role_id: int) -> str:
        """Return a known Discord role name for a role log."""
        name = await self.role_name(guild, role_id)
        if name is not None:
            return f"{name} ({role_id})"
        return f"unknown role ({role_id})"

    async def role_name(self, guild: Guild, role_id: int) -> str | None:
        """Return the known name for a guild role."""
        role = guild.get_role(role_id)
        return role.name if role is not None else None

    async def ensure_columns(self, columns: tuple[tuple[str, str], ...]) -> bool:
        """Add missing columns to this repository's existing table."""
        rows = await self.database.fetch_all(f'PRAGMA table_info("{self.table_name}")')
        existing = {row["name"] for row in rows}
        for column_name, column_type in columns:
            if column_name not in existing and not await self.database.execute(
                f'ALTER TABLE "{self.table_name}" '
                f'ADD COLUMN "{column_name}" {column_type}'
            ):
                return False
        return True

    async def drop_columns(self, columns: tuple[str, ...]) -> bool:
        """Remove obsolete columns from this repository's existing table."""
        rows = await self.database.fetch_all(f'PRAGMA table_info("{self.table_name}")')
        existing = {row["name"] for row in rows}
        for column_name in columns:
            if column_name in existing and not await self.database.execute(
                f'ALTER TABLE "{self.table_name}" DROP COLUMN "{column_name}"'
            ):
                return False
        return True


class Database:
    """Manage asynchronous SQLite connections and database operations."""

    _busy_timeout_ms = 5000
    _write_retry_attempts = 5
    _write_retry_delay = 0.2

    def __init__(self, *, folder: str = "data", filename: str = "data.db") -> None:
        """
        Configure the database file and create its parent directory.

        Args:
            folder: Directory containing the database file.
            filename: Database file name.
        """
        os.makedirs(folder, exist_ok=True)
        self.file = os.path.join(folder, filename)
        _logger = logging.getLogger(__name__)
        self._write_lock = asyncio.Lock()

    async def remove_legacy_tables(self) -> bool:
        """Drop obsolete Discord entity and registration tables."""
        for table_name in (
            "DiscordMembers",
            "DiscordChannels",
            "DiscordRoles",
            "QsList",
            "QsRegistration",
            "QsRegistrations",
            "QsRoles",
            "WzConfiguration",
            "Configuration",
            "WzConfig",
        ):
            table = await self.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            )
            if table is not None and not await self.execute(
                f'DROP TABLE "{table_name}"'
            ):
                return False
        return True

    @asynccontextmanager
    async def connect(self):
        """
        Open a configured SQLite connection and close it when the context exits.

        Yields:
            An open ``aiosqlite.Connection``.

        Raises:
            Exception: Re-raises connection or setup failures after logging them.
        """
        database = None
        try:
            database = await aiosqlite.connect(
                self.file, timeout=self._busy_timeout_ms / 1000
            )
            await database.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms};")
            await database.execute("PRAGMA foreign_keys = ON;")
            await database.execute("PRAGMA journal_mode = WAL;")
            await database.execute("PRAGMA synchronous = NORMAL;")
            database.row_factory = aiosqlite.Row
            yield database
        except Exception as e:
            _logger.exception(f"Database connection error: {e}")
            raise
        finally:
            if database:
                await database.close()

    async def execute(self, query: str, params: tuple = ()) -> bool:
        """
        Execute a write query and commit the transaction.

        Args:
            query: SQL statement to execute.
            params: Positional parameters bound to the statement.

        Returns:
            Whether the write completed successfully.
        """
        async with self._write_lock:
            for attempt in range(self._write_retry_attempts + 1):
                try:
                    async with self.connect() as connection:
                        await connection.execute(query, params)
                        await connection.commit()
                        return True
                except aiosqlite.OperationalError as e:
                    msg = str(e).lower()
                    is_locked = "database is locked" in msg or "database is busy" in msg
                    if not is_locked or attempt == self._write_retry_attempts:
                        _logger.exception(f"Database write error: {e}")
                        return False
                    delay = self._write_retry_delay * (2**attempt)
                    _logger.warning(
                        "Database is locked, retrying in %.2f seconds (attempt %s/%s)",
                        delay,
                        attempt + 1,
                        self._write_retry_attempts,
                    )
                    await asyncio.sleep(delay)
        return False

    async def execute_many(self, query: str, params: Sequence[tuple]) -> bool:
        """Execute a batch of writes in one transaction.

        Args:
            query: SQL statement to execute for each parameter tuple.
            params: Parameter tuples bound to each execution.

        Returns:
            Whether the batch completed successfully.
        """
        async with self._write_lock:
            for attempt in range(self._write_retry_attempts + 1):
                try:
                    async with self.connect() as connection:
                        await connection.executemany(query, params)
                        await connection.commit()
                        return True
                except aiosqlite.OperationalError as e:
                    msg = str(e).lower()
                    is_locked = "database is locked" in msg or "database is busy" in msg
                    if not is_locked or attempt == self._write_retry_attempts:
                        _logger.exception(f"Database batch write error: {e}")
                        return False
                    delay = self._write_retry_delay * (2**attempt)
                    _logger.warning(
                        "Database is locked, retrying batch write in %.2f seconds "
                        "(attempt %s/%s)",
                        delay,
                        attempt + 1,
                        self._write_retry_attempts,
                    )
                    await asyncio.sleep(delay)
        return False

    async def fetch_all(
        self, query: str, params: tuple = ()
    ) -> tuple[aiosqlite.Row, ...]:
        """
        Execute a query and return all result rows.

        Args:
            query: SQL statement to execute.
            params: Positional parameters bound to the statement.

        Returns:
            Rows returned by the query.
        """
        async with (
            self.connect() as connection,
            connection.execute(query, params) as cursor,
        ):
            return cast(tuple[aiosqlite.Row, ...], await cursor.fetchall())

    async def fetch_one(self, query: str, params: tuple = ()) -> aiosqlite.Row | None:
        """
        Execute a query and return its first result row.

        Args:
            query: SQL statement to execute.
            params: Positional parameters bound to the statement.

        Returns:
            The first row, or ``None`` when the query returns no rows.
        """
        async with (
            self.connect() as connection,
            connection.execute(query, params) as cursor,
        ):
            return cast(aiosqlite.Row | None, await cursor.fetchone())
