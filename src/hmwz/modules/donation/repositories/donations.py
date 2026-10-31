from __future__ import annotations

import json
import asyncio
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import discord

from hmwz import sqlite_db

from ..models import (
    DonationChannel,
    DonationRank,
    DonationRecord,
    DonationSummary,
    DonationType,
)
from ..type.rush.pricing import (
    RUSH_DURATIONS_HOURS,
    available_rush_durations,
    rush_donation_cost,
    validate_rush_target,
)
from ..type.rush.validation import donation_timezone

_logger = logging.getLogger(__name__)


class DonationRepository(sqlite_db.Base):
    """Stores channel setup and donation entries."""

    channel_table_name = "Donation_Channels"
    type_table_name = "Donation_Channel_Types"
    entry_table_name = "Donations"

    def __init__(self, database: sqlite_db.Database) -> None:
        super().__init__(database)
        self._donation_lock = asyncio.Lock()

    @property
    def tables(self) -> tuple[str, ...]:
        """Return all schema statements required by the donation module."""
        return (
            f"""
            CREATE TABLE IF NOT EXISTS {self.channel_table_name} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Message INTEGER,
                RankingMessage INTEGER,
                SummaryMessage INTEGER,
                Title TEXT NOT NULL DEFAULT 'Donations',
                Description TEXT NOT NULL DEFAULT '',
                GoalHours INTEGER,
                RecentLimit INTEGER NOT NULL DEFAULT 20,
                ShowRanking INTEGER NOT NULL DEFAULT 0,
                RushStartAt TEXT,
                CurrentCycle INTEGER NOT NULL DEFAULT 1,
                Timezone TEXT NOT NULL DEFAULT 'UTC',
                ShowDonations INTEGER NOT NULL DEFAULT 1,
                DonationsEnabled INTEGER NOT NULL DEFAULT 1,
                ExportChannel INTEGER,
                TargetAt TEXT,
                PRIMARY KEY (Guild, Channel)
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.type_table_name} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Name TEXT NOT NULL,
                Kind TEXT NOT NULL,
                Unit TEXT NOT NULL,
                InputMode TEXT NOT NULL,
                Choices TEXT NOT NULL DEFAULT '[]',
                TimeReductions TEXT NOT NULL DEFAULT '[]',
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
                Unit TEXT NOT NULL,
                TimeReduction TEXT,
                Cycle INTEGER NOT NULL DEFAULT 1,
                CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            f"""
            CREATE INDEX IF NOT EXISTS IX_Donations_Guild_Channel
            ON {self.entry_table_name} (Guild, Channel, Id DESC)
            """,
        )

    @staticmethod
    def _parse_rush_start(value: str) -> datetime:
        start = datetime.fromisoformat(value)
        if start.utcoffset() is None:
            raise ValueError("Stored Rush start time must be timezone-aware.")
        return start.astimezone(timezone.utc)

    async def ensure_schema(self) -> bool:
        """Create the schema and add columns required by earlier releases."""
        for statement in self.tables:
            if not await self.database.execute(statement):
                _logger.error("Failed to create donation schema.")
                return False

        schema_ready = (
            await self.ensure_columns_for(
                self.channel_table_name,
                (
                    ("RankingMessage", "INTEGER"),
                    ("SummaryMessage", "INTEGER"),
                    ("Title", "TEXT NOT NULL DEFAULT 'Donations'"),
                    ("Description", "TEXT NOT NULL DEFAULT ''"),
                    ("GoalHours", "INTEGER"),
                    ("RecentLimit", "INTEGER NOT NULL DEFAULT 20"),
                    ("ShowRanking", "INTEGER NOT NULL DEFAULT 0"),
                    ("RushStartAt", "TEXT"),
                    ("CurrentCycle", "INTEGER NOT NULL DEFAULT 1"),
                    ("Timezone", "TEXT NOT NULL DEFAULT 'UTC'"),
                    ("ShowDonations", "INTEGER NOT NULL DEFAULT 1"),
                    ("DonationsEnabled", "INTEGER NOT NULL DEFAULT 1"),
                    ("ExportChannel", "INTEGER"),
                    ("TargetAt", "TEXT"),
                ),
            )
            and await self.ensure_columns_for(
                self.entry_table_name,
                (
                    ("Unit", "TEXT"),
                    ("TimeReduction", "TEXT"),
                    ("Cycle", "INTEGER NOT NULL DEFAULT 1"),
                ),
            )
            and await self.database.execute(
                f"UPDATE {self.entry_table_name} SET Unit = TypeName WHERE Unit IS NULL"
            )
        )
        if not schema_ready:
            return False
        return await self.database.execute(
            f"""
            CREATE INDEX IF NOT EXISTS IX_Donations_Guild_Channel_Cycle
            ON {self.entry_table_name} (Guild, Channel, Cycle, Id DESC)
            """
        )

    async def ensure_columns_for(
        self, table_name: str, columns: tuple[tuple[str, str], ...]
    ) -> bool:
        """Add schema columns without dropping previously stored donations."""
        rows = await self.database.fetch_all(f'PRAGMA table_info("{table_name}")')
        existing = {row["name"] for row in rows}
        for name, definition in columns:
            if name not in existing and not await self.database.execute(
                f'ALTER TABLE "{table_name}" ADD COLUMN "{name}" {definition}'
            ):
                _logger.error(
                    "Failed to add %s to donation table %s.", name, table_name
                )
                return False
        return True

    async def configure_channel(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        title: str,
        description: str,
        goal_hours: int | None = None,
        recent_limit: int = 20,
        show_ranking: bool = False,
        rush_start_at: datetime | None = None,
        timezone_name: str = "UTC",
        show_donations: bool = True,
        donations_enabled: bool = True,
        export_channel_id: int | None = None,
        target_at: datetime | None = None,
    ) -> bool:
        """Create or update the channel's donation-system settings."""
        if not 1 <= recent_limit <= 20:
            _logger.error("Donation recent limit must be between 1 and 20.")
            return False
        if rush_start_at is not None and rush_start_at.utcoffset() is None:
            _logger.error("Rush start time must be timezone-aware.")
            return False
        if target_at is not None:
            try:
                if rush_start_at is None:
                    raise ValueError("A target requires a Rush start.")
                current = await self.get_channel(guild=guild, channel_id=channel_id)
                summary = await self.get_summary(
                    guild=guild,
                    channel_id=channel_id,
                    cycle=current.current_cycle if current is not None else 1,
                )
                if summary is None:
                    return False
                target_at = validate_rush_target(
                    rush_start_at, target_at, summary.time_reduction_hours
                )
            except ValueError:
                _logger.exception("Invalid Rush target for channel %s.", channel_id)
                return False
        try:
            donation_timezone(timezone_name)
        except ValueError:
            _logger.error("Unknown donation timezone %s.", timezone_name)
            return False
        stored_start = (
            rush_start_at.astimezone(timezone.utc).isoformat()
            if rush_start_at is not None
            else None
        )
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.channel_table_name}
                    (
                        Guild, Channel, Title, Description, GoalHours, RecentLimit,
                        ShowRanking, RushStartAt, Timezone, ShowDonations,
                        DonationsEnabled, ExportChannel, TargetAt
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (Guild, Channel) DO UPDATE SET
                    Title = excluded.Title,
                    Description = excluded.Description,
                    GoalHours = excluded.GoalHours,
                    RecentLimit = excluded.RecentLimit,
                    ShowRanking = excluded.ShowRanking,
                    RushStartAt = excluded.RushStartAt,
                    Timezone = excluded.Timezone,
                    ShowDonations = excluded.ShowDonations,
                    DonationsEnabled = excluded.DonationsEnabled,
                    ExportChannel = excluded.ExportChannel,
                    TargetAt = excluded.TargetAt
                """,
                (
                    guild.id,
                    channel_id,
                    title,
                    description,
                    goal_hours,
                    recent_limit,
                    int(show_ranking),
                    stored_start,
                    timezone_name,
                    int(show_donations),
                    int(donations_enabled),
                    export_channel_id,
                    target_at.astimezone(timezone.utc).isoformat()
                    if target_at is not None
                    else None,
                ),
            )
        except Exception:
            _logger.exception(
                "%s Failed to configure donation channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def configure_type(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        donation_type: DonationType,
    ) -> bool:
        """Set the channel's only donation unit and its entry options."""
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.type_table_name}
                    (Guild, Channel, Name, Kind, Unit, InputMode, Choices, TimeReductions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (Guild, Channel) DO UPDATE SET
                    Name = excluded.Name,
                    Kind = excluded.Kind,
                    Unit = excluded.Unit,
                    InputMode = excluded.InputMode,
                    Choices = excluded.Choices,
                    TimeReductions = excluded.TimeReductions
                """,
                (
                    guild.id,
                    channel_id,
                    donation_type.name,
                    donation_type.kind,
                    donation_type.unit,
                    donation_type.input_mode,
                    json.dumps(donation_type.choices, ensure_ascii=False),
                    json.dumps(donation_type.time_reductions, ensure_ascii=False),
                ),
            )
        except Exception:
            _logger.exception(
                "%s Failed to configure donation type in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def get_channels(self, *, guild: discord.Guild) -> tuple[int, ...]:
        """Return channels with complete donation configuration."""
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT c.Channel
                FROM {self.channel_table_name} AS c
                JOIN {self.type_table_name} AS t
                    ON t.Guild = c.Guild AND t.Channel = c.Channel
                WHERE c.Guild = ?
                ORDER BY c.Channel
                """,
                (guild.id,),
            )
            return tuple(row["Channel"] for row in rows)
        except Exception:
            _logger.exception(
                "%s Failed to list donation channels.", self.log_prefix(guild)
            )
            return ()

    async def get_channel(
        self, *, guild: discord.Guild, channel_id: int
    ) -> DonationChannel | None:
        """Return a channel's persistent overview settings."""
        try:
            row = await self.database.fetch_one(
                f"""
                SELECT
                    Channel, Message, RankingMessage, SummaryMessage, Title,
                    Description, GoalHours, RecentLimit, ShowRanking, RushStartAt,
                    CurrentCycle, Timezone, ShowDonations, DonationsEnabled,
                    ExportChannel, TargetAt
                FROM {self.channel_table_name}
                WHERE Guild = ? AND Channel = ?
                """,
                (guild.id, channel_id),
            )
            if row is None:
                return None
            return DonationChannel(
                channel_id=row["Channel"],
                overview_message_id=row["Message"],
                ranking_message_id=row["RankingMessage"],
                history_message_id=row["SummaryMessage"],
                title=row["Title"],
                description=row["Description"],
                goal_hours=row["GoalHours"],
                recent_limit=row["RecentLimit"],
                show_ranking=bool(row["ShowRanking"]),
                rush_start_at=(
                    self._parse_rush_start(row["RushStartAt"])
                    if row["RushStartAt"] is not None
                    else None
                ),
                current_cycle=row["CurrentCycle"],
                timezone_name=row["Timezone"],
                show_donations=bool(row["ShowDonations"]),
                donations_enabled=bool(row["DonationsEnabled"]),
                export_channel_id=row["ExportChannel"],
                target_at=(
                    self._parse_rush_start(row["TargetAt"])
                    if row["TargetAt"] is not None
                    else None
                ),
            )
        except Exception:
            _logger.exception(
                "%s Failed to load donation channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def set_message(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        message_id: int | None,
        ranking: bool = False,
        history: bool = False,
    ) -> bool:
        """Save or clear one of the channel's public message IDs."""
        if ranking and history:
            raise ValueError("A donation message cannot be both ranking and history.")
        column = (
            "RankingMessage" if ranking else "SummaryMessage" if history else "Message"
        )
        try:
            return await self.database.execute(
                f"""
                UPDATE {self.channel_table_name}
                SET {column} = ?
                WHERE Guild = ? AND Channel = ?
                """,
                (message_id, guild.id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to store donation message for channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def get_type(
        self, *, guild: discord.Guild, channel_id: int
    ) -> DonationType | None:
        """Return the one configured donation type for a channel."""
        try:
            row = await self.database.fetch_one(
                f"""
                SELECT Name, Kind, Unit, InputMode, Choices, TimeReductions
                FROM {self.type_table_name}
                WHERE Guild = ? AND Channel = ?
                """,
                (guild.id, channel_id),
            )
            if row is None:
                return None
            return DonationType(
                name=row["Name"],
                kind=row["Kind"],
                unit=row["Unit"],
                input_mode=row["InputMode"],
                choices=tuple(json.loads(row["Choices"])),
                time_reductions=tuple(json.loads(row["TimeReductions"])),
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            _logger.exception(
                "%s Invalid donation configuration in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def add_donation(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        member: discord.Member,
        donation_type: DonationType,
        amount: Decimal,
        time_reduction: str | None,
        cycle: int = 1,
        rush_quoted_at: datetime | None = None,
    ) -> bool:
        """Serialize validation and writes so simultaneous donations cannot overshoot."""
        async with self._donation_lock:
            return await self._add_donation(
                guild=guild,
                channel_id=channel_id,
                member=member,
                donation_type=donation_type,
                amount=amount,
                time_reduction=time_reduction,
                cycle=cycle,
                rush_quoted_at=rush_quoted_at,
            )

    async def _add_donation(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        member: discord.Member,
        donation_type: DonationType,
        amount: Decimal,
        time_reduction: str | None,
        cycle: int,
        rush_quoted_at: datetime | None,
    ) -> bool:
        """Persist a numeric donation and its optional time reduction."""
        if not amount.is_finite() or amount <= 0 or cycle < 1:
            return False
        configuration = await self.get_channel(guild=guild, channel_id=channel_id)
        if (
            configuration is None
            or configuration.current_cycle != cycle
            or not configuration.donations_enabled
        ):
            return False
        if donation_type.kind == "time_reduction":
            if (
                time_reduction not in {f"{hours}h" for hours in RUSH_DURATIONS_HOURS}
                or rush_quoted_at is None
                or rush_quoted_at.utcoffset() is None
                or configuration.rush_start_at is None
            ):
                return False
            duration_hours = int(time_reduction.removesuffix("h"))
            summary = await self.get_summary(
                guild=guild, channel_id=channel_id, cycle=cycle
            )
            if (
                summary is None
                or duration_hours
                not in available_rush_durations(
                    started_at=configuration.rush_start_at,
                    now=rush_quoted_at,
                    accelerated_hours=summary.time_reduction_hours,
                    target_at=configuration.target_at,
                )
                or duration_hours
                not in available_rush_durations(
                    started_at=configuration.rush_start_at,
                    now=datetime.now(timezone.utc),
                    accelerated_hours=summary.time_reduction_hours,
                    target_at=configuration.target_at,
                )
            ):
                _logger.warning(
                    "Rush donation exceeds availability or target in channel %s.",
                    channel_id,
                )
                return False
            if amount != rush_donation_cost(
                started_at=configuration.rush_start_at,
                now=rush_quoted_at,
                duration_hours=duration_hours,
                accelerated_hours=summary.time_reduction_hours,
            ):
                return False
        elif time_reduction is not None or rush_quoted_at is not None:
            return False
        try:
            return await self.database.execute(
                f"""
                INSERT INTO {self.entry_table_name}
                    (
                        Guild, Channel, Member, MemberName, TypeName, Amount,
                        Unit, TimeReduction, Cycle
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild.id,
                    channel_id,
                    member.id,
                    member.display_name,
                    donation_type.name,
                    str(amount),
                    donation_type.unit,
                    time_reduction,
                    cycle,
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
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        limit: int | None = 20,
        cycle: int | None = None,
    ) -> tuple[DonationRecord, ...]:
        """Return donations in a channel, optionally limiting the result count."""
        records = await self._get_donations(
            guild=guild,
            channel_id=channel_id,
            limit=limit,
            cycle=cycle,
        )
        return records or ()

    async def get_donations_for_export(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        cycle: int,
    ) -> tuple[DonationRecord, ...] | None:
        """Return every donation in a cycle, preserving query failures as None."""
        return await self._get_donations(
            guild=guild,
            channel_id=channel_id,
            limit=None,
            cycle=cycle,
        )

    async def _get_donations(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        limit: int | None,
        cycle: int | None,
    ) -> tuple[DonationRecord, ...] | None:
        try:
            query = f"""
                SELECT Member, MemberName, Amount, Unit, TimeReduction, CreatedAt
                FROM {self.entry_table_name}
                WHERE Guild = ? AND Channel = ?
                    AND (? IS NULL OR Cycle = ?)
                ORDER BY Id DESC
            """
            parameters: tuple[object, ...] = (guild.id, channel_id, cycle, cycle)
            if limit is not None:
                query += " LIMIT ?"
                parameters += (limit,)
            rows = await self.database.fetch_all(query, parameters)
            records: list[DonationRecord] = []
            for row in rows:
                try:
                    amount = Decimal(row["Amount"])
                except InvalidOperation:
                    _logger.warning(
                        "%s Skipping invalid legacy donation amount in channel %s.",
                        self.log_prefix(guild),
                        channel_id,
                    )
                    continue
                if not amount.is_finite():
                    _logger.warning(
                        "%s Skipping non-finite donation amount in channel %s.",
                        self.log_prefix(guild),
                        channel_id,
                    )
                    continue
                records.append(
                    DonationRecord(
                        member_id=row["Member"],
                        member_name=row["MemberName"],
                        amount=amount,
                        unit=row["Unit"],
                        time_reduction=row["TimeReduction"],
                        created_at=row["CreatedAt"],
                    )
                )
            return tuple(records)
        except Exception:
            _logger.exception(
                "%s Failed to list donations in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def get_summary(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        cycle: int | None = None,
    ) -> DonationSummary | None:
        """Return donation count and time savings for a cycle or all-time history."""
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT TimeReduction
                FROM {self.entry_table_name}
                WHERE Guild = ? AND Channel = ?
                    AND (? IS NULL OR Cycle = ?)
                """,
                (guild.id, channel_id, cycle, cycle),
            )
            total_hours = 0
            for row in rows:
                value = row["TimeReduction"]
                if value is None:
                    continue
                match = re.fullmatch(r"\s*(\d+)\s*h?\s*", str(value), re.IGNORECASE)
                if match is None:
                    _logger.warning(
                        "%s Skipping invalid time reduction in channel %s.",
                        self.log_prefix(guild),
                        channel_id,
                    )
                    continue
                total_hours += int(match.group(1))
            return DonationSummary(
                donation_count=len(rows),
                time_reduction_hours=total_hours,
            )
        except Exception:
            _logger.exception(
                "%s Failed to summarize donations in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def get_ranking(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        unit: str,
        limit: int = 10,
    ) -> tuple[DonationRank, ...]:
        """Aggregate donors across every cycle for the channel's single unit."""
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT Member, MemberName, Amount, TimeReduction
                FROM {self.entry_table_name}
                WHERE Guild = ? AND Channel = ? AND Unit = ?
                """,
                (guild.id, channel_id, unit),
            )
            totals: dict[int, tuple[str, Decimal, int, int]] = {}
            for row in rows:
                member_id = row["Member"]
                name, total, count, time_reduction_hours = totals.get(
                    member_id, (row["MemberName"], Decimal(0), 0, 0)
                )
                try:
                    amount = Decimal(row["Amount"])
                except InvalidOperation:
                    _logger.warning(
                        "%s Skipping invalid amount in donation ranking for channel %s.",
                        self.log_prefix(guild),
                        channel_id,
                    )
                    continue
                if not amount.is_finite():
                    continue
                time_reduction = row["TimeReduction"]
                if time_reduction is not None:
                    match = re.fullmatch(
                        r"\s*(\d+)\s*h?\s*", str(time_reduction), re.IGNORECASE
                    )
                    if match is None:
                        _logger.warning(
                            "%s Skipping invalid time reduction in donation ranking "
                            "for channel %s.",
                            self.log_prefix(guild),
                            channel_id,
                        )
                    else:
                        time_reduction_hours += int(match.group(1))
                totals[member_id] = (
                    name,
                    total + amount,
                    count + 1,
                    time_reduction_hours,
                )
            ranked = sorted(
                (
                    DonationRank(member_id, name, total, count, hours)
                    for member_id, (name, total, count, hours) in totals.items()
                ),
                key=lambda donor: (-donor.amount, donor.member_name.casefold()),
            )
            return tuple(ranked[:limit])
        except Exception:
            _logger.exception(
                "%s Failed to calculate donation ranking for channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return ()

    async def get_history_units(
        self, *, guild: discord.Guild, channel_id: int
    ) -> tuple[str, ...] | None:
        """Return units already represented in this channel's donation history."""
        try:
            rows = await self.database.fetch_all(
                f"""
                SELECT DISTINCT Unit
                FROM {self.entry_table_name}
                WHERE Guild = ? AND Channel = ?
                """,
                (guild.id, channel_id),
            )
            return tuple(row["Unit"] for row in rows if row["Unit"])
        except Exception:
            _logger.exception(
                "%s Failed to inspect donation units in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return None

    async def reset_cycle(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        rush_start_at: datetime | None,
        target_at: datetime | None = None,
    ) -> bool:
        """Start a new current cycle while retaining all-time donation history."""
        if rush_start_at is not None and rush_start_at.utcoffset() is None:
            _logger.error("Rush start time must be timezone-aware.")
            return False
        if target_at is not None:
            try:
                if rush_start_at is None:
                    raise ValueError("A target requires a Rush start.")
                target_at = validate_rush_target(rush_start_at, target_at)
            except ValueError:
                _logger.exception(
                    "Invalid target for new Rush cycle in %s.", channel_id
                )
                return False
        stored_start = (
            rush_start_at.astimezone(timezone.utc).isoformat()
            if rush_start_at is not None
            else None
        )
        try:
            return await self.database.execute(
                f"""
                UPDATE {self.channel_table_name}
                SET CurrentCycle = CurrentCycle + 1, RushStartAt = ?,
                    DonationsEnabled = 1, TargetAt = ?
                WHERE Guild = ? AND Channel = ?
                """,
                (
                    stored_start,
                    target_at.astimezone(timezone.utc).isoformat()
                    if target_at is not None
                    else None,
                    guild.id,
                    channel_id,
                ),
            )
        except Exception:
            _logger.exception(
                "%s Failed to reset donation cycle in channel %s.",
                self.log_prefix(guild),
                channel_id,
            )
            return False

    async def remove_channel(self, *, guild: discord.Guild, channel_id: int) -> bool:
        """Remove a donation system and all associated history and rankings."""
        return await self.delete_channel(guild=guild, channel_id=channel_id)

    async def delete_channel(self, *, guild: discord.Guild, channel_id: int) -> bool:
        """Permanently delete a channel's donation entries and configuration."""
        for table_name in (
            self.entry_table_name,
            self.type_table_name,
            self.channel_table_name,
        ):
            if not await self.database.execute(
                f"DELETE FROM {table_name} WHERE Guild = ? AND Channel = ?",
                (guild.id, channel_id),
            ):
                _logger.error(
                    "%s Failed to delete donation data from table %s in channel %s.",
                    self.log_prefix(guild),
                    table_name,
                    channel_id,
                )
                return False
        return True

    async def remove_guild(self, *, guild: discord.Guild) -> bool:
        """Remove all donation data when the bot leaves a guild."""
        for table_name in (
            self.entry_table_name,
            self.type_table_name,
            self.channel_table_name,
        ):
            if not await self.database.execute(
                f"DELETE FROM {table_name} WHERE Guild = ?", (guild.id,)
            ):
                return False
        legacy_types = await self.database.fetch_one(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("Donation_Types",),
        )
        if legacy_types is not None and not await self.database.execute(
            "DELETE FROM Donation_Types WHERE Guild = ?", (guild.id,)
        ):
            return False
        return True
