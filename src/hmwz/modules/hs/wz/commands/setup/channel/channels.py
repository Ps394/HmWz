from __future__ import annotations

import logging
from typing import Literal

import discord

from hmwz.utils.interactions import log_guild

from ....models import Channel
from ....module import WzModule

_logger = logging.getLogger(__name__)
ChannelAction = Literal["add", "remove"]


def can_view_channel(
    channel: discord.TextChannel, bot_member: discord.Member | None
) -> bool:
    """Return whether the bot can view a text channel."""
    can_view = (
        bot_member is not None and channel.permissions_for(bot_member).view_channel
    )
    _logger.debug(
        "%s Bot can view channel %s (%s): %s",
        log_guild(channel.guild),
        channel.name,
        channel.id,
        can_view,
    )
    return can_view


async def get_selectable_channels(
    *,
    guild: discord.Guild,
    module: WzModule,
    action: ChannelAction,
) -> list[discord.TextChannel]:
    """Return valid channels for the requested cleanup-list operation."""
    configured: tuple[Channel, ...] | None = await module.channels.get(guild=guild)

    if action == "add":
        configured_ids = {record.channel_id for record in configured or ()}
        configured_names = []
        for channel_id in configured_ids:
            channel = guild.get_channel(channel_id)
            channel_name = (
                f"{channel.name} ({channel_id})"
                if isinstance(channel, discord.TextChannel)
                else f"unknown channel ({channel_id})"
            )
            configured_names.append(channel_name)
        _logger.debug(
            "%s Configured channels: %s",
            log_guild(guild),
            configured_names,
        )
        channels = [
            channel
            for channel in guild.text_channels
            if (
                can_view_channel(channel, guild.me) and channel.id not in configured_ids
            )
        ]
        _logger.debug(
            "%s Selectable channels: %s",
            log_guild(guild),
            [f"{channel.name} ({channel.id})" for channel in channels],
        )
    else:
        channels = []
        for record in configured or ():
            channel = guild.get_channel(record.channel_id)
            if isinstance(channel, discord.TextChannel):
                channels.append(channel)

    return sorted(channels, key=lambda channel: channel.name.casefold())
