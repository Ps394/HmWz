from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING

import discord

from hmwz import sqlite_db
from hmwz.utils.fetchers import fetch_channel

from . import Snapshot

if TYPE_CHECKING:
    from hmwz.modules.registration.repositories import (
        RegistrationSnapshotMessageRepository,
    )

_logger = logging.getLogger(__name__)


class DiscordJsonSnapshotExporter:
    """Send snapshots as JSON attachments to Discord channels."""

    def __init__(
        self,
        guild: discord.Guild,
        snapshot_messages: RegistrationSnapshotMessageRepository | None = None,
    ) -> None:
        self.guild = guild
        self.snapshot_messages = snapshot_messages

    async def export(self, snapshot: Snapshot) -> bool:
        """Serialize and deliver one snapshot as a JSON attachment."""
        channel = await fetch_channel(self.guild, snapshot.destination_channel_id)
        if channel is None:
            _logger.error(
                "%s Snapshot destination channel %s is unavailable.",
                sqlite_db.Base.log_prefix(self.guild),
                snapshot.destination_channel_id,
            )
            return False
        tracks_startup_snapshot = (
            self._is_startup_snapshot(snapshot) and self.snapshot_messages is not None
        )
        if tracks_startup_snapshot and not isinstance(
            channel, (discord.TextChannel, discord.Thread)
        ):
            _logger.error(
                "%s Snapshot destination channel %s does not support messages.",
                sqlite_db.Base.log_prefix(self.guild),
                snapshot.destination_channel_id,
            )
            return False

        data = json.dumps(snapshot.payload, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        try:
            existing_message = (
                await self._startup_message(channel, snapshot)
                if isinstance(channel, (discord.TextChannel, discord.Thread))
                else None
            )
            file = discord.File(io.BytesIO(data), filename=snapshot.filename)
            if existing_message is None:
                message = await channel.send(file=file)
            else:
                message = await existing_message.edit(attachments=[file])
            if self._is_startup_snapshot(snapshot):
                if self.snapshot_messages is None:
                    return True
                source_channel_id = snapshot.payload["channel-id"]
                if not isinstance(source_channel_id, int):
                    _logger.error(
                        "%s Startup snapshot %s has no valid source channel ID.",
                        sqlite_db.Base.log_prefix(self.guild),
                        snapshot.filename,
                    )
                    return False
                return await self.snapshot_messages.set(
                    guild=self.guild,
                    source_channel_id=source_channel_id,
                    destination_channel_id=snapshot.destination_channel_id,
                    message_id=message.id,
                )
            return True
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to send snapshot %s to channel %s.",
                sqlite_db.Base.log_prefix(self.guild),
                snapshot.filename,
                snapshot.destination_channel_id,
            )
            return False

    async def _startup_message(
        self,
        channel: discord.TextChannel | discord.Thread,
        snapshot: Snapshot,
    ) -> discord.Message | None:
        if not self._is_startup_snapshot(snapshot) or self.snapshot_messages is None:
            return None

        source_channel_id = snapshot.payload["channel-id"]
        if not isinstance(source_channel_id, int):
            return None
        saved_message = await self.snapshot_messages.get(
            guild=self.guild,
            source_channel_id=source_channel_id,
            destination_channel_id=snapshot.destination_channel_id,
        )
        if saved_message is not None:
            try:
                return await channel.fetch_message(saved_message.message_id)
            except discord.NotFound:
                await self.snapshot_messages.remove(
                    guild=self.guild,
                    source_channel_id=source_channel_id,
                    destination_channel_id=snapshot.destination_channel_id,
                )

        return await self._find_legacy_startup_message(
            channel,
            source_channel_id=source_channel_id,
        )

    async def _find_legacy_startup_message(
        self,
        channel: discord.TextChannel | discord.Thread,
        *,
        source_channel_id: int,
    ) -> discord.Message | None:
        bot_member = self.guild.me
        if bot_member is None:
            return None

        legacy_filenames = {
            f"{module_key}-{source_channel_id}-sync.json" for module_key in ("wz", "qs")
        }
        async for message in channel.history(limit=100):
            if message.author.id != bot_member.id:
                continue
            if any(
                attachment.filename in legacy_filenames
                for attachment in message.attachments
            ):
                return message
        return None

    @staticmethod
    def _is_startup_snapshot(snapshot: Snapshot) -> bool:
        return snapshot.payload.get("type") == "sync"
