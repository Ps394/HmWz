from __future__ import annotations

import io
import json
import logging

import discord

from hmwz import sqlite_db, utils

from . import Snapshot

_logger = logging.getLogger(__name__)


class DiscordJsonSnapshotExporter:
    """Send snapshots as JSON attachments to Discord channels."""

    def __init__(self, guild: discord.Guild) -> None:
        self.guild = guild

    async def export(self, snapshot: Snapshot) -> bool:
        """Serialize and deliver one snapshot as a JSON attachment."""
        channel = await utils.fetch_channel(self.guild, snapshot.destination_channel_id)
        if channel is None:
            _logger.error(
                "%s Snapshot destination channel %s is unavailable.",
                sqlite_db.Base.log_prefix(self.guild),
                snapshot.destination_channel_id,
            )
            return False

        data = json.dumps(snapshot.payload, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        file = discord.File(io.BytesIO(data), filename=snapshot.filename)
        try:
            await channel.send(file=file)
            return True
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to send snapshot %s to channel %s.",
                sqlite_db.Base.log_prefix(self.guild),
                snapshot.filename,
                snapshot.destination_channel_id,
            )
            return False
