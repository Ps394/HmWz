from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import discord

from hmwz.i18n import t
from hmwz.ui.embeds import create_embed

from .repository import (
    DonationChannel,
    DonationRank,
    DonationRecord,
    DonationSummary,
    DonationType,
)
from .rush_pricing import RUSH_PERIOD_DURATION
from .validation import donation_timezone, donation_timezone_translation_key


class DonationOverview:
    """Creates configurable donation overviews, history, and rankings."""

    @staticmethod
    def create_embed(
        guild: discord.Guild,
        channel: DonationChannel,
        *,
        rush_start_at: datetime | None,
        timezone_name: str = "UTC",
        accelerated_hours: int = 0,
        donations_enabled: bool = True,
    ) -> discord.Embed:
        """Build the main embed using the channel's configurable title and text."""
        embed = create_embed(
            title=channel.title,
            description=channel.description or None,
            color=discord.Color.gold(),
        )
        if rush_start_at is not None:
            if accelerated_hours < 0:
                raise ValueError("Accelerated hours cannot be negative.")
            zone = donation_timezone(timezone_name)
            start_utc = rush_start_at.astimezone(UTC)
            end_utc = (
                start_utc + RUSH_PERIOD_DURATION - timedelta(hours=accelerated_hours)
            )
            start = start_utc.astimezone(zone)
            end = end_utc.astimezone(zone)
            embed.add_field(
                name=t(
                    guild,
                    "donation.overview.rush_start",
                ),
                value=f"{start:%d.%m.%Y %H:%M}",
                inline=True,
            )
            embed.add_field(
                name=t(guild, "donation.overview.rush_duration"),
                value=t(
                    guild,
                    "donation.setup.rush_duration",
                    days=RUSH_PERIOD_DURATION.days,
                    hours=int(RUSH_PERIOD_DURATION.total_seconds() // 3600),
                ),
                inline=True,
            )
            embed.add_field(
                name=t(
                    guild,
                    "donation.overview.rush_end",
                ),
                value=f"{end:%d.%m.%Y %H:%M}",
                inline=True,
            )
        embed.add_field(
            name=t(guild, "donation.overview.timezone"),
            value=t(guild, donation_timezone_translation_key(timezone_name)),
            inline=True,
        )
        embed.add_field(
            name=t(guild, "donation.overview.donations_status"),
            value=t(
                guild,
                "donation.setup.enabled"
                if donations_enabled
                else "donation.setup.disabled",
            ),
            inline=True,
        )
        return embed

    @staticmethod
    def create_ranking_embed(
        guild: discord.Guild,
        donation_type: DonationType,
        ranking: tuple[DonationRank, ...],
    ) -> discord.Embed:
        """Build a donor ranking grouped by the channel's single donation unit."""
        unit = (
            t(guild, "donation.setup.crystals_unit")
            if donation_type.kind == "time_reduction"
            else donation_type.unit
        )
        embed = create_embed(
            title=t(guild, "donation.ranking.title"),
            color=discord.Color.gold(),
        )
        lines = []
        for position, donor in enumerate(ranking, start=1):
            line = (
                f"**{position}. {donor.member_name}** — "
                f"{DonationOverview._format_amount(donor.amount)} {unit}"
            )
            if donation_type.kind == "time_reduction":
                line += " · " + t(
                    guild,
                    "donation.ranking.time_saved",
                    hours=donor.time_reduction_hours,
                )
            lines.append(line)
        embed.description = "\n".join(lines) or t(
            guild, "donation.ranking.no_donations"
        )
        return embed

    @staticmethod
    def create_history_embed(
        guild: discord.Guild,
        donation_type: DonationType,
        donations: tuple[DonationRecord, ...],
        summary: DonationSummary,
    ) -> discord.Embed:
        """Build a separate embed containing every donation in the active cycle."""
        title = t(
            guild,
            "donation.overview.history_title",
            count=summary.donation_count,
            duration=DonationOverview._format_duration(summary.time_reduction_hours),
        )
        embed = create_embed(title=title, color=discord.Color.gold())
        unit = (
            t(guild, "donation.setup.crystals_unit")
            if donation_type.kind == "time_reduction"
            else donation_type.unit
        )
        lines = [
            f"**{record.member_name}** — {DonationOverview._format_amount(record.amount)} "
            f"{unit}"
            + (
                f" · {t(guild, 'donation.overview.time_reduced')}: "
                f"{DonationOverview._format_reduction(record.time_reduction)}"
                if record.time_reduction
                else ""
            )
            for record in reversed(donations)
        ]
        history = "\n".join(lines) or t(guild, "donation.overview.no_donations")
        if len(history) > 4096:
            raise ValueError("Donation history exceeds the Discord embed limit.")
        embed.description = history
        return embed

    @staticmethod
    def _format_amount(amount: Decimal) -> str:
        """Format amounts with period thousands separators and decimal commas."""
        value = format(amount, "f")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        integer, separator, fraction = value.partition(".")
        grouped_integer = f"{int(integer):,}".replace(",", ".")
        if separator:
            return f"{grouped_integer},{fraction}"
        return grouped_integer

    @staticmethod
    def _format_reduction(reduction: str) -> str:
        """Ensure legacy and current time values are shown in hours."""
        return reduction if reduction.lower().endswith("h") else f"{reduction}h"

    @staticmethod
    def _format_duration(hours: int) -> str:
        """Render an integer hour duration as days and an HH:MM timestamp."""
        days, remaining_hours = divmod(hours, 24)
        return f"{days}d {remaining_hours:02d}:00"
