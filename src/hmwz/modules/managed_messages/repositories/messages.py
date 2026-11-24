"""Persistence for bot-managed Discord message locations."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

import aiosqlite
import discord

from hmwz import sqlite_db

from ..models import ManagedMessage


class ManagedMessageRepository(sqlite_db.Base):
    """Store managed message IDs and comparable Discord payload data."""

    table_name = "Module_Managed_Messages"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            Guild INTEGER NOT NULL,
            ManagedId TEXT NOT NULL,
            Channel INTEGER NOT NULL,
            Message INTEGER,
            Content TEXT,
            Embeds TEXT NOT NULL DEFAULT '[]',
            TargetKind TEXT NOT NULL DEFAULT 'channel',
            AttachmentNames TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (Guild, ManagedId)
        ) WITHOUT ROWID
        """

    async def ensure_schema(self) -> bool:
        if not await self.database.execute(self.table):
            return False
        rows = await self.database.fetch_all(f'PRAGMA table_info("{self.table_name}")')
        existing = {row["name"] for row in rows}
        for name in ("TargetKind", "AttachmentNames"):
            if name not in existing:
                if name == "TargetKind":
                    definition = "TEXT NOT NULL DEFAULT 'channel'"
                elif name == "AttachmentNames":
                    definition = "TEXT NOT NULL DEFAULT '[]'"
                if not await self.database.execute(
                    f'ALTER TABLE "{self.table_name}" ADD COLUMN "{name}" {definition}'
                ):
                    return False
        return True

    async def get(
        self, *, guild: discord.Guild, managed_id: str
    ) -> ManagedMessage | None:
        row = await self.database.fetch_one(
            f"""
            SELECT ManagedId, Channel, Message, Content, Embeds,
                   TargetKind, AttachmentNames
            FROM {self.table_name}
            WHERE Guild = ? AND ManagedId = ?
            """,
            (guild.id, managed_id),
        )
        return self._to_model(guild.id, row) if row is not None else None

    async def get_all(self, *, guild: discord.Guild) -> tuple[ManagedMessage, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT ManagedId, Channel, Message, Content, Embeds,
                   TargetKind, AttachmentNames
            FROM {self.table_name}
            WHERE Guild = ?
            ORDER BY ManagedId
            """,
            (guild.id,),
        )
        return tuple(self._to_model(guild.id, row) for row in rows)

    async def save(self, message: ManagedMessage) -> bool:
        embeds = json.dumps(
            list(message.embeds),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return await self.database.execute(
            f"""
            INSERT INTO {self.table_name}
                (Guild, ManagedId, Channel, Message, Content, Embeds,
                 TargetKind, AttachmentNames)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (Guild, ManagedId) DO UPDATE SET
                Channel = excluded.Channel,
                Message = excluded.Message,
                Content = excluded.Content,
                Embeds = excluded.Embeds,
                TargetKind = excluded.TargetKind,
                AttachmentNames = excluded.AttachmentNames
            """,
            (
                message.guild_id,
                message.managed_id,
                message.channel_id,
                message.message_id,
                message.content,
                embeds,
                message.target_kind,
                json.dumps(list(message.attachment_names), ensure_ascii=False),
            ),
        )

    async def set_message(
        self,
        *,
        guild: discord.Guild,
        managed_id: str,
        message_id: int | None,
    ) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET Message = ?
            WHERE Guild = ? AND ManagedId = ?
            """,
            (message_id, guild.id, managed_id),
        )

    async def remove(self, *, guild: discord.Guild, managed_id: str) -> bool:
        return await self.database.execute(
            f"DELETE FROM {self.table_name} WHERE Guild = ? AND ManagedId = ?",
            (guild.id, managed_id),
        )

    async def remove_guild(self, *, guild: discord.Guild) -> bool:
        return await self.database.execute(
            f"DELETE FROM {self.table_name} WHERE Guild = ?",
            (guild.id,),
        )

    @staticmethod
    def _to_model(guild_id: int, row: aiosqlite.Row) -> ManagedMessage:
        try:
            embeds: tuple[dict[str, Any], ...] = tuple(json.loads(row["Embeds"]))
        except (TypeError, json.JSONDecodeError):
            embeds = ()
        try:
            attachment_names = tuple(json.loads(row["AttachmentNames"]))
        except (KeyError, TypeError, json.JSONDecodeError):
            attachment_names = ()
        return ManagedMessage(
            guild_id=guild_id,
            managed_id=row["ManagedId"],
            channel_id=row["Channel"],
            message_id=row["Message"],
            content=row["Content"],
            embeds=embeds,
            target_kind=cast(
                Literal["channel", "thread"],
                row["TargetKind"] if "TargetKind" in row.keys() else "channel",
            ),
            attachment_names=attachment_names,
        )
