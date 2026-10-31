from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

from ..models import channels

_logger = logging.getLogger(__name__)


class ChannelRepository(sqlite_db.Base):
    """Repository für zusätzliche Bereinigungskanäle je Guild."""

    table_name = "HsWzChannels"

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Channel: str = "Channel"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER NOT NULL,
            {self.TableCols.Channel} INTEGER NOT NULL,
            PRIMARY KEY (
                {self.TableCols.Guild}, {self.TableCols.Channel}
            ),
            FOREIGN KEY ({self.TableCols.Guild}) REFERENCES Servers(Guild)
        ) WITHOUT ROWID
        """

    async def migrate_schema(self) -> bool:
        """Migrate cleanup channels and remove cached names."""
        if not await self.database.execute(self.table):
            return False
        if not await self.drop_columns(("RegistrationChannel",)):
            return False
        if not await self._migrate_legacy_table():
            return False
        return await self.drop_columns(("GuildName", "ChannelName"))

    async def _migrate_legacy_table(self) -> bool:
        """Move existing channel settings from the former table atomically."""
        legacy_table_name = "WzPurgeChannels"
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                cursor = await connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (legacy_table_name,),
                )
                if await cursor.fetchone() is None:
                    await connection.commit()
                    return True
                await connection.execute(
                    f"""
                    INSERT INTO "{self.table_name}" (Guild, Channel)
                    SELECT legacy.Guild, legacy.Channel
                    FROM "{legacy_table_name}" AS legacy
                    WHERE NOT EXISTS (
                        SELECT 1 FROM "{self.table_name}" AS current
                        WHERE current.Guild = legacy.Guild
                          AND current.Channel = legacy.Channel
                    )
                    """
                )
                await connection.execute(f'DROP TABLE "{legacy_table_name}"')
                await connection.commit()
            return True
        except sqlite3.Error:
            _logger.exception(
                "%s Failed to migrate WZ channel settings from %s.",
                self.log_prefix(),
                legacy_table_name,
            )
            return False

    type Records = tuple[channels.Channel, ...] | None

    async def get(self, *, guild: discord.Guild) -> Records:
        try:
            query = f"""
                SELECT {self.TableCols.Channel}
                FROM {self.table_name}
                WHERE {self.TableCols.Guild} = ?
            """
            params: tuple[int, ...] = (guild.id,)
            query += f" ORDER BY {self.TableCols.Channel}"
            rows = await self.database.fetch_all(query, params)
            if not rows:
                return None
            return tuple(
                channels.Channel(
                    guild_id=guild.id, channel_id=row[self.TableCols.Channel]
                )
                for row in rows
            )
        except Exception:
            _logger.exception(
                "%s Failed to get WZ cleanup channels.", self.log_prefix(guild)
            )
            return None

    async def count(self, *, guild: discord.Guild) -> int:
        try:
            query = (
                f"SELECT COUNT(*) FROM {self.table_name} "
                f"WHERE {self.TableCols.Guild} = ?"
            )
            params: tuple[int, ...] = (guild.id,)
            row = await self.database.fetch_one(
                query,
                params,
            )
            return row[0] if row else 0
        except Exception:
            _logger.exception(
                "%s Failed to count WZ cleanup channels.", self.log_prefix(guild)
            )
            return 0

    async def add(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
    ) -> bool:
        channel_name = f"unknown channel ({channel_id})"
        try:
            resolved_channel_name = await self.channel_name(guild, channel_id)
            if resolved_channel_name is not None:
                channel_name = f"{resolved_channel_name} ({channel_id})"
            executed = await self.database.execute(
                f"""
                INSERT OR IGNORE INTO {self.table_name}
                    ({self.TableCols.Guild}, {self.TableCols.Channel})
                SELECT ?, ?
                WHERE (
                    SELECT COUNT(*) FROM {self.table_name}
                    WHERE {self.TableCols.Guild} = ?
                ) < ?
                """,
                (
                    guild.id,
                    channel_id,
                    guild.id,
                    channels.Channel.MAX_PER_GUILD,
                ),
            )
            if not executed:
                return False

            row = await self.database.fetch_one(
                f"""
                SELECT {self.TableCols.Channel} FROM {self.table_name}
                WHERE {self.TableCols.Guild} = ? AND {self.TableCols.Channel} = ?
                """,
                (guild.id, channel_id),
            )
            if row is None:
                _logger.warning(
                    "%s Cannot add cleanup channel %s: guild limit reached.",
                    self.log_prefix(guild),
                    channel_name,
                )
                return False

            _logger.debug(
                "%s Added WZ cleanup channel %s.", self.log_prefix(guild), channel_name
            )
            return True
        except Exception:
            _logger.exception(
                "%s Failed to add WZ cleanup channel %s.",
                self.log_prefix(guild),
                channel_name,
            )
            return False

    async def remove(
        self,
        *,
        guild: discord.Guild,
        channel_id: int | None = None,
    ) -> bool:
        target = (
            f"channel unknown ({channel_id})" if channel_id is not None else "channels"
        )
        try:
            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: tuple[int, ...] = (guild.id,)
            if channel_id is not None:
                query += f" AND {self.TableCols.Channel} = ?"
                params += (channel_id,)

            executed = await self.database.execute(query, params)
            if not executed:
                return False
            target = (
                f"channel {await self.channel_log_name(guild, channel_id)}"
                if channel_id is not None
                else "channels"
            )
            _logger.debug("%s Removed WZ cleanup %s.", self.log_prefix(guild), target)
            return True
        except Exception:
            _logger.exception(
                "%s Failed to remove WZ cleanup %s.", self.log_prefix(guild), target
            )
            return False
