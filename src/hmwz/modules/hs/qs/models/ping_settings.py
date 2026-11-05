"""Channel-scoped switches for automatic Qs notifications."""

from dataclasses import dataclass
from typing import Final, Literal

PingEvent = Literal["start", "end", "goal", "phase_start"]
PING_EVENTS: Final[tuple[PingEvent, ...]] = ("start", "end", "goal", "phase_start")


@dataclass(frozen=True, slots=True)
class PingSettings:
    """Enable each automatic notification independently; manual pings are unaffected."""

    start: bool = True
    end: bool = True
    goal: bool = True
    phase_start: bool = True

    def is_enabled(self, event: PingEvent) -> bool:
        """Return the draft or persisted state of one automatic notification."""
        return {
            "start": self.start,
            "end": self.end,
            "goal": self.goal,
            "phase_start": self.phase_start,
        }[event]
