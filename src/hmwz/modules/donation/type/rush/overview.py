"""Rush-specific time fields for donation overviews."""

from datetime import UTC, datetime

import discord

from hmwz.i18n import t

from .pricing import RUSH_PERIOD_DURATION, rush_end_at


def add_time_fields(
    embed: discord.Embed,
    guild: discord.Guild,
    *,
    started_at: datetime,
    accelerated_hours: int,
    target_at: datetime | None = None,
) -> None:
    """Display the Rush start, nominal duration, and accelerated end time."""
    if accelerated_hours < 0:
        raise ValueError("Accelerated hours cannot be negative.")
    start_utc = started_at.astimezone(UTC)
    end_utc = rush_end_at(started_at, accelerated_hours)
    embed.add_field(
        name=t(guild, "donation.type.rush.overview.start"),
        value=discord.utils.format_dt(start_utc, "F"),
        inline=True,
    )
    embed.add_field(
        name=t(guild, "donation.type.rush.overview.duration"),
        value=t(
            guild,
            "donation.type.rush.duration",
            days=RUSH_PERIOD_DURATION.days,
            hours=int(RUSH_PERIOD_DURATION.total_seconds() // 3600),
        ),
        inline=True,
    )
    embed.add_field(
        name=t(guild, "donation.type.rush.overview.end"),
        value=discord.utils.format_dt(end_utc, "F"),
        inline=True,
    )
    if target_at is not None:
        add_target_field(embed, guild, target_at, end_utc)


def add_target_field(
    embed: discord.Embed,
    context: discord.Guild | discord.Interaction,
    target_at: datetime,
    end_at: datetime,
) -> None:
    """Highlight the target separately and explicitly mark when it is reached."""
    embed.add_field(
        name=t(context, "donation.type.rush.overview.target"),
        value=f"**{discord.utils.format_dt(target_at, 'F')}**\n"
        + t(
            context,
            "donation.type.rush.overview.target_reached"
            if end_at <= target_at
            else "donation.type.rush.overview.target_pending",
        ),
        inline=False,
    )
