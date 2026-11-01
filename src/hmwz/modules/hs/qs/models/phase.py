"""Qs phase records and local schedule validation."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from hmwz.ui.components.timestamp_input import parse_local_datetime, resolve_timezone

from .constants import MIN_PHASE_COUNT, PHASE_COUNT, PHASE_SECONDS


def phase_starts(
    date: str,
    hours: tuple[int, ...],
    timezone: str,
    *,
    eruption_start: int | None = None,
) -> tuple[int, ...]:
    """Resolve local phase hours, rolling earlier hours onto the next calendar day."""
    if not MIN_PHASE_COUNT <= len(hours) <= PHASE_COUNT or any(
        not 0 <= hour <= 23 for hour in hours
    ):
        raise ValueError("Qs requires four or five start hours between 0 and 23.")
    if eruption_start is None:
        return tuple(
            int(parse_local_datetime(f"{date} {hour:02}:00", timezone).timestamp())
            for hour in hours
        )
    local_start = datetime.fromtimestamp(eruption_start, resolve_timezone(timezone))
    starts = []
    for hour in hours:
        day = local_start.date()
        if (hour, 0, 0, 0) < (
            local_start.hour,
            local_start.minute,
            local_start.second,
            local_start.microsecond,
        ):
            day += timedelta(days=1)
        starts.append(
            int(
                parse_local_datetime(
                    f"{day.isoformat()} {hour:02}:00", timezone
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
