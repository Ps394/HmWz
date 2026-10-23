from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DonationType:
    """A donation category and its optional second input field."""

    name: str
    extra_field: str | None


@dataclass(frozen=True, slots=True)
class DonationRecord:
    """A persisted donation entry."""

    member_id: int
    member_name: str
    type_name: str
    amount: str
    extra_label: str | None
    extra_value: str | None
    created_at: str


class DonationRepository(sqlite_db.Base):
    """Stores donation types, channel setup, and donation entries."""

    table_name = "Donation_Types"
    channel_table_name = "Donation_Channels"
    entry_table_name = "Donations"

    @property
    def tables(self) -> tuple[str, ...]:
        """Return all schema statements required by the donation module."""
        return (
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                Guild INTEGER NOT NULL,
                Name TEXT NOT NULL COLLATE NOCASE,
                ExtraField TEXT,
                PRIMARY KEY (Guild, Name)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.channel_table_name} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Message INTEGER,
                PRIMARY KEY (Guild, Channel)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.entry_table_name} (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                MemberName TEXT NOT NULL,
                TypeName TEXT NOT NULL,
                Amount TEXT NOT NULL,
                ExtraLabel TEXT,
                ExtraValue TEXT,
                CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            f"""
            CREATE INDEX IF NOT EXISTS IX_Donations_Guild_Channel
            ON {self.entry_table_name} (Guild, Channel, Id DESC)
            """,
        )

    async def ensure_schema(self) -> bool:
        """Create every donation table and index."""
        for statement in self.tables:
            if not await self.database.execute(statement):
                _logger.error("Failed to create donation schema.")
                return False
        return True

    async def add_type(
        self, *, guild: discord.Guild, name: str, extra_field: str | None
    ) -> bool:
        """Add a donation type for a guild."""
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.table_name} (Guild, Name, ExtraField)
                VALUES (?, ?, ?)
                """,
                (guild.id, name, extra_field),
            )
        except Exception:
            _logger.exception(
                "%s Failed to add donation type %r.", self.log_prefix(guild), name
            )
            return False

    async def remove_type(self, *, guild: discord.Guild, name: str) -> bool:
        """Remove a configured donation type."""
        try:
            existing = await self.database.fetch_one(
                f"SELECT 1 FROM {self.table_name} WHERE Guild = ? AND Name = ?",
                (guild.id, name),
            )
            if existing is None:
                return False
            return await self.database.execute(
                f"DELETE FROM {self.table_name} WHERE Guild = ? AND Name = ?",
                (guild.id, name),
            )
        except Exception:
            _logger.exception(
                "%s Failed to remove donation type %r.", self.log_prefix(guild), name
            )
            return False

    async def get_types(self, *, guild: discord.Guild) -> tuple[DonationType, ...]:
        """Return configured donation types for a guild."""
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT Name, ExtraField
                FROM {self.table_name}
                WHERE Guild = ?
                ORDER BY Name COLLATE NOCASE
                """,
                (guild.id,),
            )
            return tuple(
                DonationType(name=row["Name"], extra_field=row["ExtraField"])
                for row in rows
            )
        except Exception:
            _logger.exception(
                "%s Failed to list donation types.", self.log_prefix(guild)
            )
            return ()

    async def get_type(self, *, guild: discord.Guild, name: str) -> DonationType | None:
        """Find a configured donation type by its name."""
        try:
            row = await self.database.fetch_one(
                f"""
                SELECT Name, ExtraField
                FROM {self.table_name}
                WHERE Guild = ? AND Name = ?
                """,
                (guild.id, name),
            )
            if row is None:
                return None
            return DonationType(name=row["Name"], extra_field=row["ExtraField"])
        except Exception:
            _logger.exception(
                "%s Failed to get donation type %r.", self.log_prefix(guild), name
            )
            return None

    async def add_channel(self, *, guild: discord.Guild, channel_id: int) -> bool:
        """Enable donation tracking in a channel."""
        try:
            return await self.database.execute(
                f"""
                INSERT OR IGNORE INTO {self.channel_table_name} (Guild, Channel)
                VALUES (?, ?)
                """,
                (guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to configure donation channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def get_channels(self, *, guild: discord.Guild) -> tuple[int, ...]:
        """Return configured donation channel IDs."""
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT Channel
                FROM {self.channel_table_name}
                WHERE Guild = ?
                ORDER BY Channel
                """,
                (guild.id,),
            )
            return tuple(row["Channel"] for row in rows)
        except Exception:
            _logger.exception(
                "%s Failed to list donation channels.", self.log_prefix(guild)
            )
            return ()

    async def get_channel(self, *, guild: discord.Guild, channel_id: int) -> int | None:
        """Return the overview message ID for a configured channel."""
        try:
            row = await self.database.fetch_one(
                f"""
                SELECT Message
                FROM {self.channel_table_name}
                WHERE Guild = ? AND Channel = ?
                """,
                (guild.id, channel_id),
            )
            return row["Message"] if row is not None else None
        except Exception:
            _logger.exception(
                "%s Failed to get donation channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def set_overview_message(
        self, *, guild: discord.Guild, channel_id: int, message_id: int
    ) -> bool:
        """Save the overview message ID for a configured channel."""
        try:
            return await self.database.execute(
                f"""
                UPDATE {self.channel_table_name}
                SET Message = ?
                WHERE Guild = ? AND Channel = ?
                """,
                (message_id, guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to store donation overview message in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def clear_overview_message(
        self, *, guild: discord.Guild, channel_id: int
    ) -> bool:
        """Clear a deleted or unavailable overview message reference."""
        try:
            return await self.database.execute(
                f"""
                UPDATE {self.channel_table_name}
                SET Message = NULL
                WHERE Guild = ? AND Channel = ?
                """,
                (guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to clear donation overview message in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def remove_channel(self, *, guild: discord.Guild, channel_id: int) -> bool:
        """Disable tracking in a channel without deleting its donation history."""
        try:
            return await self.database.execute(
                f"DELETE FROM {self.channel_table_name} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to remove donation channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def add_donation(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        member: discord.Member,
        donation_type: DonationType,
        amount: str,
        extra_value: str | None,
    ) -> bool:
        """Persist a donation and the donor's display name."""
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.entry_table_name}
                    (
                        Guild, Channel, Member, MemberName, TypeName, Amount,
                        ExtraLabel, ExtraValue
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild.id,
                    channel_id,
                    member.id,
                    member.display_name,
                    donation_type.name,
                    amount,
                    donation_type.extra_field,
                    extra_value,
                ),
            )
        except Exception:
            _logger.exception(
                "%s Failed to save donation for member %s in channel %s.",
                self.log_prefix(guild),
                member.id,
                channel_id,
            )
            return False

    async def get_donations(
        self, *, guild: discord.Guild, channel_id: int, limit: int = 20
    ) -> tuple[DonationRecord, ...]:
        """Return the most recent donations in a channel."""
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT
                    Member, MemberName, TypeName, Amount,
                    ExtraLabel, ExtraValue, CreatedAt
                FROM {self.entry_table_name}
                WHERE Guild = ? AND Channel = ?
                ORDER BY Id DESC
                LIMIT ?
                """,
                (guild.id, channel_id, limit),
            )
            return tuple(
                DonationRecord(
                    member_id=row["Member"],
                    member_name=row["MemberName"],
                    type_name=row["TypeName"],
                    amount=row["Amount"],
                    extra_label=row["ExtraLabel"],
                    extra_value=row["ExtraValue"],
                    created_at=row["CreatedAt"],
                )
                for row in rows
            )
        except Exception:
            _logger.exception(
                "%s Failed to list donations in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return ()

    async def remove_guild(self, *, guild: discord.Guild) -> bool:
        """Remove all donation data when the bot leaves a guild."""
        for table_name in (
            self.entry_table_name,
            self.channel_table_name,
            self.table_name,
        ):
            if not await self.database.execute(
                f"DELETE FROM {table_name} WHERE Guild = ?", (guild.id,)
            ):
                return False
        return True
