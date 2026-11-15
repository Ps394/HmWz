"""Qs phase signup model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemberSignup:
    """One Discord member's selected identity for a phase signup."""

    member_id: int
    game_account: str | None
