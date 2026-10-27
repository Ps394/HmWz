from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

DonationKind = Literal["simple", "time_reduction"]
DonationInputMode = Literal["free", "choice"]
DEFAULT_DONATION_CHOICES = ("10000", "100000", "1000000", "8000000")


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
    show_ranking: bool = True
    rush_start_at: datetime | None = None
    current_cycle: int = 1
    history_message_id: int | None = None
    timezone_name: str = "UTC"
    show_donations: bool = True
    donations_enabled: bool = True
    export_channel_id: int | None = None


@dataclass(frozen=True, slots=True)
class DonationRecord:
    """A persisted donation entry represented as domain data."""

    member_id: int
    member_name: str
    amount: Decimal
    unit: str
    time_reduction: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class DonationSummary:
    """Aggregate donation count and time reduction for a channel."""

    donation_count: int
    time_reduction_hours: int


@dataclass(frozen=True, slots=True)
class DonationRank:
    """A donor's aggregate amount, count, and time savings."""

    member_id: int
    member_name: str
    amount: Decimal
    donation_count: int
    time_reduction_hours: int = 0
