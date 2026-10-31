"""Create and deliver registration snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.modules.snapshots import SnapshotExporter
from hmwz.modules.snapshots.json_discord import DiscordJsonSnapshotExporter

from .builder import (
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


class RegistrationSnapshotExporter:
    """Coordinate registration snapshot creation and delivery."""

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


__all__ = ["RegistrationEventType", "RegistrationSnapshotExporter"]
