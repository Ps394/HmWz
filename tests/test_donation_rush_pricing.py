import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.models import DonationChannel, DonationType
from hmwz.modules.donation.type.rush.pricing import (
    RUSH_PERIOD_DURATION,
    RUSH_DONATION_CUTOFF,
    available_rush_durations,
    is_rush_donation_open,
    rush_donation_cost,
    rush_donation_prices,
    rush_end_at,
)
from hmwz.modules.donation.type.rush.validation import (
    parse_rush_start,
    normalize_donation_timezone,
)


def test_rush_cost_ignores_elapsed_wall_clock_time() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = start + timedelta(hours=60)

    assert rush_donation_cost(started_at=start, now=now, duration_hours=24) == Decimal(
        667
    )
    assert rush_donation_cost(
        started_at=start,
        now=start + timedelta(hours=68),
        duration_hours=8,
    ) == Decimal(223)


def test_rush_cost_uses_active_zone_after_the_second_boundary() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert rush_donation_cost(
        started_at=start,
        now=start + timedelta(hours=144),
        duration_hours=8,
        accelerated_hours=144,
    ) == Decimal(669)
    assert rush_donation_cost(
        started_at=start,
        now=start + timedelta(hours=192),
        duration_hours=1,
        accelerated_hours=144,
    ) == Decimal(84)


def test_rush_cost_does_not_round_elapsed_hours_into_the_price() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert rush_donation_cost(
        started_at=start,
        now=start + timedelta(hours=71, minutes=30),
        duration_hours=8,
    ) == Decimal(223)


def test_previous_donations_advance_rush_price_progression() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = start + timedelta(hours=60)

    assert rush_donation_cost(
        started_at=start,
        now=now,
        duration_hours=24,
        accelerated_hours=0,
    ) == Decimal(667)
    assert rush_donation_cost(
        started_at=start,
        now=now,
        duration_hours=24,
        accelerated_hours=72,
    ) == Decimal(1334)


def test_rush_prices_use_independent_option_base_prices() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert rush_donation_prices(
        started_at=start,
        now=start,
        accelerated_hours=0,
    ) == {
        24: Decimal(667),
        8: Decimal(223),
        1: Decimal(28),
    }
    assert rush_donation_prices(
        started_at=start,
        now=start,
        accelerated_hours=72,
    ) == {
        24: Decimal(1334),
        8: Decimal(446),
        1: Decimal(56),
    }


@pytest.mark.parametrize(
    ("accelerated_hours", "prices"),
    [
        (0, (667, 223, 28)),
        (47, (667, 223, 28)),
        (48, (667, 223, 28)),
        (50, (723, 223, 28)),
        (58, (945, 223, 28)),
        (64, (1112, 223, 28)),
        (65, (1140, 381, 28)),
        (71, (1307, 437, 28)),
        (72, (1334, 446, 56)),
        (119, (1334, 446, 56)),
        (120, (1334, 446, 56)),
        (122, (1390, 446, 56)),
        (136, (1779, 446, 56)),
        (137, (1807, 604, 56)),
        (143, (1974, 660, 56)),
        (144, (2001, 669, 84)),
        (192, (2001, 669, 84)),
    ],
)
def test_rush_cost_matches_reference_formula_at_ramps_and_boundaries(
    accelerated_hours: int, prices: tuple[int, int, int]
) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert tuple(
        rush_donation_cost(
            started_at=start,
            now=start,
            duration_hours=duration,
            accelerated_hours=accelerated_hours,
        )
        for duration in (24, 8, 1)
    ) == tuple(Decimal(price) for price in prices)


@pytest.mark.parametrize("hours", range(217))
def test_every_integer_hour_matches_exact_reference_arithmetic(hours: int) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for duration, base in ((24, 667), (8, 223), (1, 28)):
        if hours >= 144:
            numerator = 72
        elif hours >= 72:
            numerator = 48
            if hours > 120 and hours + duration > 144:
                numerator += hours - 120
        else:
            numerator = 24
            if hours >= 48 and hours + duration > 72:
                numerator += hours - 48
        expected = (base * numerator + 23) // 24
        assert rush_donation_cost(
            started_at=start,
            now=start,
            duration_hours=duration,
            accelerated_hours=hours,
        ) == Decimal(expected)


@pytest.mark.parametrize(
    ("duration", "hours", "naive", "before_start"),
    [
        (2, 0, False, False),
        (24, -1, False, False),
        (24, 0, True, False),
        (24, 0, False, True),
    ],
)
def test_rush_cost_rejects_invalid_inputs(
    duration: int, hours: int, naive: bool, before_start: bool
) -> None:
    start = datetime(2026, 1, 1, tzinfo=None if naive else timezone.utc)
    now = start - timedelta(seconds=1) if before_start else start
    with pytest.raises(ValueError):
        rush_donation_cost(
            started_at=start, now=now, duration_hours=duration, accelerated_hours=hours
        )


def test_rush_stop_is_exactly_nine_days_after_start() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert RUSH_PERIOD_DURATION == timedelta(days=9)
    assert start + RUSH_PERIOD_DURATION == start + timedelta(days=9)

    assert is_rush_donation_open(start, start)
    assert not is_rush_donation_open(
        start, start + RUSH_PERIOD_DURATION - timedelta(hours=24)
    )
    assert not is_rush_donation_open(start, start - timedelta(seconds=1))


