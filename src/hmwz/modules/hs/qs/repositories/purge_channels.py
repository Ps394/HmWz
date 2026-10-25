from __future__ import annotations

import logging

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class QSPurgeChannelRepository(sqlite_db.Base):
    """Persist the channels configured for QS message cleanup."""

    table_name = "QsPurgeChannels"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            Guild INTEGER NOT NULL,
            Channel INTEGER NOT NULL,
            PRIMARY KEY (Guild, Channel),
            FOREIGN KEY (Guild) REFERENCES Servers(Guild)
        ) WITHOUT ROWID
        """

    type Records = tuple[int, ...] | None

    async def get(self, *, guild: discord.Guild) -> Records:
        try:
            rows = await self.database.fetch_all(
                f"SELECT Channel FROM {self.table_name} WHERE Guild = ? ORDER BY Channel",
                (guild.id,),
            )
            return tuple(row["Channel"] for row in rows) or None
        except Exception:
            _logger.exception(
                "%s Failed to get QS cleanup channels.", self.log_prefix(guild)
            )
            return None

    async def add(self, *, guild: discord.Guild, channel_id: int) -> bool:
        try:
            return await self.database.execute(
                f"INSERT OR IGNORE INTO {self.table_name} (Guild, Channel) VALUES (?, ?)",
                (guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to add QS cleanup channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def remove(
        self, *, guild: discord.Guild, channel_id: int | None = None
    ) -> bool:
        try:
            query = f"DELETE FROM {self.table_name} WHERE Guild = ?"
            params: tuple[int, ...] = (guild.id,)
            if channel_id is not None:
                query += " AND Channel = ?"
                params += (channel_id,)
            return await self.database.execute(query, params)
        except Exception:
            _logger.exception(
                "%s Failed to remove QS cleanup channels.", self.log_prefix(guild)
            )
            return False
