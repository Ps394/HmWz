"""Coordinate donation snapshot creation and delivery."""

from __future__ import annotations

import logging

import discord

from hmwz.modules.snapshots import SnapshotExporter
from hmwz.modules.snapshots.json_discord import DiscordJsonSnapshotExporter

from ..repositories import DonationRepository
from .builder import DonationEventType, DonationSnapshotBuilder

_logger = logging.getLogger(__name__)


class DonationSnapshotExporter:
    """Export an active cycle to its channel-specific JSON destination."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        donations: DonationRepository,
        exporter: SnapshotExporter | None = None,
    ) -> None:
        self.guild = guild
        self.donations = donations
        self.snapshot_builder = DonationSnapshotBuilder(
            guild=guild, donations=donations
        )
        self.exporter = (
            exporter if exporter is not None else DiscordJsonSnapshotExporter(guild)
        )

    async def export(self, channel_id: int, event_type: DonationEventType) -> bool:
        """Deliver a snapshot; an unconfigured destination only permits resets."""
        configuration = await self.donations.get_channel(
            guild=self.guild, channel_id=channel_id
        )
        if configuration is None:
            _logger.error(
                "%s Donation channel %s is not configured.",
                self.guild.name,
                channel_id,
            )
            return False
        destination = configuration.export_channel_id
        if destination is None:
            if event_type == "cycle-reset":
                return True
            _logger.error(
                "%s Donation channel %s has no snapshot destination.",
                self.guild.name,
                channel_id,
            )
            return False
        snapshot = await self.snapshot_builder.build(
            configuration=configuration,
            destination_channel_id=destination,
            event_type=event_type,
        )
        if snapshot is None:
            return False
        if not await self.exporter.export(snapshot):
            _logger.error(
                "%s Failed to export donation cycle %s from channel %s.",
                self.guild.name,
                configuration.current_cycle,
                channel_id,
            )
            return False
        return True
