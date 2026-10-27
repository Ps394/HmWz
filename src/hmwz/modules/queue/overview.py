from __future__ import annotations

import discord

from hmwz.i18n import t
from hmwz.ui.embeds import create_embed

from .modes.protocol import QueuePool
from .repository import QueueConfiguration, QueueRepository


class QueueOverview:
    @staticmethod
    async def create_embed(
        guild: discord.Guild,
        configuration: QueueConfiguration,
        repository: QueueRepository,
        pools: tuple[QueuePool, ...],
    ) -> discord.Embed:
        completed = await repository.completed_count(
            guild=guild, channel_id=configuration.channel_id
        )
        embed = create_embed(
            title=configuration.title or t(guild, "queue.overview.default_title"),
            description=(
                configuration.description or t(guild, "queue.overview.description")
            ),
            color=discord.Color.blurple(),
        )
        for pool in pools:
            if configuration.mode in ("stages", "seasons") and not pool.members:
                continue
            waiting = "\n".join(f"<@{member_id}>" for member_id in pool.members)
            if len(waiting) > 1024:
                waiting = waiting[:1018].rsplit("\n", maxsplit=1)[0] + "\n..."
            if configuration.mode == "continuous":
                pool_title = t(guild, "queue.overview.members")
            elif pool.progress is not None:
                pool_title = f"{pool.label} — {pool.progress}"
            elif configuration.mode == "seasons":
                pool_title = (
                    f"{pool.label} — "
                    f"{t(guild, 'queue.season.active_count', count=len(pool.members))}"
                )
            else:
                pool_title = f"{pool.label} ({len(pool.members)} / {pool.capacity})"
            embed.add_field(
                name=pool_title[:256],
                value=waiting or t(guild, "queue.overview.empty"),
                inline=False,
            )
        if configuration.mode == "seasons":
            tasks = await repository.get_season_tasks(
                guild=guild, channel_id=configuration.channel_id
            )
            embed.description = (
                f"{embed.description or ''}\n\n"
                f"**{t(guild, 'queue.season.duration')}: "
                f"{configuration.season_duration_hours} h**"
            )[:4096]
            for offset in range(0, len(tasks), 8):
                task_lines = "\n".join(
                    f"• {task.label[:100]}: {task.completed} / {task.completion_limit}"
                    for task in tasks[offset : offset + 8]
                )
                embed.add_field(
                    name=t(guild, "queue.season.task_progress"),
                    value=task_lines,
                    inline=False,
                )
            return embed
        if configuration.mode == "stages":
            embed.description = (
                f"{embed.description}\n"
                f"**{t(guild, 'queue.overview.range')}: "
                f"{configuration.min_players}–{configuration.max_players}**"
            )
            embed.add_field(
                name=t(guild, "queue.overview.completed_runs"),
                value=str(completed),
                inline=True,
            )
        else:
            embed.add_field(
                name=t(guild, "queue.overview.range"),
                value=f"{configuration.min_players}–{configuration.max_players}",
                inline=True,
            )
            embed.add_field(
                name=t(guild, "queue.overview.completed_runs"),
                value=str(completed),
                inline=True,
            )
        return embed
