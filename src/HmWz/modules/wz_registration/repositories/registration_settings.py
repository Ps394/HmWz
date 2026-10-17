from __future__ import annotations

import logging
import typing
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class RegistrationSettingsRepository(sqlite_db.Base):
    """Repository fuer Registrierungskanal und Registrierungsnachricht je Guild."""

    table_name = "WzRegistration"

    def __init__(self, database: sqlite_db.Database):
        super().__init__(database)

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Channel: str = "Channel"
        Message: str = "Message"
        Title: str = "Title"
        Description: str = "Description"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER PRIMARY KEY,
            {self.TableCols.Channel} INTEGER,
            {self.TableCols.Message} INTEGER,
            {self.TableCols.Title} TEXT,
            {self.TableCols.Description} TEXT,
            FOREIGN KEY ({self.TableCols.Guild}) REFERENCES Servers(Guild)
        ) WITHOUT ROWID
        """

    @dataclass(frozen=True)
    class _Data:
        guild_id: int
        channel: int | None
        message: int | None
        title: str | None
        description: str | None

        @property
        def has_channel(self) -> bool:
            return self.channel is not None

        @property
        def has_message(self) -> bool:
            return self.message is not None

        @property
        def has_title(self) -> bool:
            return self.title is not None and self.title != ""

        @property
        def has_description(self) -> bool:
            return self.description is not None and self.description != ""

    type Record = _Data | None

    async def get(self, *, guild: discord.Guild) -> Record:
        try:
            query = f"""
            SELECT
                {self.TableCols.Channel},
                {self.TableCols.Message},
                {self.TableCols.Title},
                {self.TableCols.Description}
            FROM
                {self.table_name}
            WHERE
                {self.TableCols.Guild} = ?
            """
            record = await self.database.fetch_one(query, (guild.id,))
            if not record:
                return None

            return self._Data(
                guild_id=guild.id,
                channel=record[self.TableCols.Channel],
                message=record[self.TableCols.Message],
                title=record[self.TableCols.Title],
                description=record[self.TableCols.Description],
            )
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to get WZ registration: {e}"
            )
            return None

    async def upsert(
        self,
        *,
        guild: discord.Guild,
        channel_id: int | None = None,
        message_id: int | None = None,
        title: str | None = None,
        description: str | None = None,
    ) -> bool:
        try:
            cols: list[str] = []
            vals: list[typing.Any] = []

            if channel_id is not None:
                cols.append(self.TableCols.Channel)
                vals.append(channel_id)
            if message_id is not None:
                cols.append(self.TableCols.Message)
                vals.append(message_id)
            if title is not None:
                cols.append(self.TableCols.Title)
                vals.append(title)
            if description is not None:
                cols.append(self.TableCols.Description)
                vals.append(description)

            if not cols:
                return False

            columns = f"{self.TableCols.Guild}, " + ", ".join(cols)
            placeholders = ", ".join(["?"] * (1 + len(cols)))
            update_clause = ", ".join([f"{c}=excluded.{c}" for c in cols])

            query = f"""
                INSERT INTO {self.table_name} ({columns})
                VALUES ({placeholders})
                ON CONFLICT({self.TableCols.Guild}) DO UPDATE SET {update_clause}
            """

            params = [guild.id] + vals
            if not await self.database.execute(query, tuple(params)):
                return False
            _logger.info(f"{self.log_prefix(guild)} WZ registration upserted.")
            return True
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to upsert WZ registration: {e}"
            )
            return False

    async def remove(self, *, guild: discord.Guild) -> bool:
        try:
            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            executed = await self.database.execute(query, (guild.id,))
            if executed:
                _logger.info(
                    f"{self.log_prefix(guild)} Removed WZ registration records."
                )
            return executed
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to remove WZ registration records: {e}"
            )
            return False
