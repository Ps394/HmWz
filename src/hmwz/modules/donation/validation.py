from __future__ import annotations

import re
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


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


def parse_rush_start(date_value: str, time_value: str) -> datetime:
    """Parse a Berlin-local Rush start and return it as an aware datetime."""
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
        raise ValueError("Rush start time must use HH:MM in Europe/Berlin.")

    zone = ZoneInfo("Europe/Berlin")
    local_start = datetime.combine(local_date, local_time, tzinfo=zone)
    round_trip = local_start.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if round_trip != local_start.replace(tzinfo=None):
        raise ValueError("The selected local time does not exist in Europe/Berlin.")
    return local_start
