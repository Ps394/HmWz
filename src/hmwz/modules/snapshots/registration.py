from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord

from . import SnapshotExporter
from .json_discord import DiscordJsonSnapshotExporter
from .registration_payload import (
    RegistrationEventType,
    RegistrationSnapshotBuilder,
)

if TYPE_CHECKING:
    from hmwz.modules.registration.repositories import (
        MemberRegistrationRepository,
        RegistrationEventChannelRepository,
        RegistrationSettingsRepository,
    )


class RegistrationSnapshotExporter:
    """Coordinate registration snapshot creation and delivery."""

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
        self.event_channel = event_channel
        self.registration = registration
        self.exporter = (
            exporter if exporter is not None else DiscordJsonSnapshotExporter(guild)
        )
        self.snapshot_builder = RegistrationSnapshotBuilder(
            guild=guild,
            module_key=module_key,
            registration=registration,
            registrations=registrations,
        )
        self._startup_sync_export_lock = asyncio.Lock()
        self._startup_sync_exports: set[tuple[int, int]] = set()

    async def export(self, channel_id: int, event_type: RegistrationEventType) -> bool:
        """Export the current registration snapshot to its configured destination."""
        destination_channel_id = await self.event_channel.get(guild=self.guild)
        if destination_channel_id is None:
            return True
        return await self._export_to_destination(
            channel_id=channel_id,
            destination_channel_id=destination_channel_id,
            event_type=event_type,
        )

    async def _export_to_destination(
        self,
        *,
        channel_id: int,
        destination_channel_id: int,
        event_type: RegistrationEventType,
    ) -> bool:
        snapshot = await self.snapshot_builder.build(
            channel_id=channel_id,
            destination_channel_id=destination_channel_id,
            event_type=event_type,
        )
        return await self.exporter.export(snapshot)

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
                if await self._export_to_destination(
                    channel_id=channel_id,
                    destination_channel_id=destination_channel_id,
                    event_type="sync",
                ):
                    self._startup_sync_exports.add(export_key)


__all__ = ["RegistrationEventType", "RegistrationSnapshotExporter"]
