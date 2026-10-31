"""Local calendar input, DST handling, and exact Discord timestamp generation."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.ui.components.timestamp_input import (
    TimestampInput,
    parse_local_datetime,
    resolve_timezone,
)


@pytest.mark.parametrize(
    "raw",
    [
        "31.10.2026 00:32:10",
        "2026-10-31 00:32:10",
        "2026-10-31T00:32:10",
        " <t:1793403130:F> ",
        "1793403130",
    ],
)
@pytest.mark.asyncio
async def test_helper_generates_exact_requested_discord_timestamp(raw: str) -> None:
    field = TimestampInput(
        cast(discord.Guild, SimpleNamespace(locale="de")),
        label="Startzeit",
        timezone_name="Europe/Berlin",
    )
    field._value = raw
    assert field.parse() == datetime(2026, 10, 30, 23, 32, 10, tzinfo=UTC)
    assert field.discord_timestamp() == "<t:1793403130:F>"
    assert "Europe/Berlin" in field.label
    assert "TT.MM.JJJJ" in field.placeholder


@pytest.mark.parametrize(
    ("raw", "zone", "expected"),
    [
        ("2026-06-01 12:00", "Europe/Berlin", datetime(2026, 6, 1, 10, tzinfo=UTC)),
        ("2026-12-01 12:00", "Europe/Berlin", datetime(2026, 12, 1, 11, tzinfo=UTC)),
        ("2026-06-01 12:00", "Asia/Kolkata", datetime(2026, 6, 1, 6, 30, tzinfo=UTC)),
        ("2026-06-01 12:00", "UTC+1", datetime(2026, 6, 1, 11, tzinfo=UTC)),
        ("2026-06-01 12:00", "UTC-4", datetime(2026, 6, 1, 16, tzinfo=UTC)),
        ("<t:1793403130:F>", "Asia/Tokyo", datetime.fromtimestamp(1793403130, UTC)),
    ],
)
def test_local_conversion_supports_summer_time_and_preserves_absolute_inputs(
    raw: str,
    zone: str,
    expected: datetime,
) -> None:
    assert parse_local_datetime(raw, zone) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "tomorrow",
        "2026-02-30 12:00",
        "2026-10-31 24:00",
        "2026-10-31 12:60",
        "2026-10-31 12:00:60",
        "31.13.2026 12:00",
        "2026-10-31",
        "2026-10-31 12:00+01:00",
        "2026-03-29 02:30",
        "2026-10-25 02:30",
        "<t:1793403130:X>",
        "999999999999999999",
    ],
)
def test_invalid_or_ambiguous_local_input_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_local_datetime(raw, "Europe/Berlin")


@pytest.mark.parametrize("zone", ["invalid", "UTC-0", "UTC-00", "UTC+15", "UTC-13"])
def test_invalid_timezone_is_rejected(zone: str) -> None:
    with pytest.raises(ValueError):
        resolve_timezone(zone)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instant",
    [
        datetime(2026, 10, 31, 12, 30, 10, 123456, tzinfo=UTC),
        datetime(2026, 10, 25, 0, 30, tzinfo=UTC),
        datetime(2026, 10, 25, 1, 30, tzinfo=UTC),
    ],
)
async def test_unchanged_default_preserves_exact_instant_even_during_dst_overlap(
    instant: datetime,
) -> None:
    field = TimestampInput(
        cast(discord.Guild, SimpleNamespace(locale="de")),
        label="Start",
        timezone_name="Europe/Berlin",
        value=instant,
    )
    field._value = field.default
    assert field.parse() == instant
    assert len(field.label) <= 45
    if instant.day == 25:
        assert field.default.startswith("<t:")
    else:
        assert field.default == "2026-10-31 13:30:10.123456"
        assert parse_local_datetime(field.default, field.timezone_name) == instant


@pytest.mark.asyncio
async def test_optional_input_clears_and_required_input_rejects_empty() -> None:
    context = cast(discord.Guild, SimpleNamespace(locale="en"))
    field = TimestampInput(context, label="Target", timezone_name="UTC", required=False)
    assert field.parse() is None
    assert field.discord_timestamp() is None
    field = TimestampInput(context, label="Start", timezone_name="UTC")
    with pytest.raises(ValueError):
        field.parse()
    with pytest.raises(ValueError):
        TimestampInput(
            context,
            label="Start",
            timezone_name="UTC",
            value=datetime(2026, 1, 1),
        )
