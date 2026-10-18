from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

from ..models import PurgeChannel

_logger = logging.getLogger(__name__)


class PurgeChannelRepository(sqlite_db.Base):
    """Repository für zusätzliche Bereinigungskanäle je Guild."""

    table_name = "WzPurgeChannels"

    def __init__(self, database: sqlite_db.Database) -> None:
        super().__init__(database)

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Channel: str = "Channel"
        GuildName: str = "GuildName"
        ChannelName: str = "ChannelName"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER NOT NULL,
            {self.TableCols.Channel} INTEGER NOT NULL,
            {self.TableCols.GuildName} TEXT,
            {self.TableCols.ChannelName} TEXT,
            PRIMARY KEY ({self.TableCols.Guild}, {self.TableCols.Channel}),
            FOREIGN KEY ({self.TableCols.Guild}) REFERENCES Servers(Guild)
        ) WITHOUT ROWID
        """

    async def migrate_names(self) -> bool:
        """Add and populate readable names for existing purge-channel records."""
        if not await self.ensure_columns(
            ((self.TableCols.GuildName, "TEXT"), (self.TableCols.ChannelName, "TEXT"))
        ):
            return False
        return await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET {self.TableCols.GuildName} = COALESCE(
                    (SELECT Name FROM Servers WHERE Guild = {self.table_name}.Guild),
                    {self.TableCols.GuildName}
                ),
                {self.TableCols.ChannelName} = COALESCE(
                    (SELECT Name FROM DiscordChannels
                     WHERE Guild = {self.table_name}.Guild
                       AND Channel = {self.table_name}.Channel),
                    {self.TableCols.ChannelName}
                )
            """
        )

    type Records = tuple[PurgeChannel, ...] | None

    async def get(self, *, guild: discord.Guild) -> Records:
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT {self.TableCols.Channel}
                FROM {self.table_name}
                WHERE {self.TableCols.Guild} = ?
                ORDER BY {self.TableCols.Channel}
                """,
                (guild.id,),
            )
            if not rows:
                return None
            return tuple(
                PurgeChannel(guild_id=guild.id, channel_id=row[self.TableCols.Channel])
                for row in rows
            )
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to get WZ purge channels: {e}"
            )
            return None

    async def count(self, *, guild: discord.Guild) -> int:
        try:
            row = await self.database.fetch_one(
                f"SELECT COUNT(*) FROM {self.table_name} "
                f"WHERE {self.TableCols.Guild} = ?",
                (guild.id,),
            )
            return row[0] if row else 0
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to count WZ purge channels: {e}"
            )
            return 0

    async def add(self, *, guild: discord.Guild, channel_id: int) -> bool:
        channel_name = f"unknown channel ({channel_id})"
        try:
            resolved_channel_name = await self.channel_name(guild, channel_id)
            if resolved_channel_name is not None:
                channel_name = f"{resolved_channel_name} ({channel_id})"
            executed = await self.database.execute(
                f"""
                INSERT OR IGNORE INTO {self.table_name}
                    ({self.TableCols.Guild}, {self.TableCols.Channel},
                     {self.TableCols.GuildName}, {self.TableCols.ChannelName})
                SELECT ?, ?, ?, ?
                WHERE (
                    SELECT COUNT(*) FROM {self.table_name}
                    WHERE {self.TableCols.Guild} = ?
                ) < ?
                """,
                (
                    guild.id,
                    channel_id,
                    guild.name,
                    resolved_channel_name,
                    guild.id,
                    PurgeChannel.MAX_PER_GUILD,
                ),
            )
            if not executed:
                return False

            row = await self.database.fetch_one(
                f"""
                SELECT 1 FROM {self.table_name}
                WHERE {self.TableCols.Guild} = ? AND {self.TableCols.Channel} = ?
                """,
                (guild.id, channel_id),
            )
            if row is None:
                _logger.warning(
                    "%s Cannot add purge channel %s: guild limit reached.",
                    self.log_prefix(guild),
                    channel_name,
                )
                return False

            _logger.debug(
                f"{self.log_prefix(guild)} Added WZ purge channel {channel_name}."
            )
            return True
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to add WZ purge channel "
                f"{channel_name}: {e}"
            )
            return False

    async def remove(
        self, *, guild: discord.Guild, channel_id: int | None = None
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
            _logger.debug(f"{self.log_prefix(guild)} Removed WZ purge {target}.")
            return True
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to remove WZ purge {target}: {e}"
            )
            return False
