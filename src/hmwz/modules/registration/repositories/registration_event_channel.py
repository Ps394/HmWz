from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class RegistrationEventChannelRepository(sqlite_db.Base):
    """Stores the guild-wide destination for registration event snapshots."""

    table_name = "Registration_Event_Channel"

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Channel: str = "Channel"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER PRIMARY KEY,
            {self.TableCols.Channel} INTEGER NOT NULL
        )
        """

    async def get(self, *, guild: discord.Guild) -> int | None:
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
