"""Data model for persisted guild overview content."""

from __future__ import annotations

from dataclasses import dataclass

from .button import OverviewButton


@dataclass(frozen=True, slots=True)
class Overview:
    """Persisted content and Discord message location for one overview."""

    guild_id: int
    overview_id: str
    channel_id: int
    message_id: int | None
    title: str
    description: str
    buttons: tuple[OverviewButton, ...] = ()
