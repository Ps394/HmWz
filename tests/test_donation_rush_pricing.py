from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import discord
import pytest

from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.repository import DonationChannel, DonationType
from hmwz.modules.donation.rush_pricing import (
    RUSH_DONATION_CUTOFF,
    is_rush_donation_open,
    rush_donation_cost,
)
from hmwz.modules.donation.validation import parse_rush_start


def test_rush_cost_prorates_a_donation_across_price_zones() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = start + timedelta(hours=60)

    assert rush_donation_cost(started_at=start, now=now, duration_hours=24) == Decimal(
        1001
    )
    assert rush_donation_cost(
        started_at=start,
        now=start + timedelta(hours=68),
        duration_hours=8,
    ) == Decimal(260)


def test_rush_cost_uses_active_zone_after_the_second_boundary() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert rush_donation_cost(
        started_at=start,
        now=start + timedelta(hours=144),
        duration_hours=8,
    ) == Decimal(667)
    assert rush_donation_cost(
        started_at=start,
        now=start + timedelta(hours=192),
        duration_hours=1,
    ) == Decimal(84)


def test_rush_cost_rounds_partial_crossing_hours_up() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert rush_donation_cost(
        started_at=start,
        now=start + timedelta(hours=71, minutes=30),
        duration_hours=8,
    ) == Decimal(297)


def test_rush_cutoff_is_inclusive_at_eight_days() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert is_rush_donation_open(start, start)
    assert is_rush_donation_open(start, start + RUSH_DONATION_CUTOFF)
    assert not is_rush_donation_open(
        start, start + RUSH_DONATION_CUTOFF + timedelta(microseconds=1)
    )
    assert not is_rush_donation_open(start, start - timedelta(seconds=1))


def test_parse_rush_start_uses_berlin_timezone() -> None:
    parsed = parse_rush_start("2026-06-01", "12:30")

    assert parsed.tzinfo == ZoneInfo("Europe/Berlin")
    assert parsed.utcoffset() == timedelta(hours=2)


def test_parse_rush_start_rejects_nonexistent_daylight_saving_time() -> None:
    with pytest.raises(ValueError):
        parse_rush_start("2026-03-29", "02:30")


@pytest.mark.asyncio
async def test_confirmed_rush_donation_records_the_quoted_price_in_current_cycle() -> (
    None
):
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
    )
    repository = SimpleNamespace(
        get_channel=AsyncMock(return_value=configuration),
        get_type=AsyncMock(return_value=donation_type),
        add_donation=AsyncMock(return_value=True),
    )
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=guild,
            donations=repository,
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
    ) == (True, True)
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
