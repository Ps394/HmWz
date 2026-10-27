from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def local_datetime_timestamp(
    local_date: date, local_time: time, timezone_name: str
) -> float | None:
    """Convert a valid, unambiguous local wall time to a Unix timestamp."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None

    local_value = datetime.combine(local_date, local_time, tzinfo=zone)
    round_trip = local_value.astimezone(timezone.utc).astimezone(zone)
    if round_trip.replace(tzinfo=None) != local_value.replace(tzinfo=None):
        return None
    if local_value.replace(fold=1).utcoffset() != local_value.utcoffset():
        return None
    return local_value.timestamp()


def phase_schedule(
    start_date: str,
    timezone_name: str,
    phase_hours: tuple[tuple[str, int], ...],
    start_time: str = "00:00",
) -> tuple[float, float, tuple[tuple[float, float], ...]] | None:
    """Validate a 24-hour eruption and its non-overlapping local-time phases."""
    if not 3 <= len(phase_hours) <= 6:
        return None
    if len({hour for hour, _ in phase_hours}) != len(phase_hours):
        return None
    try:
        parsed_date = date.fromisoformat(start_date)
    except ValueError:
        return None
    if parsed_date.isoformat() != start_date:
        return None

    if (
        len(start_time) != 5
        or start_time[2] != ":"
        or not start_time[:2].isdigit()
        or not start_time[3:].isdigit()
        or int(start_time[:2]) > 23
        or int(start_time[3:]) > 59
    ):
        return None
    eruption_start = local_datetime_timestamp(
        parsed_date,
        time(hour=int(start_time[:2]), minute=int(start_time[3:])),
        timezone_name,
    )
    if eruption_start is None:
        return None
    eruption_end = eruption_start + timedelta(hours=24).total_seconds()
    phases: list[tuple[float, float]] = []
    for hour, duration in phase_hours:
        if (
            len(hour) != 5
            or hour[2:] != ":00"
            or not hour[:2].isdigit()
            or not 0 <= int(hour[:2]) <= 23
            or duration not in (1, 2, 3)
        ):
            return None
        start = local_datetime_timestamp(
            parsed_date,
            time(hour=int(hour[:2])),
            timezone_name,
        )
        if start is None:
            return None
        end = start + timedelta(hours=duration).total_seconds()
        if start < eruption_start or end > eruption_end:
            return None
        phases.append((start, end))

    phases.sort()
    if any(current[0] < previous[1] for previous, current in zip(phases, phases[1:])):
        return None
    return eruption_start, eruption_end, tuple(phases)
