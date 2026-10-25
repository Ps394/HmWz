from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import discord

from ..repository import QueueMode, QueueRepository


@dataclass(frozen=True, slots=True)
class QueueModeSetup:
    stage_count: int
    stage_prefix: str
    stage_labels: tuple[str, ...]
    seasons: tuple[str, ...]
    season_goal_limit: int
    season_goal_description: str
    season_start_date: str | None
    timezone: str
    season_duration_hours: int
    season_tasks: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class QueuePool:
    index: int
    label: str
    members: tuple[int, ...]
    capacity: int | None = None
    progress: str | None = None


class QueueModeProtocol(Protocol):
    """Mode-specific operations used by the queue coordinator."""

    mode: QueueMode

    def validate_setup(self, setup: QueueModeSetup) -> bool:
        """Return whether mode-specific settings are valid."""
        ...

    async def get_pools(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        *,
        max_players: int,
    ) -> tuple[QueuePool, ...]:
        """Load the participant pools shown for this queue mode."""
        ...

    async def join(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        member_id: int,
        pool_index: int,
        joined_at: float,
    ) -> bool:
        """Add a participant to one mode-specific pool."""
        ...

    async def leave(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        member_id: int,
        pool_index: int,
    ) -> bool:
        """Remove a participant from one mode-specific pool."""
        ...
