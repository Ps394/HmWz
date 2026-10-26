from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueueConfiguration:
    guild_id: int
    channel_id: int
    title: str
    description: str
    role_id: int
    modal_prompt: str
    message_id: int | None
    destruction_message_id: int | None
    mode: str
    timezone: str
    next_start_at: float | None
    phase_hours: tuple[tuple[str, int], ...]
    remove_role_on_reset: bool
    eruption_start_reminder_enabled: bool
    eruption_start_reminder_minutes: int
    eruption_end_reminder_enabled: bool
    eruption_end_reminder_minutes: int
    phase_start_reminder_enabled: bool
    phase_start_reminder_minutes: int


@dataclass(frozen=True, slots=True)
class Eruption:
    id: int
    guild_id: int
    channel_id: int
    starts_at: float
    ends_at: float
    timezone: str


@dataclass(frozen=True, slots=True)
class QueuePhase:
    id: int
    eruption_id: int
    index: int
    starts_at: float
    ends_at: float
    thread_id: int | None
    message_id: int | None


@dataclass(frozen=True, slots=True)
class PhaseParticipant:
    member_id: int
    joined_at: float


@dataclass(frozen=True, slots=True)
class BaseDestruction:
    member_id: int
    phase_id: int
    confirmed_at: float
    details: str


@dataclass(frozen=True, slots=True)
class QueueReminder:
    eruption_id: int
    phase_id: int | None
    kind: str
    due_at: float
    event_at: float
    attempts: int


@dataclass(frozen=True, slots=True)
class QueueCleanupJob:
    id: int
    guild_id: int
    channel_id: int
    operation: str
    status: str
    payload: str


@dataclass(frozen=True, slots=True)
class QueueCleanupItem:
    kind: str
    parent_id: int | None
    resource_id: int
    status: str
    attempts: int
    last_error: str | None
