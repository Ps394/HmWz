from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def valid_run_range(min_players: int, max_players: int) -> bool:
    """Return whether Min and Max describe a valid group-size range."""
    return 1 <= min_players <= max_players <= 100


def can_start_early(waiting_count: int, *, min_players: int, max_players: int) -> bool:
    """Return whether a staged queue can open an early-start vote."""
    return min_players <= waiting_count < max_players


def season_start_timestamp(
    start_date: str, season_name: str, timezone_name: str
) -> float | None:
    """Convert a season's local date and hour to a Unix timestamp."""
    try:
        parsed_date = date.fromisoformat(start_date)
        if parsed_date.isoformat() != start_date:
            return None
        if (
            len(season_name) != 5
            or season_name[2:] != ":00"
            or not season_name[:2].isdigit()
            or not 0 <= int(season_name[:2]) <= 23
        ):
            return None
        zone = ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError):
        return None

    local_start = datetime.combine(
        parsed_date,
        time(hour=int(season_name[:2])),
        tzinfo=zone,
    )
    if local_start.astimezone(timezone.utc).astimezone(zone).replace(
        tzinfo=None
    ) != local_start.replace(tzinfo=None):
        return None
    return local_start.timestamp()
