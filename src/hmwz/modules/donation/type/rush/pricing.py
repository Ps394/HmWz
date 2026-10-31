"""Game-accurate prices and availability for Rush donations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from typing import Final

RUSH_DURATIONS_HOURS: tuple[int, ...] = (1, 8, 24)
RUSH_BUTTON_DURATIONS_HOURS: tuple[int, ...] = (24, 8, 1)
RUSH_BASE_PRICES: Final = {1: Decimal(28), 8: Decimal(223), 24: Decimal(667)}
RUSH_PERIOD_DURATION = timedelta(days=9)
RUSH_DONATION_CUTOFF = RUSH_PERIOD_DURATION - timedelta(hours=24)


def rush_end_at(started_at: datetime, accelerated_hours: int = 0) -> datetime:
    """Return the actual end after subtracting all donated hours."""
    if started_at.utcoffset() is None or accelerated_hours < 0:
        raise ValueError("Rush start must be timezone-aware and hours non-negative.")
    return (
        started_at.astimezone(UTC)
        + RUSH_PERIOD_DURATION
        - timedelta(hours=accelerated_hours)
    )


def validate_rush_target(
    started_at: datetime, target_at: datetime, accelerated_hours: int = 0
) -> None:
    """Require an attainable whole-hour target between start and current end."""
    if target_at.utcoffset() is None:
        raise ValueError("Rush target must be timezone-aware.")
    end = rush_end_at(started_at, accelerated_hours)
    if target_at <= started_at or target_at > end:
        raise ValueError(
            "Rush target must be after start and no later than current end."
        )
    if (rush_end_at(started_at) - target_at).total_seconds() % 3600:
        raise ValueError("Rush target must differ from the nominal end by whole hours.")


def available_rush_durations(
    *,
    started_at: datetime,
    now: datetime,
    accelerated_hours: int,
    target_at: datetime | None = None,
) -> tuple[int, ...]:
    """Return durations respecting both the target and the 24-hour cutoff."""
    if started_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Rush start and current time must be timezone-aware.")
    if accelerated_hours < 0:
        raise ValueError("Previously donated Rush hours cannot be negative.")
    if now < started_at:
        return ()

    remaining_hours = (
        Decimal(str((started_at + RUSH_DONATION_CUTOFF - now).total_seconds()))
        / Decimal(3600)
        - accelerated_hours
    )
    if target_at is not None:
        if target_at.utcoffset() is None:
            raise ValueError("Rush target must be timezone-aware.")
        target_hours = Decimal(
            str(
                (rush_end_at(started_at, accelerated_hours) - target_at).total_seconds()
            )
        ) / Decimal(3600)
        remaining_hours = min(remaining_hours, target_hours)
    return tuple(
        hours
        for hours in RUSH_BUTTON_DURATIONS_HOURS
        if Decimal(hours) <= remaining_hours
    )


def is_rush_donation_open(
    started_at: datetime,
    now: datetime,
    *,
    accelerated_hours: int = 0,
    target_at: datetime | None = None,
) -> bool:
    """Return whether any donation duration can still be offered."""
    return bool(
        available_rush_durations(
            started_at=started_at,
            now=now,
            accelerated_hours=accelerated_hours,
            target_at=target_at,
        )
    )


def rush_donation_cost(
    *,
    started_at: datetime,
    now: datetime,
    duration_hours: int,
    accelerated_hours: int = 0,
) -> Decimal:
    """Price a donation from previously accelerated hours using the game formula.

    Wall-clock time only validates that the Rush has started; it does not
    increase the price. In the 48-72h and 120-144h transition ranges, the
    multiplier increases only if this donation strictly crosses the boundary.
    """
    if duration_hours not in RUSH_DURATIONS_HOURS:
        raise ValueError("Rush duration must be 1, 8, or 24 hours.")
    if started_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Rush start and current time must be timezone-aware.")
    if accelerated_hours < 0:
        raise ValueError("Previously donated Rush hours cannot be negative.")

    if now < started_at:
        raise ValueError("Rush donations cannot be priced before the start time.")
    new_accelerated_hours = accelerated_hours + duration_hours
    if accelerated_hours < 48:
        multiplier = Decimal(1)
    elif accelerated_hours < 72:
        multiplier = Decimal(1)
        if new_accelerated_hours > 72:
            multiplier += Decimal(accelerated_hours - 48) / Decimal(24)
    elif accelerated_hours <= 120:
        multiplier = Decimal(2)
    elif accelerated_hours < 144:
        multiplier = Decimal(2)
        if new_accelerated_hours > 144:
            multiplier += Decimal(accelerated_hours - 120) / Decimal(24)
    else:
        multiplier = Decimal(3)
    return (RUSH_BASE_PRICES[duration_hours] * multiplier).to_integral_value(
        rounding=ROUND_CEILING
    )


def rush_donation_prices(
    *,
    started_at: datetime,
    now: datetime,
    accelerated_hours: int,
    target_at: datetime | None = None,
) -> dict[int, Decimal]:
    """Return the current price for each Rush duration."""
    return {
        duration_hours: rush_donation_cost(
            started_at=started_at,
            now=now,
            duration_hours=duration_hours,
            accelerated_hours=accelerated_hours,
        )
        for duration_hours in available_rush_durations(
            started_at=started_at,
            now=now,
            accelerated_hours=accelerated_hours,
            target_at=target_at,
        )
    }
