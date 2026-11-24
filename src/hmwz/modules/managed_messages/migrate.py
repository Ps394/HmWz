"""Opt-in migration from legacy OverviewModule records."""

from __future__ import annotations

import discord

from hmwz.modules.overview.repositories import OverviewRepository
from hmwz.modules.overview.models import Overview
from hmwz import sqlite_db

from .models import ManagedMessage
from .module import ManagedMessagesModule


async def migrate_overviews(
    module: ManagedMessagesModule,
    guild: discord.Guild,
    *,
    overview_ids: tuple[str, ...] = (),
) -> bool:
    """Adopt selected OverviewModule records without removing their source rows."""
    if not await module.sync():
        return False
    database = module.database
    if not isinstance(database, sqlite_db.Database):
        return False
    repository = OverviewRepository(database)
    if not await repository.ensure_schema():
        return False
    if overview_ids:
        selected: list[Overview] = []
        for overview_id in overview_ids:
            record = await repository.get(guild=guild, overview_id=overview_id)
            if record is not None:
                selected.append(record)
        records: tuple[Overview, ...] = tuple(selected)
    else:
        records = await repository.get_all(guild=guild)
    success = True
    for overview in records:
        managed = ManagedMessage(
            guild_id=guild.id,
            managed_id=overview.overview_id,
            channel_id=overview.channel_id,
            message_id=overview.message_id,
            content=None,
            embeds=(
                {
                    "title": overview.title,
                    "description": overview.description,
                },
            ),
            target_kind="channel",
        )
        success = await module.messages.save(managed) and success
    return success
