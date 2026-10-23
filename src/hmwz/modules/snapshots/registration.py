from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal

import discord

from hmwz import sqlite_db

from . import Snapshot, SnapshotExporter
from .json_discord import DiscordJsonSnapshotExporter

if TYPE_CHECKING:
    from hmwz.modules.registration.repositories import (
        MemberRegistrationRepository,
        RegistrationEventChannelRepository,
        RegistrationSettingsRepository,
    )

RegistrationEventType = Literal[
    "registration", "registration_change", "deregistration", "sync"
]

_logger = logging.getLogger(__name__)


class RegistrationSnapshotExporter:
    """Build and export snapshots for configured registration channels."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        module_key: str,
        event_channel: RegistrationEventChannelRepository,
        registration: RegistrationSettingsRepository,
        registrations: MemberRegistrationRepository,
        exporter: SnapshotExporter | None = None,
    ) -> None:
        self.guild = guild
        self.module_key = module_key
        self.event_channel = event_channel
        self.registration = registration
        self.registrations = registrations
        self.exporter = (
            exporter if exporter is not None else DiscordJsonSnapshotExporter(guild)
        )
        self._startup_sync_export_lock = asyncio.Lock()
        self._startup_sync_exports: set[tuple[int, int]] = set()

    async def export(self, channel_id: int, event_type: RegistrationEventType) -> bool:
        """Export the current registration snapshot to its configured destination."""
        destination_channel_id = await self.event_channel.get(guild=self.guild)
        if destination_channel_id is None:
            return True

        source_channel = self.guild.get_channel_or_thread(channel_id)
        configuration = await self.registration.get(
            guild=self.guild, channel_id=channel_id
        )
        registration_records = await self.registrations.get(
            guild=self.guild, channel_id=channel_id
        )

        registrations: list[dict[str, int | str]] = []
        for record in registration_records or ():
            if record.member is None:
                _logger.warning(
                    "%s Skipping registration without a member ID in channel %s.",
                    sqlite_db.Base.log_prefix(self.guild),
                    channel_id,
                )
                continue
            member_names = None
            if not record.member_username or not record.member_display_name:
                member_names = await self.registrations.member_names(
                    self.guild, record.member
                )
            member_name = record.member_username or (
                member_names[0] if member_names is not None else str(record.member)
            )
            display_name = record.member_display_name or (
                member_names[1] if member_names is not None else member_name
            )
            registrations.append(
                {
                    "member_id": record.member,
                    "member_name": member_name,
                    "registration_alias": record.account or display_name,
                }
            )

        payload = {
            "type": event_type,
            "name": configuration.title
            if configuration is not None and configuration.title
            else source_channel.name
            if source_channel is not None
            else str(channel_id),
            "channel-id": channel_id,
            "registrations": registrations,
        }
        return await self.exporter.export(
            Snapshot(
                destination_channel_id=destination_channel_id,
                filename=f"{self.module_key}-{channel_id}-{event_type}.json",
                payload=payload,
            )
        )

    async def export_startup_snapshots(self) -> None:
        """Export one startup snapshot per registration and destination channel."""
        async with self._startup_sync_export_lock:
            destination_channel_id = await self.event_channel.get(guild=self.guild)
            if destination_channel_id is None:
                return
            for configuration in (
                await self.registration.get_all(guild=self.guild) or ()
            ):
                channel_id = configuration.channel
                if channel_id is None:
                    continue
                export_key = (channel_id, destination_channel_id)
                if export_key in self._startup_sync_exports:
                    continue
                if await self.export(channel_id, "sync"):
                    self._startup_sync_exports.add(export_key)


__all__ = ["RegistrationEventType", "RegistrationSnapshotExporter"]
