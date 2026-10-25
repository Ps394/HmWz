from __future__ import annotations

import discord

from ..repository import QueueMode, QueueRepository
from .protocol import QueueModeSetup, QueuePool


class ContinuousQueueMode:
    """Participant-pool behavior for a continuous queue."""

    mode: QueueMode = "continuous"

    def validate_setup(self, setup: QueueModeSetup) -> bool:
        return True

    async def get_pools(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        *,
        max_players: int,
    ) -> tuple[QueuePool, ...]:
        members = await repository.get_members(guild=guild, channel_id=channel_id)
        return (QueuePool(0, "members", members, max_players),)

    async def join(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        member_id: int,
        pool_index: int,
        joined_at: float,
    ) -> bool:
        if pool_index != 0:
            return False
        return await repository.join(
            guild=guild,
            channel_id=channel_id,
            member_id=member_id,
            joined_at=joined_at,
        )

    async def leave(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        member_id: int,
        pool_index: int,
    ) -> bool:
        if pool_index != 0:
            return False
        return await repository.leave(
            guild=guild, channel_id=channel_id, member_id=member_id
        )
