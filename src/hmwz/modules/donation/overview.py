from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import discord

from hmwz.i18n import t

from .repository import (
    DonationChannel,
    DonationRank,
    DonationRecord,
    DonationSummary,
    DonationType,
)
from .rush_pricing import (
    RUSH_DONATION_CUTOFF,
    RUSH_PERIOD_DURATION,
    RUSH_ZONE_BOUNDARIES_HOURS,
    RUSH_ZONE_PRICES,
    rush_zone_index,
)


class DonationOverview:
    """Creates a donation overview and its separate ranking message."""

    @staticmethod
    def create_embed(
        guild: discord.Guild,
        channel: DonationChannel,
        donation_type: DonationType,
        donations: tuple[DonationRecord, ...],
        summary: DonationSummary,
        now: datetime | None = None,
    ) -> discord.Embed:
        """Build the main donation overview."""
        now = now or datetime.now(timezone.utc)
        unit = (
            t(guild, "donation.setup.crystals_unit")
            if donation_type.kind == "time_reduction"
            else donation_type.unit
        )
        embed = discord.Embed(
            title=channel.title,
            description=channel.description or None,
            color=discord.Color.gold(),
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
            for record in donations
        ]
        history = "\n".join(lines) or t(guild, "donation.overview.no_donations")
        if len(history) > 1024:
            history = history[:1020].rsplit("\n", maxsplit=1)[0] + "\n..."
        embed.add_field(
            name=t(guild, "donation.overview.recent"),
            value=history,
            inline=False,
        )
        embed.add_field(
            name=t(guild, "donation.overview.donation_count"),
            value=str(summary.donation_count),
            inline=True,
        )
        if donation_type.kind == "time_reduction":
            if channel.rush_start_at is not None:
                berlin = ZoneInfo("Europe/Berlin")
                start = channel.rush_start_at.astimezone(berlin)
                end = (channel.rush_start_at + RUSH_PERIOD_DURATION).astimezone(berlin)
                embed.add_field(
                    name=t(guild, "donation.overview.rush_period"),
                    value=(f"{start:%d.%m.%Y %H:%M} → {end:%d.%m.%Y %H:%M}"),
                    inline=False,
                )
            embed.add_field(
                name=t(guild, "donation.overview.rush_zones"),
                value=DonationOverview._format_rush_zones(
                    guild,
                    rush_zone_index(channel.rush_start_at, now)
                    if channel.rush_start_at is not None
                    else None,
                ),
                inline=False,
            )
            reduced_hours = summary.time_reduction_hours
            embed.add_field(
                name=t(guild, "donation.overview.total_time_reduced"),
                value=DonationOverview._format_duration(reduced_hours),
                inline=True,
            )
            goal_value = t(guild, "donation.overview.goal_not_set")
            if channel.goal_hours is not None:
                remaining_hours = max(channel.goal_hours - reduced_hours, 0)
                goal_value = (
                    f"{DonationOverview._format_duration(channel.goal_hours)} → "
                    f"{DonationOverview._format_duration(remaining_hours)}"
                )
            embed.add_field(
                name=t(guild, "donation.overview.goal_remaining"),
                value=goal_value,
                inline=True,
            )
        if len(donations) >= channel.recent_limit:
            embed.set_footer(
                text=t(
                    guild,
                    "donation.overview.recent_limit",
                    count=channel.recent_limit,
                )
            )
        return embed

    @staticmethod
    def _format_rush_zones(guild: discord.Guild, current_zone: int | None) -> str:
        """Render each Rush price band and emphasize the active band."""
        zone_ranges = (
            (0, RUSH_ZONE_BOUNDARIES_HOURS[0]),
            (RUSH_ZONE_BOUNDARIES_HOURS[0], RUSH_ZONE_BOUNDARIES_HOURS[1]),
            (
                RUSH_ZONE_BOUNDARIES_HOURS[1],
                int(RUSH_DONATION_CUTOFF.total_seconds() / 3600),
            ),
        )
        lines = []
        for zone_index, (start, end) in enumerate(zone_ranges):
            price_1h, price_8h, price_24h = (
                RUSH_ZONE_PRICES[1][zone_index],
                RUSH_ZONE_PRICES[8][zone_index],
                RUSH_ZONE_PRICES[24][zone_index],
            )
            line = t(
                guild,
                "donation.overview.rush_zone_range",
                start=start,
                end=end,
                price_1h=price_1h,
                price_8h=price_8h,
                price_24h=price_24h,
            )
            lines.append(f"**{line}**" if zone_index == current_zone else line)
        return "\n".join(lines)

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
        embed = discord.Embed(
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
