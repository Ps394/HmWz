from __future__ import annotations

import discord

from hmwz.i18n import t

from .repository import QueueConfiguration, QueueRepository


class QueueOverview:
    @staticmethod
    async def create_embed(
        guild: discord.Guild,
        configuration: QueueConfiguration,
        repository: QueueRepository,
    ) -> discord.Embed:
        members = await repository.get_members(
            guild=guild, channel_id=configuration.channel_id
        )
        completed = await repository.completed_count(
            guild=guild, channel_id=configuration.channel_id
        )
        waiting = "\n".join(f"<@{member_id}>" for member_id in members)
        if len(waiting) > 1024:
            waiting = waiting[:1018].rsplit("\n", maxsplit=1)[0] + "\n..."
        embed = discord.Embed(
            title=configuration.name,
            description=t(guild, "queue.overview.description"),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name=t(guild, "queue.overview.members"),
            value=waiting or t(guild, "queue.overview.empty"),
            inline=False,
        )
        embed.add_field(
            name=t(guild, "queue.overview.capacity"),
            value=f"{len(members)} / {configuration.max_players}",
            inline=True,
        )
        embed.add_field(
            name=t(guild, "queue.overview.completed_runs"),
            value=str(completed),
            inline=True,
        )
        return embed
