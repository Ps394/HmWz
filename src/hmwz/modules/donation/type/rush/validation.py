"""Rush duration, timezone, and start-time validation."""

from __future__ import annotations

import re
from datetime import datetime, tzinfo

from hmwz.ui.components.timestamp_input import (
    parse_timestamp,
    parse_local_datetime,
    resolve_timezone,
)

UTC_OFFSET_PATTERN = re.compile(r"UTC([+-])(\d{1,2})")
COMMON_DONATION_TIMEZONES = (
    ("UTC", "donation.timezone.utc"),
    ("Europe/Berlin", "donation.timezone.berlin"),
    ("Europe/London", "donation.timezone.london"),
    ("Europe/Paris", "donation.timezone.paris"),
    ("Europe/Helsinki", "donation.timezone.helsinki"),
    ("America/New_York", "donation.timezone.new_york"),
    ("America/Chicago", "donation.timezone.chicago"),
    ("America/Denver", "donation.timezone.denver"),
    ("America/Los_Angeles", "donation.timezone.los_angeles"),
    ("America/Phoenix", "donation.timezone.phoenix"),
    ("America/Toronto", "donation.timezone.toronto"),
    ("America/Vancouver", "donation.timezone.vancouver"),
    ("America/Sao_Paulo", "donation.timezone.sao_paulo"),
    ("Asia/Dubai", "donation.timezone.dubai"),
    ("Asia/Kolkata", "donation.timezone.kolkata"),
    ("Asia/Bangkok", "donation.timezone.bangkok"),
    ("Asia/Shanghai", "donation.timezone.shanghai"),
    ("Asia/Singapore", "donation.timezone.singapore"),
    ("Asia/Tokyo", "donation.timezone.tokyo"),
    ("Asia/Seoul", "donation.timezone.seoul"),
    ("Australia/Sydney", "donation.timezone.sydney"),
    ("Pacific/Auckland", "donation.timezone.auckland"),
)
LEGACY_OFFSET_TIMEZONES = {
    -12: "America/Los_Angeles",
    -11: "America/Los_Angeles",
    -10: "America/Los_Angeles",
    -9: "America/Los_Angeles",
    -8: "America/Los_Angeles",
    -7: "America/Denver",
    -6: "America/Chicago",
    -5: "America/New_York",
    -4: "America/New_York",
    -3: "America/Sao_Paulo",
    -2: "America/Sao_Paulo",
    -1: "America/Sao_Paulo",
    0: "UTC",
    1: "Europe/Berlin",
    2: "Europe/Helsinki",
    3: "Europe/Helsinki",
    4: "Asia/Dubai",
    5: "Asia/Kolkata",
    6: "Asia/Kolkata",
    7: "Asia/Bangkok",
    8: "Asia/Shanghai",
    9: "Asia/Tokyo",
    10: "Australia/Sydney",
    11: "Australia/Sydney",
    12: "Pacific/Auckland",
    13: "Pacific/Auckland",
    14: "Pacific/Auckland",
}
COMMON_DONATION_TIMEZONE_NAMES = tuple(
    timezone_name for timezone_name, _translation_key in COMMON_DONATION_TIMEZONES
)


def parse_rush_timestamp(raw: str) -> datetime:
    """Parse a Discord timestamp token or integer Unix seconds as an UTC instant."""
    return parse_timestamp(raw)


def donation_timezone(timezone_name: str) -> tzinfo:
    """Resolve a stored fixed UTC offset or a legacy IANA timezone."""
    return resolve_timezone(timezone_name)


def normalize_donation_timezone(timezone_name: str) -> str:
    """Replace a legacy fixed UTC offset with a commonly used regional zone."""
    match = UTC_OFFSET_PATTERN.fullmatch(timezone_name)
    if match is None:
        return timezone_name
    hours = int(match.group(2))
    if match.group(1) == "-":
        hours = -hours
    if not -12 <= hours <= 14 or (hours == 0 and match.group(1) == "-"):
        raise ValueError("The saved UTC offset is outside the supported range.")
    return LEGACY_OFFSET_TIMEZONES[hours]


def donation_timezone_translation_key(timezone_name: str) -> str:
    """Return the localized display key for a common timezone."""
    timezone_name = normalize_donation_timezone(timezone_name)
    return dict(COMMON_DONATION_TIMEZONES).get(
        timezone_name, "donation.timezone.custom"
    )


def parse_hours(raw: str) -> int:
    """Parse a positive whole-number duration expressed in hours."""
    match = re.fullmatch(r"\s*(\d+)\s*h?\s*", raw, re.IGNORECASE)
    if match is None or int(match.group(1)) <= 0:
        raise ValueError("Hour values must be positive whole numbers.")
    return int(match.group(1))


def parse_rush_start(
    date_value: str, time_value: str, timezone_name: str = "UTC"
) -> datetime:
    """Parse a Rush start in its selected timezone and return it in UTC."""
    date_value = date_value.strip()
    time_value = time_value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value) is None:
        raise ValueError("Rush start date must use YYYY-MM-DD.")
    if re.fullmatch(r"\d{2}:\d{2}", time_value) is None:
        raise ValueError("Rush start time must use HH:MM.")
    return parse_local_datetime(f"{date_value} {time_value}", timezone_name)
