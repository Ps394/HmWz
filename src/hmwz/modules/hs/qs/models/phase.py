"""Qs phase records and local schedule validation."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from hmwz.ui.components.timestamp_input import parse_local_datetime, resolve_timezone

from .constants import PHASE_COUNT, PHASE_SECONDS


def phase_starts(
    date: str,
    hours: tuple[int, ...],
    timezone: str,
    *,
    minutes: tuple[int, ...] | None = None,
    eruption_start: int | None = None,
) -> tuple[int, ...]:
    """Resolve local phase times, rolling earlier times onto the next day."""
    minutes = minutes if minutes is not None else (0,) * len(hours)
    if (
        len(hours) != PHASE_COUNT
        or len(minutes) != PHASE_COUNT
        or any(not 0 <= hour <= 23 for hour in hours)
        or any(not 0 <= minute <= 59 for minute in minutes)
    ):
        raise ValueError("Qs requires five start times with valid hours and minutes.")
    if eruption_start is None:
        return tuple(
            int(
                parse_local_datetime(
                    f"{date} {hour:02}:{minute:02}", timezone
                ).timestamp()
            )
            for hour, minute in zip(hours, minutes, strict=True)
        )
    local_start = datetime.fromtimestamp(eruption_start, resolve_timezone(timezone))
    starts = []
    for hour, minute in zip(hours, minutes, strict=True):
        day = local_start.date()
        if (hour, minute, 0, 0) < (
            local_start.hour,
            local_start.minute,
            local_start.second,
            local_start.microsecond,
        ):
            day += timedelta(days=1)
        starts.append(
            int(
                parse_local_datetime(
                    f"{day.isoformat()} {hour:02}:{minute:02}", timezone
                ).timestamp()
            )
        )
    return tuple(starts)


@dataclass(frozen=True, slots=True)
class Phase:
    """A configured phase with its persistent Discord thread and message."""

    index: int
    starts_at: int
    thread_id: int | None
    message_id: int | None
    duration_hours: int = 2
    goal_notified: bool = False
    members_message_id: int | None = None
    start_notified: bool = False

    @property
    def ends_at(self) -> int:
        """Return the end after the configured elapsed hours, including midnight."""
        return self.starts_at + self.duration_hours * (PHASE_SECONDS // 2)
