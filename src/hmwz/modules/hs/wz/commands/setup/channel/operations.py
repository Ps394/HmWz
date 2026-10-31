from __future__ import annotations

import discord

from hmwz.i18n import t

from ....models import Channel
from ....module import WzModule


async def add_channels(
    *,
    interaction: discord.Interaction,
    guild: discord.Guild,
    module: WzModule,
    channels: list[discord.TextChannel],
) -> list[str]:
    configured = await module.channels.get(
        guild=guild,
    )
    configured_ids = {record.channel_id for record in configured or ()}
    added: list[str] = []
    failed: list[str] = []

    for channel in channels:
        if len(configured_ids) >= Channel.MAX_PER_GUILD:
            failed.append(channel.mention)
            continue
        if await module.channels.add(
            guild=guild,
            channel_id=channel.id,
        ):
            configured_ids.add(channel.id)
            added.append(channel.mention)
        else:
            failed.append(channel.mention)

    messages: list[str] = []
    if added:
        messages.append(
            t(
                interaction,
                "wz.setup.channel.add.success",
                channel_names=", ".join(added),
            )
        )
    if failed:
        messages.append(
            t(
                interaction,
                "wz.setup.channel.operation_failed",
                channel_names=", ".join(failed),
            )
        )
    return messages


async def remove_channels(
    *,
    interaction: discord.Interaction,
    guild: discord.Guild,
    module: WzModule,
    channels: list[discord.TextChannel],
) -> list[str]:
    removed: list[str] = []
    failed: list[str] = []

    for channel in channels:
        if await module.channels.remove(
            guild=guild,
            channel_id=channel.id,
        ):
            removed.append(channel.mention)
        else:
            failed.append(channel.mention)

    messages: list[str] = []
    if removed:
        messages.append(
            t(
                interaction,
                "wz.setup.channel.remove.success",
                channel_names=", ".join(removed),
            )
        )
    if failed:
        messages.append(
            t(
                interaction,
                "wz.setup.channel.operation_failed",
                channel_names=", ".join(failed),
            )
        )
    return messages
