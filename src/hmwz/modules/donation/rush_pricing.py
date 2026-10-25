from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

RUSH_DURATIONS_HOURS: tuple[int, ...] = (1, 8, 24)
RUSH_ZONE_BOUNDARIES_HOURS: tuple[int, ...] = (72, 144)
RUSH_ZONE_PRICES: dict[int, tuple[Decimal, Decimal, Decimal]] = {
    1: (Decimal(28), Decimal(56), Decimal(84)),
    8: (Decimal(223), Decimal(445), Decimal(667)),
    24: (Decimal(667), Decimal(1334), Decimal(2001)),
}
RUSH_PERIOD_DURATION = timedelta(days=9)
RUSH_DONATION_CUTOFF = timedelta(days=8)


def is_rush_donation_open(started_at: datetime, now: datetime) -> bool:
    """Return whether donations are allowed in the first eight days of a rush."""
    return started_at <= now <= started_at + RUSH_DONATION_CUTOFF


def rush_zone_index(started_at: datetime, now: datetime) -> int | None:
    """Return the current zero-based Rush price zone, if the period has started."""
    if now < started_at or now > started_at + RUSH_DONATION_CUTOFF:
        return None

    elapsed_hours = (now - started_at).total_seconds() / 3600
    for zone_index, boundary in enumerate(RUSH_ZONE_BOUNDARIES_HOURS):
        if elapsed_hours < boundary:
            return zone_index
    return len(RUSH_ZONE_BOUNDARIES_HOURS)


def rush_donation_cost(
    *,
    started_at: datetime,
    now: datetime,
    duration_hours: int,
) -> Decimal:
    """Calculate a prorated, whole-crystal cost for a duration across price zones."""
    if duration_hours not in RUSH_ZONE_PRICES:
        raise ValueError("Rush duration must be 1, 8, or 24 hours.")
    if started_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Rush start and current time must be timezone-aware.")

    elapsed_hours = Decimal(str((now - started_at).total_seconds())) / Decimal(3600)
    if elapsed_hours < 0:
        raise ValueError("Rush donations cannot be priced before the start time.")

    donation_end = elapsed_hours + duration_hours
    zone_prices = RUSH_ZONE_PRICES[duration_hours]
    zone_index = sum(
        elapsed_hours >= boundary for boundary in RUSH_ZONE_BOUNDARIES_HOURS
    )
    base_price = zone_prices[zone_index]
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
