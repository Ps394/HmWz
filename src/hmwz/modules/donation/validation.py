from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def donation_timezone(timezone_name: str) -> tzinfo:
    """Resolve a stored fixed UTC offset or a legacy IANA timezone."""
    match = UTC_OFFSET_PATTERN.fullmatch(timezone_name)
    if match is not None:
        offset = int(match.group(2))
        if match.group(1) == "-":
            offset = -offset
        if not -12 <= offset <= 14 or (offset == 0 and match.group(1) == "-"):
            raise ValueError("UTC offset must be between UTC-12 and UTC+14.")
        return timezone(timedelta(hours=offset), name=timezone_name)
    if timezone_name == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("Select a valid timezone.") from error


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


def parse_choices(raw: str) -> tuple[str, ...]:
    """Split semicolon-separated values and reject duplicates or empty entries."""
    choices = tuple(value.strip() for value in raw.split(";"))
    if (
        not choices
        or len(choices) > 25
        or len(set(choices)) != len(choices)
        or any(not choice for choice in choices)
        or any(len(choice) > 100 for choice in choices)
    ):
        raise ValueError("Enter between 1 and 25 unique, semicolon-separated values.")
    return choices


def parse_amount(raw: str) -> Decimal:
    """Parse a positive amount with optional grouped thousands separators."""
    value = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:([.,])\d{2,3})+", value):
        separators = re.findall(r"[.,]", value)
        groups = re.split(r"[.,]", value)
        if len(set(separators)) == 1 and all(
            2 <= len(group) <= 3 for group in groups[1:]
        ):
            value = "".join(groups)
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Donation amount must be numeric.") from error
    if not amount.is_finite() or amount <= 0 or amount.adjusted() > 50:
        raise ValueError("Donation amount must be greater than zero.")
    return amount


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
    try:
        local_date = date.fromisoformat(date_value)
        local_time = time.fromisoformat(time_value)
    except ValueError as error:
        raise ValueError("Enter a date as YYYY-MM-DD and time as HH:MM.") from error
    if local_time.second or local_time.microsecond or local_time.tzinfo is not None:
        raise ValueError("Rush start time must use HH:MM.")

    zone = donation_timezone(timezone_name)

    local_start = datetime.combine(local_date, local_time, tzinfo=zone)
    round_trip = local_start.astimezone(ZoneInfo("UTC")).astimezone(zone)
    if round_trip.replace(tzinfo=None) != local_start.replace(tzinfo=None):
        raise ValueError(f"The selected local time does not exist in {timezone_name}.")
    if local_start.replace(fold=1).utcoffset() != local_start.utcoffset():
        raise ValueError(f"The selected local time is ambiguous in {timezone_name}.")
    return local_start.astimezone(ZoneInfo("UTC"))
