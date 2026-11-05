"""Channel-scoped Qs event configuration."""

from dataclasses import dataclass

from .constants import ERUPTION_SECONDS
from .ping_settings import PingSettings


@dataclass(frozen=True, slots=True)
class Configuration:
    """Settings for one Qs event in a text channel."""

    channel_id: int
    role_id: int
    date: str
    message_id: int | None
    bases_message_id: int | None
    eruption_start: int = 0
    start_notified: bool = False
    end_notified: bool = False
    state: str = "active"
    ping_settings: PingSettings = PingSettings()

    @property
    def eruption_end(self) -> int:
        """Return the fixed end after 24 elapsed hours."""
        return self.eruption_start + ERUPTION_SECONDS