def test_available_rush_durations_respect_stop_minus_24_hours() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert available_rush_durations(
        started_at=start,
        now=start + timedelta(hours=168),
        accelerated_hours=0,
    ) == (24, 8, 1)
    assert available_rush_durations(
        started_at=start,
        now=start + timedelta(hours=168),
        accelerated_hours=8,
    ) == (8, 1)
    assert available_rush_durations(
        started_at=start,
        now=start + timedelta(hours=191),
        accelerated_hours=0,
    ) == (1,)
    assert (
        available_rush_durations(
            started_at=start,
            now=start + RUSH_DONATION_CUTOFF,
            accelerated_hours=0,
        )
        == ()
    )


def test_parse_rush_start_uses_utc_timezone() -> None:
    parsed = parse_rush_start("2026-06-01", "12:30")

    assert parsed.utcoffset() == timedelta(0)


def test_parse_rush_start_accepts_any_valid_utc_time() -> None:
    assert parse_rush_start("2026-03-29", "02:30") == datetime(
        2026, 3, 29, 2, 30, tzinfo=timezone.utc
    )


def test_parse_rush_start_converts_selected_timezone_to_utc() -> None:
    assert parse_rush_start("2026-06-01", "12:30", "America/New_York") == datetime(
        2026, 6, 1, 16, 30, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    ("timezone_name", "expected_start"),
    (
        ("UTC+1", datetime(2026, 6, 1, 11, tzinfo=timezone.utc)),
        ("UTC-4", datetime(2026, 6, 1, 16, tzinfo=timezone.utc)),
        ("UTC-12", datetime(2026, 6, 2, 0, tzinfo=timezone.utc)),
        ("UTC+14", datetime(2026, 5, 31, 22, tzinfo=timezone.utc)),
    ),
)
def test_parse_rush_start_supports_fixed_utc_offsets(
    timezone_name: str, expected_start: datetime
) -> None:
    assert parse_rush_start("2026-06-01", "12:00", timezone_name) == expected_start


@pytest.mark.parametrize("timezone_name", ("UTC-13", "UTC+15", "UTC-0", "UTC+"))
def test_parse_rush_start_rejects_invalid_fixed_utc_offsets(
    timezone_name: str,
) -> None:
    with pytest.raises(ValueError):
        parse_rush_start("2026-06-01", "12:00", timezone_name)


@pytest.mark.parametrize(
    ("stored_timezone", "expected_timezone"),
    (("UTC+1", "Europe/Berlin"), ("UTC-5", "America/New_York"), ("UTC+0", "UTC")),
)
def test_legacy_utc_timezone_settings_normalize_to_common_zones(
    stored_timezone: str, expected_timezone: str
) -> None:
    assert normalize_donation_timezone(stored_timezone) == expected_timezone


@pytest.mark.parametrize(
    ("date_value", "time_value"),
    (("2026-03-08", "02:30"), ("2026-11-01", "01:30")),
)
def test_parse_rush_start_rejects_daylight_saving_gaps_and_ambiguities(
    date_value: str, time_value: str
) -> None:
    with pytest.raises(ValueError):
        parse_rush_start(date_value, time_value, "America/New_York")


@pytest.mark.asyncio
@pytest.mark.parametrize("target_remaining", [None, 24, 1, 0])
async def test_confirmed_rush_donation_records_the_quoted_price_in_current_cycle(
    target_remaining: int | None,
) -> None:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=60)
    guild = cast(discord.Guild, SimpleNamespace(id=123))
    member = Mock(spec=discord.Member)
    member.id = 456
    donation_type = DonationType(
        name="Rush donation",
        kind="time_reduction",
        unit="crystals",
        input_mode="free",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
    )
    configuration = DonationChannel(
        channel_id=789,
        overview_message_id=None,
        ranking_message_id=None,
        title="Rush",
        description="",
        goal_hours=216,
        rush_start_at=start,
        current_cycle=2,
        target_at=(
            rush_end_at(start, target_remaining)
            if target_remaining is not None
            else None
        ),
    )
    repository = SimpleNamespace(
        get_channel=AsyncMock(return_value=configuration),
        get_type=AsyncMock(return_value=donation_type),
        get_summary=AsyncMock(return_value=SimpleNamespace(time_reduction_hours=0)),
        add_donation=AsyncMock(return_value=True),
    )
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=guild,
            donations=repository,
            _cycle_locks={},
            _cycle_lock=lambda channel_id: asyncio.Lock(),
            compose_overview=AsyncMock(return_value=True),
        ),
    )
    interaction = cast(discord.Interaction, SimpleNamespace(guild=guild, user=member))
    quote_time = now - timedelta(minutes=1)
    cost = rush_donation_cost(started_at=start, now=quote_time, duration_hours=24)

    assert await DonationModule.record_rush_donation(
        module,
        interaction,
        789,
        donation_type,
        24,
        cost,
        2,
        start,
        quote_time,
    ) == ((True, True) if target_remaining in (None, 24) else (False, False))
    if target_remaining in (1, 0):
        repository.add_donation.assert_not_awaited()
        module.compose_overview.assert_not_awaited()
        return
    repository.add_donation.assert_awaited_once_with(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=donation_type,
        amount=cost,
        time_reduction="24h",
        cycle=2,
        rush_quoted_at=quote_time,
    )
