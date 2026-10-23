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
        RegistrationChannel: str = "RegistrationChannel"
        Channel: str = "Channel"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER NOT NULL,
            {self.TableCols.RegistrationChannel} INTEGER NOT NULL DEFAULT 0,
            {self.TableCols.Channel} INTEGER NOT NULL,
            PRIMARY KEY (
                {self.TableCols.Guild}, {self.TableCols.Channel}
            ),
            FOREIGN KEY ({self.TableCols.Guild}) REFERENCES Servers(Guild)
        ) WITHOUT ROWID
        """

    async def migrate_schema(self) -> bool:
        """Add registration scope to legacy purge channels and remove cached names."""
        if not await self.ensure_columns(
            ((self.TableCols.RegistrationChannel, "INTEGER NOT NULL DEFAULT 0"),)
        ):
            return False
        if not await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET {self.TableCols.RegistrationChannel} = COALESCE(
                (SELECT Channel FROM Registration_Settings
                 WHERE Guild = {self.table_name}.Guild
                 ORDER BY Channel LIMIT 1),
                0
            )
            WHERE {self.TableCols.RegistrationChannel} = 0
            """
        ):
            return False
        return await self.drop_columns(("GuildName", "ChannelName"))

    type Records = tuple[PurgeChannel, ...] | None

    async def get(
        self, *, guild: discord.Guild, registration_channel_id: int | None = None
    ) -> Records:
        try:
            query = f"""
                SELECT {self.TableCols.Channel}
                FROM {self.table_name}
                WHERE {self.TableCols.Guild} = ?
            """
            params: tuple[int, ...] = (guild.id,)
            if registration_channel_id is not None:
                query += f" AND {self.TableCols.RegistrationChannel} = ?"
                params += (registration_channel_id,)
            query += f" ORDER BY {self.TableCols.Channel}"
            rows = await self.database.fetch_all(query, params)
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

    async def count(
        self, *, guild: discord.Guild, registration_channel_id: int | None = None
    ) -> int:
        try:
            query = (
                f"SELECT COUNT(*) FROM {self.table_name} "
                f"WHERE {self.TableCols.Guild} = ?"
            )
            params: tuple[int, ...] = (guild.id,)
            if registration_channel_id is not None:
                query += f" AND {self.TableCols.RegistrationChannel} = ?"
                params += (registration_channel_id,)
            row = await self.database.fetch_one(
                query,
                params,
            )
            return row[0] if row else 0
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to count WZ purge channels: {e}"
            )
            return 0

    async def add(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        registration_channel_id: int = 0,
    ) -> bool:
        channel_name = f"unknown channel ({channel_id})"
        try:
            resolved_channel_name = await self.channel_name(guild, channel_id)
            if resolved_channel_name is not None:
                channel_name = f"{resolved_channel_name} ({channel_id})"
            executed = await self.database.execute(
                f"""
                INSERT OR IGNORE INTO {self.table_name}
                    ({self.TableCols.Guild}, {self.TableCols.RegistrationChannel},
                     {self.TableCols.Channel})
                SELECT ?, ?, ?
                WHERE (
                    SELECT COUNT(*) FROM {self.table_name}
                    WHERE {self.TableCols.Guild} = ?
                      AND {self.TableCols.RegistrationChannel} = ?
                ) < ?
                """,
                (
                    guild.id,
                    registration_channel_id,
                    channel_id,
                    guild.id,
                    registration_channel_id,
                    PurgeChannel.MAX_PER_REGISTRATION,
                ),
            )
            if not executed:
                return False

            row = await self.database.fetch_one(
                f"""
                SELECT {self.TableCols.RegistrationChannel} FROM {self.table_name}
                WHERE {self.TableCols.Guild} = ? AND {self.TableCols.Channel} = ?
                """,
                (guild.id, channel_id),
            )
            if (
                row is None
                or row[self.TableCols.RegistrationChannel] != registration_channel_id
            ):
                _logger.warning(
                    "%s Cannot add purge channel %s: registration limit reached.",
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
        self,
        *,
        guild: discord.Guild,
        channel_id: int | None = None,
        registration_channel_id: int | None = None,
    ) -> bool:
        target = (
            f"channel unknown ({channel_id})" if channel_id is not None else "channels"
        )
        try:
            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: tuple[int, ...] = (guild.id,)
            if registration_channel_id is not None:
                query += f" AND {self.TableCols.RegistrationChannel} = ?"
                params += (registration_channel_id,)
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
