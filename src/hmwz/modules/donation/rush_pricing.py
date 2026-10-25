from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

RUSH_DURATIONS_HOURS: tuple[int, ...] = (1, 8, 24)
RUSH_BUTTON_DURATIONS_HOURS: tuple[int, ...] = (24, 8, 1)
RUSH_ZONE_BOUNDARIES_HOURS: tuple[int, ...] = (72, 144)
RUSH_ZONE_24H_PRICES: tuple[Decimal, ...] = (
    Decimal(667),
    Decimal(1334),
    Decimal(2001),
)
RUSH_PERIOD_DURATION = timedelta(days=9)
RUSH_DONATION_CUTOFF = RUSH_PERIOD_DURATION - timedelta(hours=24)


def available_rush_durations(
    *,
    started_at: datetime,
    now: datetime,
    accelerated_hours: int,
) -> tuple[int, ...]:
    """Return donation durations that keep the Rush at least 24 hours from its end."""
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
) -> bool:
    """Return whether any donation duration can still be offered."""
    return bool(
        available_rush_durations(
            started_at=started_at,
            now=now,
            accelerated_hours=accelerated_hours,
        )
    )


def rush_donation_cost(
    *,
    started_at: datetime,
    now: datetime,
    duration_hours: int,
    accelerated_hours: int = 0,
) -> Decimal:
    """Calculate a prorated, whole-crystal cost for a duration across price zones."""
    if duration_hours not in RUSH_DURATIONS_HOURS:
        raise ValueError("Rush duration must be 1, 8, or 24 hours.")
    if started_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Rush start and current time must be timezone-aware.")
    if accelerated_hours < 0:
        raise ValueError("Previously donated Rush hours cannot be negative.")

    elapsed_hours = (
        Decimal(str((now - started_at).total_seconds())) / Decimal(3600)
        + accelerated_hours
    )
    if elapsed_hours < 0:
        raise ValueError("Rush donations cannot be priced before the start time.")

    donation_end = elapsed_hours + duration_hours
    zone_index = sum(
        elapsed_hours >= boundary for boundary in RUSH_ZONE_BOUNDARIES_HOURS
    )
    base_price = (
        RUSH_ZONE_24H_PRICES[zone_index] * duration_hours / Decimal(24)
    ).to_integral_value(rounding=ROUND_CEILING)
    if zone_index == len(RUSH_ZONE_BOUNDARIES_HOURS):
        return base_price

    next_boundary = Decimal(RUSH_ZONE_BOUNDARIES_HOURS[zone_index])
    if donation_end <= next_boundary:
        return base_price

    hours_in_next_zone = min(donation_end - next_boundary, Decimal(duration_hours))
    started_hours_in_next_zone = hours_in_next_zone.to_integral_value(
        rounding=ROUND_CEILING
    )
    adjusted_price = base_price * (
        Decimal(1) + started_hours_in_next_zone / Decimal(24)
    )
    return adjusted_price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def rush_donation_prices(
    *,
    started_at: datetime,
    now: datetime,
    accelerated_hours: int,
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
        )
    }
