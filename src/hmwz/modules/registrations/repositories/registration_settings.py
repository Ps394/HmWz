from __future__ import annotations

import logging
import typing
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class RegistrationSettingsRepository(sqlite_db.Base):
    """Repository fuer Registrierungskanaele und Nachrichten je Guild."""

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
        GuildName: str = "GuildName"
        ChannelName: str = "ChannelName"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER NOT NULL,
            {self.TableCols.Channel} INTEGER,
            {self.TableCols.Message} INTEGER,
            {self.TableCols.Title} TEXT,
            {self.TableCols.Description} TEXT,
            {self.TableCols.GuildName} TEXT,
            {self.TableCols.ChannelName} TEXT,
            PRIMARY KEY ({self.TableCols.Guild}, {self.TableCols.Channel}),
            FOREIGN KEY ({self.TableCols.Guild}) REFERENCES Servers(Guild)
        )
        """

    async def migrate_names(self) -> bool:
        """Add and populate readable names for existing registration settings."""
        if not await self._migrate_channel_key():
            return False
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

                await connection.execute(
                    f'ALTER TABLE "{self.table_name}" RENAME TO "{self.table_name}_legacy"'
                )
                await connection.execute(self.table)
                legacy_columns = {column["name"] for column in columns}
                name_columns = (
                    "GuildName" if "GuildName" in legacy_columns else "NULL",
                    "ChannelName" if "ChannelName" in legacy_columns else "NULL",
                )
                await connection.execute(
                    f"""
                    INSERT OR IGNORE INTO "{self.table_name}"
                        (Guild, Channel, Message, Title, Description, GuildName, ChannelName)
                    SELECT Guild, Channel, Message, Title, Description,
                           {name_columns[0]}, {name_columns[1]}
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
    type Records = tuple[_Data, ...] | None

    @staticmethod
    def _record(guild_id: int, record: typing.Any) -> _Data:
        return RegistrationSettingsRepository._Data(
            guild_id=guild_id,
            channel=record["Channel"],
            message=record["Message"],
            title=record["Title"],
            description=record["Description"],
        )

    async def get_all(self, *, guild: discord.Guild) -> Records:
        """Return every configured WZ registration for a guild."""
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT Channel, Message, Title, Description
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
    ) -> bool:
        channel_name: str | None = None
        try:
            resolved_channel_name = (
                await self.channel_name(guild, channel_id)
                if channel_id is not None
                else None
            )
            channel_name = (
                f"{resolved_channel_name} ({channel_id})"
                if channel_id is not None and resolved_channel_name is not None
                else None
            )
            cols: list[str] = []
            vals: list[typing.Any] = []

            cols.append(self.TableCols.Channel)
            vals.append(channel_id)
            cols.append(self.TableCols.ChannelName)
            vals.append(resolved_channel_name)
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

            cols.insert(0, self.TableCols.GuildName)
            vals.insert(0, guild.name)
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
            channel_context = (
                f" for channel {channel_name}" if channel_name is not None else ""
            )
            _logger.debug(
                f"{self.log_prefix(guild)} WZ registration upserted{channel_context}."
            )
            return True
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to upsert WZ registration "
                f"for channel {channel_name or 'not specified'}: {e}"
            )
            return False

    async def remove(
        self, *, guild: discord.Guild, channel_id: int | None = None
    ) -> bool:
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
