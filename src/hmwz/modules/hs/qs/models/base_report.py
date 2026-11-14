"""Destroyed-base report records."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BaseReport:
    """One account or Discord display-name destroyed-base report."""

    member_id: int
    phase_index: int
    display_name: str
    created_at: int
    game_account: str | None = None
    report_key: str = ""
