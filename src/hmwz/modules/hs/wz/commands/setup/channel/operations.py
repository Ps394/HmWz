from __future__ import annotations

import discord

from hmwz.i18n import t

from ....models import PurgeChannel
from ....module import WzRegistrationModule


async def add_channels(
    *,
    interaction: discord.Interaction,
    guild: discord.Guild,
    module: WzRegistrationModule,
    channels: list[discord.TextChannel],
    registration_channel_id: int | None,
) -> list[str]:
    configured = await module.purge_channels.get(
        guild=guild,
        registration_channel_id=registration_channel_id,
    )
    configured_ids = {record.channel_id for record in configured or ()}
    added: list[str] = []
    failed: list[str] = []

    for channel in channels:
        if len(configured_ids) >= PurgeChannel.MAX_PER_REGISTRATION:
            failed.append(channel.mention)
            continue
        if await module.purge_channels.add(
            guild=guild,
            channel_id=channel.id,
            registration_channel_id=registration_channel_id or 0,
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
    module: WzRegistrationModule,
    channels: list[discord.TextChannel],
    registration_channel_id: int | None,
) -> list[str]:
    removed: list[str] = []
    failed: list[str] = []

    for channel in channels:
        if await module.purge_channels.remove(
            guild=guild,
            channel_id=channel.id,
            registration_channel_id=registration_channel_id,
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
