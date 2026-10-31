"""Persistent channel settings and donation input configuration."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

DonationKind = Literal["simple", "time_reduction"]
DonationInputMode = Literal["free", "choice"]
DEFAULT_DONATION_CHOICES: Final = ("10000", "100000", "1000000", "8000000")


@dataclass(frozen=True, slots=True)
class DonationType:
    """The single donation unit configured for a channel."""

    name: str
    kind: DonationKind
    unit: str
    input_mode: DonationInputMode
    choices: tuple[str, ...]
    time_reductions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DonationChannel:
    """Persistent overview settings for a donation channel."""

    channel_id: int
    overview_message_id: int | None
    ranking_message_id: int | None
    title: str
    description: str
    goal_hours: int | None
    recent_limit: int = 20
    show_ranking: bool = False
    rush_start_at: datetime | None = None
    current_cycle: int = 1
    history_message_id: int | None = None
    timezone_name: str = "UTC"
    show_donations: bool = True
    donations_enabled: bool = True
    export_channel_id: int | None = None
    target_at: datetime | None = None
