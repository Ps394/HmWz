from __future__ import annotations

import asyncio
import logging
import typing
from dataclasses import dataclass

import discord
import sqlLiteDB

_logger = logging.getLogger(__name__)


class WzList(sqlLiteDB.Base):
    """Recordset fuer Registrierungslisten-Nachrichten je Guild."""

    def __init__(self, database: sqlLiteDB.Database):
        super().__init__(database)

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Channel: str = "Channel"
        Message: str = "Message"
        Title: str = "Title"
        Text: str = "Text"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER,
            {self.TableCols.Channel} INTEGER,
            {self.TableCols.Message} INTEGER,
            {self.TableCols.Title} TEXT,
            {self.TableCols.Text} TEXT,
            FOREIGN KEY ({self.TableCols.Guild}) REFERENCES Servers(Guild),
            PRIMARY KEY ({self.TableCols.Guild}, {self.TableCols.Message})
        ) WITHOUT ROWID
        """

    @dataclass(frozen=True)
    class _Data:
        guild_id: int
        channel: int
        message: int
        title: str | None
        text: str | None

    type Record = _Data | None
    type Records = tuple[_Data, ...] | None

    async def get(self, *, guild: discord.Guild) -> Records:
        try:
            query = f"""
            SELECT
                {self.TableCols.Channel},
                {self.TableCols.Message},
                {self.TableCols.Title},
                {self.TableCols.Text}
            FROM
                {self.table_name}
            WHERE
                {self.TableCols.Guild} = ?
            """
            records = await self.database.fetch_all(query, (guild.id,))
            if not records:
                return None

            async def resolve_record(rec: typing.Any) -> WzList._Data:
                return self._Data(
                    guild_id=guild.id,
                    channel=rec[self.TableCols.Channel],
                    message=rec[self.TableCols.Message],
                    title=rec[self.TableCols.Title],
                    text=rec[self.TableCols.Text],
                )

            out: list[WzList._Data] = await asyncio.gather(*(resolve_record(rec) for rec in records))
            return tuple(out) if out else None
        except Exception as e:
            _logger.exception(f"{self.log_prefix(guild)} Failed to get WZ lists: {e}")
            return None

    async def add(
        self,
        *,
        guild: discord.Guild,
        channel: int,
        message: int,
        title: str,
        text: str,
    ) -> bool:
        try:
            await self.database.execute(
                f"""
                INSERT OR REPLACE INTO {self.table_name}
                ({self.TableCols.Guild}, {self.TableCols.Channel}, {self.TableCols.Message}, {self.TableCols.Title}, {self.TableCols.Text})
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild.id, channel, message, title, text),
            )
            _logger.info(f"{self.log_prefix(guild)} Added WZ list message {message}.")
            return True
        except Exception as e:
            _logger.exception(f"{self.log_prefix(guild)} Failed to add WZ list message {message}: {e}")
            return False

    async def remove(
        self,
        *,
        guild: discord.Guild,
        message: int | None = None,
        messages: list[int] | None = None,
    ) -> bool:
        target = "lists"
        try:
            if message is not None and messages:
                raise ValueError("Cannot provide both message and messages filters.")

            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: list[typing.Any] = [guild.id]

            if message is not None:
                query += f" AND {self.TableCols.Message} = ?"
                params.append(message)
                target = f"message {message}"
            elif messages:
                placeholders = ",".join("?" for _ in messages)
                query += f" AND {self.TableCols.Message} IN ({placeholders})"
                params.extend(messages)
                target = f"messages {messages}"
            else:
                target = "all list messages"

            await self.database.execute(query, tuple(params))
            _logger.info(f"{self.log_prefix(guild)} Removed WZ {target}.")
            return True
        except Exception as e:
            _logger.exception(f"{self.log_prefix(guild)} Failed to remove WZ {target}: {e}")
            return False
