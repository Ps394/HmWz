"""Persistence for the guild-wide registration snapshot destination."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class RegistrationSnapshotChannelRepository(sqlite_db.Base):
    """Stores the guild-wide destination for registration event snapshots."""

    table_name = "Registration_Snapshot_Channel"
    legacy_table_name = "Registration_Event_Channel"

    @dataclass(frozen=True)
    class TableCols:
        """Column names used by the snapshot destination table."""

        Guild: str = "Guild"
        Channel: str = "Channel"

    @property
    def table(self) -> str:
        """Return the SQL statement that creates the destination table."""
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER PRIMARY KEY,
            {self.TableCols.Channel} INTEGER NOT NULL
        )
        """

    async def migrate_schema(self) -> bool:
        """Rename the former snapshot destination table without losing records."""
        try:
            if not await self.database.execute(self.table):
                return False
            legacy_table = await self.database.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (self.legacy_table_name,),
            )
            if legacy_table is None:
                return True

            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    f"""
                    INSERT OR IGNORE INTO {self.table_name} (Guild, Channel)
                    SELECT Guild, Channel FROM {self.legacy_table_name}
                    """
                )
                await connection.execute(f"DROP TABLE {self.legacy_table_name}")
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "%s Failed to migrate the registration snapshot channel table.",
                self.log_prefix(),
            )
            return False

    async def get(self, *, guild: discord.Guild) -> int | None:
        """Return the configured snapshot destination channel ID, if any."""
        try:
            row = await self.database.fetch_one(
                f"SELECT {self.TableCols.Channel} FROM {self.table_name} "
                f"WHERE {self.TableCols.Guild} = ?",
                (guild.id,),
            )
            return row[self.TableCols.Channel] if row is not None else None
        except Exception:
            _logger.exception(
                "%s Failed to get the registration event channel.",
                self.log_prefix(guild),
            )
            return None

    async def set(self, *, guild: discord.Guild, channel_id: int) -> bool:
        """Set or replace the guild's snapshot destination channel."""
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.table_name} ({self.TableCols.Guild}, {self.TableCols.Channel})
                VALUES (?, ?)
                ON CONFLICT ({self.TableCols.Guild})
                DO UPDATE SET {self.TableCols.Channel} = excluded.{self.TableCols.Channel}
                """,
                (guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to set the registration event channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def remove(self, *, guild: discord.Guild) -> bool:
        """Remove the guild's configured snapshot destination."""
        try:
            return await self.database.execute(
                f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?",
                (guild.id,),
            )
        except Exception:
            _logger.exception(
                "%s Failed to remove the registration event channel.",
                self.log_prefix(guild),
            )
            return False

    async def remove_channel(self, *, guild: discord.Guild, channel_id: int) -> bool:
        """Remove the destination only when it matches the supplied channel."""
        try:
            return await self.database.execute(
                f"""
                DELETE FROM {self.table_name}
                WHERE {self.TableCols.Guild} = ? AND {self.TableCols.Channel} = ?
                """,
                (guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to remove registration event channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False


RegistrationEventChannelRepository = RegistrationSnapshotChannelRepository
