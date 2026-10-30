from __future__ import annotations

import json

import aiosqlite
import discord

from hmwz import sqlite_db
from hmwz.modules.overview.models import Overview, OverviewButton


class OverviewRepository(sqlite_db.Base):
    """Stores overview content and message IDs for each guild."""

    table_name = "Module_Overviews"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            Guild INTEGER NOT NULL,
            OverviewId TEXT NOT NULL,
            Channel INTEGER NOT NULL,
            Message INTEGER,
            Title TEXT NOT NULL,
            Description TEXT NOT NULL,
            Buttons TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (Guild, OverviewId)
        ) WITHOUT ROWID
        """

    async def ensure_schema(self) -> bool:
        """Create the overview table."""
        return await self.database.execute(self.table)

    async def get(self, *, guild: discord.Guild, overview_id: str) -> Overview | None:
        """Return one overview, if it exists."""
        row = await self.database.fetch_one(
            f"""
            SELECT OverviewId, Channel, Message, Title, Description, Buttons
            FROM {self.table_name}
            WHERE Guild = ? AND OverviewId = ?
            """,
            (guild.id, overview_id),
        )
        return self._to_model(guild.id, row) if row is not None else None

    async def get_all(self, *, guild: discord.Guild) -> tuple[Overview, ...]:
        """Return every overview owned by a guild."""
        rows = await self.database.fetch_all(
            f"""
            SELECT OverviewId, Channel, Message, Title, Description, Buttons
            FROM {self.table_name}
            WHERE Guild = ?
            ORDER BY OverviewId
            """,
            (guild.id,),
        )
        return tuple(self._to_model(guild.id, row) for row in rows)

    async def save(self, overview: Overview) -> bool:
        """Insert or replace overview content while preserving its message ID."""
        buttons = json.dumps(
            [
                {
                    "button_id": button.button_id,
                    "label": button.label,
                    "style": button.style.value,
                    "row": button.row,
                }
                for button in overview.buttons
            ],
            separators=(",", ":"),
        )
        return await self.database.execute(
            f"""
            INSERT INTO {self.table_name}
                (Guild, OverviewId, Channel, Message, Title, Description, Buttons)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (Guild, OverviewId) DO UPDATE SET
                Channel = excluded.Channel,
                Message = excluded.Message,
                Title = excluded.Title,
                Description = excluded.Description,
                Buttons = excluded.Buttons
            """,
            (
                overview.guild_id,
                overview.overview_id,
                overview.channel_id,
                overview.message_id,
                overview.title,
                overview.description,
                buttons,
            ),
        )

    async def set_message(
        self,
        *,
        guild: discord.Guild,
        overview_id: str,
        message_id: int | None,
    ) -> bool:
        """Update the Discord message ID associated with an overview."""
        return await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET Message = ?
            WHERE Guild = ? AND OverviewId = ?
            """,
            (message_id, guild.id, overview_id),
        )

    async def remove(self, *, guild: discord.Guild, overview_id: str) -> bool:
        """Remove one overview record."""
        return await self.database.execute(
            f"DELETE FROM {self.table_name} WHERE Guild = ? AND OverviewId = ?",
            (guild.id, overview_id),
        )

    async def remove_guild(self, *, guild: discord.Guild) -> bool:
        """Remove all overview records owned by a guild."""
        return await self.database.execute(
            f"DELETE FROM {self.table_name} WHERE Guild = ?", (guild.id,)
        )

    @staticmethod
    def _to_model(guild_id: int, row: aiosqlite.Row) -> Overview:
        buttons_data = json.loads(row["Buttons"])
        buttons = tuple(
            OverviewButton(
                button_id=item["button_id"],
                label=item["label"],
                style=discord.ButtonStyle(item["style"]),
                row=item["row"],
            )
            for item in buttons_data
        )
        return Overview(
            guild_id=guild_id,
            overview_id=row["OverviewId"],
            channel_id=row["Channel"],
            message_id=row["Message"],
            title=row["Title"],
            description=row["Description"],
            buttons=buttons,
        )
