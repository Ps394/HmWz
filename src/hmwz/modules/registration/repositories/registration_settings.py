"""Persistence for registration channel configuration."""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class RegistrationSettingsRepository(sqlite_db.Base):
    """Store registration channel settings for each guild."""

    table_name = "Registration_Settings"

    def __init__(self, database: sqlite_db.Database):
        super().__init__(database)

    @dataclass(frozen=True)
    class TableCols:
        """Column names used by the registration settings table."""

        Guild: str = "Guild"
        Channel: str = "Channel"
        Message: str = "Message"
        Title: str = "Title"
        Description: str = "Description"
        ShowLockEmojis: str = "ShowLockEmojis"

    @property
    def table(self) -> str:
        """Return the SQL statement that creates the settings table."""
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER NOT NULL,
            {self.TableCols.Channel} INTEGER,
            {self.TableCols.Message} INTEGER,
            {self.TableCols.Title} TEXT,
            {self.TableCols.Description} TEXT,
            {self.TableCols.ShowLockEmojis} INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY ({self.TableCols.Guild}, {self.TableCols.Channel}),
            FOREIGN KEY ({self.TableCols.Guild}) REFERENCES Servers(Guild)
        )
        """

    async def migrate_schema(self) -> bool:
        """Migrate legacy registration settings to channel-scoped records."""
        if not await self._migrate_channel_key():
            return False
        if not await self._migrate_show_lock_emojis():
            return False
        return await self.drop_columns(("GuildName", "ChannelName"))

    async def _migrate_channel_key(self) -> bool:
        """Rebuild the legacy guild-only table with one row per registration channel."""
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                cursor = await connection.execute(
                    f'PRAGMA table_info("{self.table_name}")'
                )
                columns = await cursor.fetchall()
                channel_column = next(
                    (column for column in columns if column["name"] == "Channel"), None
                )
                guild_column = next(
                    (column for column in columns if column["name"] == "Guild"), None
                )
                if (
                    channel_column is not None
                    and channel_column["pk"] > 0
                    and guild_column is not None
                    and guild_column["pk"] > 0
                ):
                    await connection.commit()
                    return True

                copy_columns = "Guild, Channel, Message, Title, Description"
                copy_show_lock_emojis = (
                    "ShowLockEmojis"
                    if any(column["name"] == "ShowLockEmojis" for column in columns)
                    else "1"
                )
                await connection.execute(
                    f'ALTER TABLE "{self.table_name}" RENAME TO "{self.table_name}_legacy"'
                )
                await connection.execute(self.table)
                await connection.execute(
                    f"""
                    INSERT OR IGNORE INTO "{self.table_name}"
                        ({copy_columns}, ShowLockEmojis)
                    SELECT {copy_columns}, {copy_show_lock_emojis}
                    FROM "{self.table_name}_legacy"
                    """
                )
                await connection.execute(f'DROP TABLE "{self.table_name}_legacy"')
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "%s Failed to migrate WZ registration settings to channel keys.",
                self.log_prefix(),
            )
            return False

    async def _migrate_show_lock_emojis(self) -> bool:
        """Add the optional lock-emoji display setting to existing tables."""
        try:
            async with self.database.connect() as connection:
                cursor = await connection.execute(
                    f'PRAGMA table_info("{self.table_name}")'
                )
                columns = await cursor.fetchall()
                if any(column["name"] == "ShowLockEmojis" for column in columns):
                    return True
                await connection.execute(
                    f"""
                    ALTER TABLE "{self.table_name}"
                    ADD COLUMN ShowLockEmojis INTEGER NOT NULL DEFAULT 1
                    """
                )
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "%s Failed to add the lock-emoji display setting.",
                self.log_prefix(),
            )
            return False

    @dataclass(frozen=True)
    class _Data:
        guild_id: int
        channel: int | None
        message: int | None
        title: str | None
        description: str | None
        show_lock_emojis: bool

        @property
        def has_channel(self) -> bool:
            """Whether this record has a channel assigned."""
            return self.channel is not None

        @property
        def has_message(self) -> bool:
            """Whether this record has a message assigned."""
            return self.message is not None

        @property
        def has_title(self) -> bool:
            """Whether this record has a non-empty title."""
            return self.title is not None and self.title != ""

        @property
        def has_description(self) -> bool:
            """Whether this record has a non-empty description."""
            return self.description is not None and self.description != ""

    type Record = _Data | None
    type Records = tuple[_Data, ...] | None

    @staticmethod
    def _record(guild_id: int, record: typing.Any) -> _Data:
        return RegistrationSettingsRepository._Data(
            guild_id=guild_id,
            channel=record["Channel"],
            message=record["Message"],
            title=record["Title"],
            description=record["Description"],
            show_lock_emojis=bool(record["ShowLockEmojis"]),
        )

    async def get_all(self, *, guild: discord.Guild) -> Records:
        """Return every configured WZ registration for a guild."""
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT Channel, Message, Title, Description, ShowLockEmojis
                FROM {self.table_name}
                WHERE Guild = ?
                ORDER BY Channel
                """,
                (guild.id,),
            )
            return tuple(self._record(guild.id, row) for row in rows) or None
        except Exception:
            _logger.exception(
                "%s Failed to list WZ registrations.", self.log_prefix(guild)
            )
            return None

    async def get(
        self, *, guild: discord.Guild, channel_id: int | None = None
    ) -> Record:
        """Retrieve one registration configuration for a guild.

        Args:
            guild: Guild whose configuration should be retrieved.
            channel_id: Optional registration channel identifier.

        Returns:
            The matching record, or ``None`` if unavailable.
        """
        try:
            query = f"""
            SELECT
                {self.TableCols.Channel},
                {self.TableCols.Message},
                {self.TableCols.Title},
                {self.TableCols.Description},
                {self.TableCols.ShowLockEmojis}
            FROM
                {self.table_name}
            WHERE
                {self.TableCols.Guild} = ?
            """
            params: tuple[int, ...] = (guild.id,)
            if channel_id is not None:
                query += f" AND {self.TableCols.Channel} = ?"
                params += (channel_id,)
            records = await self.database.fetch_all(query, params)
            if len(records) > 1:
                raise ValueError(
                    "A channel ID is required when a guild has multiple WZ registrations."
                )
            record = records[0] if records else None
            if not record:
                return None

            return self._record(guild.id, record)
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to get WZ registration: {e}"
            )
            return None

    async def upsert(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        message_id: int | None = None,
        title: str | None = None,
        description: str | None = None,
        show_lock_emojis: bool | None = None,
    ) -> bool:
        """Insert or update registration settings for a channel.

        Args:
            guild: Guild that owns the configuration.
            channel_id: Registration channel identifier.
            message_id: Optional overview message identifier.
            title: Optional overview title.
            description: Optional overview description.
            show_lock_emojis: Whether lock emojis should appear in registration lists.

        Returns:
            Whether the database write succeeded.
        """
        try:
            cols = [self.TableCols.Channel]
            vals: list[typing.Any] = [channel_id]
            if message_id is not None:
                cols.append(self.TableCols.Message)
                vals.append(message_id)
            if title is not None:
                cols.append(self.TableCols.Title)
                vals.append(title)
            if description is not None:
                cols.append(self.TableCols.Description)
                vals.append(description)
            if show_lock_emojis is not None:
                cols.append(self.TableCols.ShowLockEmojis)
                vals.append(show_lock_emojis)

            if not cols:
                return False

            columns = f"{self.TableCols.Guild}, " + ", ".join(cols)
            placeholders = ", ".join(["?"] * (1 + len(cols)))
            update_clause = ", ".join([f"{c}=excluded.{c}" for c in cols])

            query = f"""
                INSERT INTO {self.table_name} ({columns})
                VALUES ({placeholders})
                ON CONFLICT({self.TableCols.Guild}, {self.TableCols.Channel})
                DO UPDATE SET {update_clause}
            """

            params = [guild.id] + vals
            if not await self.database.execute(query, tuple(params)):
                return False
            _logger.debug(
                "%s Registration upserted for channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return True
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to upsert WZ registration "
                f"for channel {channel_id}: {e}"
            )
            return False

    async def create(self, *, guild: discord.Guild, channel_id: int) -> bool:
        """Create a registration only if the guild/channel pair is unused."""
        try:
            async with self.database.connect() as connection:
                async with connection.execute(
                    f"""
                    INSERT INTO {self.table_name}
                        ({self.TableCols.Guild}, {self.TableCols.Channel})
                    VALUES (?, ?)
                    ON CONFLICT({self.TableCols.Guild}, {self.TableCols.Channel})
                    DO NOTHING
                    RETURNING {self.TableCols.Channel}
                    """,
                    (guild.id, channel_id),
                ) as cursor:
                    created = await cursor.fetchone() is not None
                await connection.commit()
            if created:
                _logger.debug(
                    "%s Created registration for channel %s.",
                    self.log_prefix(guild),
                    channel_id,
                )
            return created
        except Exception:
            _logger.exception(
                "%s Failed to create registration for channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def remove(
        self, *, guild: discord.Guild, channel_id: int | None = None
    ) -> bool:
        """Remove one channel configuration or all configurations for a guild."""
        try:
            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: tuple[int, ...] = (guild.id,)
            if channel_id is not None:
                query += f" AND {self.TableCols.Channel} = ?"
                params += (channel_id,)
            executed = await self.database.execute(query, params)
            if executed:
                _logger.debug(
                    f"{self.log_prefix(guild)} Removed WZ registration records."
                )
            return executed
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to remove WZ registration records: {e}"
            )
            return False

    async def clear_message(self, *, guild: discord.Guild, channel_id: int) -> bool:
        """Clear the overview-message reference for one registration channel."""
        try:
            return await self.database.execute(
                f"""
                UPDATE {self.table_name}
                SET {self.TableCols.Message} = NULL
                WHERE {self.TableCols.Guild} = ?
                  AND {self.TableCols.Channel} = ?
                """,
                (guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to clear the registration message for channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False
