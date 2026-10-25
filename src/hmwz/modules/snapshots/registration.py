from __future__ import annotations

import asyncio
import weakref
from dataclasses import dataclass, field
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
        RegistrationSnapshotMessageRepository,
        RegistrationSettingsRepository,
    )


@dataclass
class _StartupSyncExportState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    exported: set[tuple[int, int]] = field(default_factory=set)


class RegistrationSnapshotExporter:
    """Coordinate registration snapshot creation and delivery."""

    _startup_sync_states: weakref.WeakKeyDictionary[
        discord.Client, dict[int, _StartupSyncExportState]
    ] = weakref.WeakKeyDictionary()

    def __init__(
        self,
        *,
        client: discord.Client,
        guild: discord.Guild,
        module_key: str,
        event_channel: RegistrationEventChannelRepository,
        registration: RegistrationSettingsRepository,
        registrations: MemberRegistrationRepository,
        snapshot_messages: RegistrationSnapshotMessageRepository | None = None,
        exporter: SnapshotExporter | None = None,
    ) -> None:
        self.client = client
        self.guild = guild
        self.event_channel = event_channel
        self.registration = registration
        self.snapshot_messages = snapshot_messages
        self.exporter = (
            exporter
            if exporter is not None
            else DiscordJsonSnapshotExporter(guild, snapshot_messages)
        )
        self.snapshot_builder = RegistrationSnapshotBuilder(
            guild=guild,
            module_key=module_key,
            registration=registration,
            registrations=registrations,
        )

    def _startup_sync_state(self) -> _StartupSyncExportState:
        guild_states = self._startup_sync_states.get(self.client)
        if guild_states is None:
            guild_states = {}
            self._startup_sync_states[self.client] = guild_states
        state = guild_states.get(self.guild.id)
        if state is None:
            state = _StartupSyncExportState()
            guild_states[self.guild.id] = state
        return state

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
        """Export one startup snapshot per registration and destination channel.

        WZ and QS share registration tables and the export destination, so
        different module exporters must share the startup deduplication state.
        """
        state = self._startup_sync_state()
        async with state.lock:
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
                if export_key in state.exported:
                    continue
                if await self._export_to_destination(
                    channel_id=channel_id,
                    destination_channel_id=destination_channel_id,
                    event_type="sync",
                ):
                    state.exported.add(export_key)


__all__ = ["RegistrationEventType", "RegistrationSnapshotExporter"]
