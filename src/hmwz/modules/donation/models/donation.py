"""Immutable donation entries and aggregates."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DonationRecord:
    """A persisted donation entry."""

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
