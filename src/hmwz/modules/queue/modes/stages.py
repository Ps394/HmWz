from __future__ import annotations

import discord

from ..repository import QueueMode, QueueRepository
from .protocol import QueueModeSetup, QueuePool


class StagedQueueMode:
    """Independent participant-pool behavior for a staged queue."""

    mode: QueueMode = "stages"

    def validate_setup(self, setup: QueueModeSetup) -> bool:
        return (
            1 <= setup.stage_count <= 24
            and len(setup.stage_prefix) <= 78
            and setup.stage_labels
            == tuple(
                f"{setup.stage_prefix}{stage_number}"
                for stage_number in range(1, setup.stage_count + 1)
            )
            and all(len(label) <= 80 for label in setup.stage_labels)
            and all(
                "\n" not in label and "\r" not in label for label in setup.stage_labels
            )
        )

    async def get_pools(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        *,
        max_players: int,
    ) -> tuple[QueuePool, ...]:
        stages = await repository.get_stages(guild=guild, channel_id=channel_id)
        pools: list[QueuePool] = []
        for stage in stages:
            members = await repository.get_members(
                guild=guild,
                channel_id=channel_id,
                stage_index=stage.index,
            )
            pools.append(QueuePool(stage.index, stage.name, members, max_players))
        return tuple(pools)

    async def join(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        member_id: int,
        pool_index: int,
        joined_at: float,
    ) -> bool:
        return await repository.join(
            guild=guild,
            channel_id=channel_id,
            member_id=member_id,
            joined_at=joined_at,
            stage_index=pool_index,
        )

    async def leave(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        member_id: int,
        pool_index: int,
    ) -> bool:
        members = await repository.get_members(
            guild=guild,
            channel_id=channel_id,
            stage_index=pool_index,
        )
        if member_id not in members:
            return False
        return await repository.leave(
            guild=guild, channel_id=channel_id, member_id=member_id
        )
