"""Persistence for thread targets of bot-managed messages."""

from __future__ import annotations

import discord

from hmwz import sqlite_db

from ..models import ManagedThread


class ManagedThreadRepository(sqlite_db.Base):
    """Store one or more Discord threads for a managed message."""

    table_name = "Module_Managed_Message_Threads"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            Guild INTEGER NOT NULL,
            ManagedId TEXT NOT NULL,
            Thread INTEGER NOT NULL,
            Message INTEGER,
            PRIMARY KEY (Guild, ManagedId, Thread)
        ) WITHOUT ROWID
        """

    async def ensure_schema(self) -> bool:
        return await self.database.execute(self.table)

    async def get(
        self,
        *,
        guild: discord.Guild,
        managed_id: str,
        thread_id: int,
    ) -> ManagedThread | None:
        row = await self.database.fetch_one(
            f"""
            SELECT Thread, Message
            FROM {self.table_name}
            WHERE Guild = ? AND ManagedId = ? AND Thread = ?
            """,
            (guild.id, managed_id, thread_id),
        )
        if row is None:
            return None
        return ManagedThread(
            guild_id=guild.id,
            managed_id=managed_id,
            thread_id=row["Thread"],
            message_id=row["Message"],
        )

    async def get_all(
        self, *, guild: discord.Guild, managed_id: str
    ) -> tuple[ManagedThread, ...]:
        rows = await self.database.fetch_all(
            f"""
            SELECT Thread, Message
            FROM {self.table_name}
            WHERE Guild = ? AND ManagedId = ?
            ORDER BY Thread
            """,
            (guild.id, managed_id),
        )
        return tuple(
            ManagedThread(
                guild_id=guild.id,
                managed_id=managed_id,
                thread_id=row["Thread"],
                message_id=row["Message"],
            )
            for row in rows
        )

    async def save(self, managed_thread: ManagedThread) -> bool:
        return await self.database.execute(
            f"""
            INSERT INTO {self.table_name}
                (Guild, ManagedId, Thread, Message)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (Guild, ManagedId, Thread) DO UPDATE SET
                Message = excluded.Message
            """,
            (
                managed_thread.guild_id,
                managed_thread.managed_id,
                managed_thread.thread_id,
                managed_thread.message_id,
            ),
        )

    async def set_message(
        self,
        *,
        guild: discord.Guild,
        managed_id: str,
        thread_id: int,
        message_id: int | None,
    ) -> bool:
        return await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET Message = ?
            WHERE Guild = ? AND ManagedId = ? AND Thread = ?
            """,
            (message_id, guild.id, managed_id, thread_id),
        )

    async def remove(
        self,
        *,
        guild: discord.Guild,
        managed_id: str,
        thread_id: int,
    ) -> bool:
        return await self.database.execute(
            f"""
            DELETE FROM {self.table_name}
            WHERE Guild = ? AND ManagedId = ? AND Thread = ?
            """,
            (guild.id, managed_id, thread_id),
        )

    async def remove_managed(self, *, guild: discord.Guild, managed_id: str) -> bool:
        return await self.database.execute(
            f"""
            DELETE FROM {self.table_name}
            WHERE Guild = ? AND ManagedId = ?
            """,
            (guild.id, managed_id),
        )

    async def remove_guild(self, *, guild: discord.Guild) -> bool:
        return await self.database.execute(
            f"DELETE FROM {self.table_name} WHERE Guild = ?",
            (guild.id,),
        )
