"""Destroyed-base report records."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BaseReport:
    """One member's unique destroyed-base report for the event."""

    member_id: int
    phase_index: int
    display_name: str
    created_at: int
