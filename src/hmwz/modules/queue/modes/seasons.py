from __future__ import annotations

import discord

from ..repository import QueueMode, QueueRepository
from ..rules import season_start_timestamp
from .protocol import QueueModeSetup, QueuePool


class SeasonQueueMode:
    """Independent participant-pool behavior for a season queue."""

    mode: QueueMode = "seasons"

    def validate_setup(self, setup: QueueModeSetup) -> bool:
        if (
            not 1 <= len(setup.seasons) <= 6
            or len(set(setup.seasons)) != len(setup.seasons)
            or setup.season_duration_hours not in {12, 24, 36, 48, 60, 72}
            or not 1 <= len(setup.season_tasks) <= 25
            or setup.season_start_date is None
        ):
            return False
        if any(
            not label.strip()
            or len(label.strip()) > 100
            or "\n" in label
            or "\r" in label
            or not 1 <= completion_limit <= 10000
            for label, completion_limit in setup.season_tasks
        ):
            return False
        if len({label.strip().casefold() for label, _ in setup.season_tasks}) != len(
            setup.season_tasks
        ):
            return False
        return all(
            season_start_timestamp(setup.season_start_date, season, setup.timezone)
            is not None
            for season in setup.seasons
        )

    async def get_pools(
        self,
        repository: QueueRepository,
        guild: discord.Guild,
        channel_id: int,
        *,
        max_players: int,
    ) -> tuple[QueuePool, ...]:
        del max_players
        seasons = await repository.get_seasons(guild=guild, channel_id=channel_id)
        pools: list[QueuePool] = []
        for season in seasons:
            members = await repository.get_season_members(
                guild=guild,
                channel_id=channel_id,
                season_index=season.index,
            )
            pools.append(
                QueuePool(
                    season.index,
                    season.name,
                    members,
                )
            )
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
        return await repository.join_season(
            guild=guild,
            channel_id=channel_id,
            season_index=pool_index,
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
        return await repository.leave_season(
            guild=guild,
            channel_id=channel_id,
            season_index=pool_index,
            member_id=member_id,
        )
