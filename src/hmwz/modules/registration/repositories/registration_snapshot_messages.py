from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class RegistrationSnapshotMessageRepository(sqlite_db.Base):
    """Store the Discord message used for each registration startup snapshot."""

    table_name = "Registration_Snapshot_Messages"

    @dataclass(frozen=True)
    class _Data:
        message_id: int

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            Guild INTEGER NOT NULL,
            SourceChannel INTEGER NOT NULL,
            DestinationChannel INTEGER NOT NULL,
            Message INTEGER NOT NULL,
            PRIMARY KEY (Guild, SourceChannel, DestinationChannel)
        ) WITHOUT ROWID
        """

    async def get(
        self,
        *,
        guild: discord.Guild,
        source_channel_id: int,
        destination_channel_id: int,
    ) -> _Data | None:
        try:
            row = await self.database.fetch_one(
                f"""
                SELECT Message
                FROM {self.table_name}
                WHERE Guild = ? AND SourceChannel = ? AND DestinationChannel = ?
                """,
                (guild.id, source_channel_id, destination_channel_id),
            )
            return self._Data(row["Message"]) if row is not None else None
        except Exception:
            _logger.exception(
                "%s Failed to get the startup snapshot message for channel %s.",
                self.log_prefix(guild),
                source_channel_id,
            )
            return None

    async def set(
        self,
        *,
        guild: discord.Guild,
        source_channel_id: int,
        destination_channel_id: int,
        message_id: int,
    ) -> bool:
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.table_name}
                    (Guild, SourceChannel, DestinationChannel, Message)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (Guild, SourceChannel, DestinationChannel)
                DO UPDATE SET Message = excluded.Message
                """,
                (guild.id, source_channel_id, destination_channel_id, message_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to store the startup snapshot message for channel %s.",
                self.log_prefix(guild),
                source_channel_id,
            )
            return False

    async def remove(
        self,
        *,
        guild: discord.Guild,
        source_channel_id: int,
        destination_channel_id: int,
    ) -> bool:
        try:
            return await self.database.execute(
                f"""
                DELETE FROM {self.table_name}
                WHERE Guild = ? AND SourceChannel = ? AND DestinationChannel = ?
                """,
                (guild.id, source_channel_id, destination_channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to remove the startup snapshot message for channel %s.",
                self.log_prefix(guild),
                source_channel_id,
            )
            return False
