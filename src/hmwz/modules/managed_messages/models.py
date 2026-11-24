"""Data models for bot-managed Discord messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ManagedTargetKind = Literal["channel", "thread"]


@dataclass(frozen=True, slots=True)
class ManagedMessage:
    """Persisted location and payload for one bot-managed Discord message."""

    guild_id: int
    managed_id: str
    channel_id: int
    message_id: int | None
    content: str | None = None
    embeds: tuple[dict[str, object], ...] = ()
    target_kind: ManagedTargetKind = "channel"
    attachment_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ManagedThread:
    """Persisted thread mapping and message location for one managed message."""

    guild_id: int
    managed_id: str
    thread_id: int
    message_id: int | None
