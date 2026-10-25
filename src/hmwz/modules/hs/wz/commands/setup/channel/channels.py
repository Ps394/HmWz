from __future__ import annotations

import logging
from typing import Literal

import discord

from ....models import PurgeChannel
from ....module import WzRegistrationModule

logger = logging.getLogger(__name__)
PurgeAction = Literal["add", "remove"]


def can_view_channel(
    channel: discord.TextChannel, bot_member: discord.Member | None
) -> bool:
    """Return whether the bot can view a text channel."""
    can_view = (
        bot_member is not None and channel.permissions_for(bot_member).view_channel
    )
    logger.debug(
        "Bot can view channel %s (%s) in guild %s (%s): %s",
        channel.name,
        channel.id,
        channel.guild.name,
        channel.guild.id,
        can_view,
    )
    return can_view


async def _remove_registration_channel_from_purge_list(
    guild: discord.Guild,
    module: WzRegistrationModule,
    channel_id: int,
) -> None:
    if not await module.purge_channels.remove(guild=guild, channel_id=channel_id):
        raise RuntimeError(
            f"Failed to remove registration channel {channel_id} "
            "from the WZ purge list."
        )


async def get_selectable_channels(
    *,
    guild: discord.Guild,
    module: WzRegistrationModule,
    action: PurgeAction,
    registration_channel_id: int | None,
) -> list[discord.TextChannel]:
    """Return valid channels for the requested purge-list operation."""
    configured: tuple[PurgeChannel, ...] | None = await module.purge_channels.get(
        guild=guild, registration_channel_id=registration_channel_id
    )
    registrations = await module.registration.get_all(guild=guild)
    registration_channel_ids = {
        record.channel for record in registrations or () if record.channel is not None
    }
    for channel_id in registration_channel_ids & {
        record.channel_id for record in configured or ()
    }:
        await _remove_registration_channel_from_purge_list(
            guild=guild,
            module=module,
            channel_id=channel_id,
        )
    configured = await module.purge_channels.get(
        guild=guild, registration_channel_id=registration_channel_id
    )

    if action == "add":
        all_configured = await module.purge_channels.get(guild=guild)
        configured_ids = {record.channel_id for record in all_configured or ()}
        configured_names = []
        for channel_id in configured_ids:
            channel = guild.get_channel(channel_id)
            channel_name = (
                f"{channel.name} ({channel_id})"
                if isinstance(channel, discord.TextChannel)
                else f"unknown channel ({channel_id})"
            )
            configured_names.append(channel_name)
        logger.debug(
            "Configured channels for guild %s (%s): %s",
            guild.name,
            guild.id,
            configured_names,
        )
        channels = [
            channel
            for channel in guild.text_channels
            if (
                can_view_channel(channel, guild.me)
                and channel.id not in configured_ids
                and channel.id not in registration_channel_ids
            )
        ]
        logger.debug(
            "Selectable channels for guild %s (%s): %s",
            guild.name,
            guild.id,
            [f"{channel.name} ({channel.id})" for channel in channels],
        )
    else:
        channels = []
        for record in configured or ():
            channel = guild.get_channel(record.channel_id)
            if (
                isinstance(channel, discord.TextChannel)
                and channel.id not in registration_channel_ids
            ):
                channels.append(channel)

    return sorted(channels, key=lambda channel: channel.name.casefold())
