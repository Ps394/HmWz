"""Build complete donation snapshots from persisted cycle data."""

from __future__ import annotations

import logging
from typing import Literal

import discord

from hmwz.modules.snapshots import Snapshot

from ..models import DonationChannel
from ..repositories import DonationRepository
from ..type.rush.pricing import rush_end_at

DonationEventType = Literal["cycle-reset", "rushed-donation", "credit-donation"]
_logger = logging.getLogger(__name__)


class DonationSnapshotBuilder:
    """Build JSON-compatible snapshots without truncating cycle history."""

    def __init__(self, *, guild: discord.Guild, donations: DonationRepository) -> None:
        self.guild = guild
        self.donations = donations

    async def build(
        self,
        *,
        configuration: DonationChannel,
        destination_channel_id: int,
        event_type: DonationEventType,
    ) -> Snapshot | None:
        """Build a snapshot, rejecting failed queries or incomplete history."""
        channel_id = configuration.channel_id
        cycle = configuration.current_cycle
        records = await self.donations.get_donations_for_export(
            guild=self.guild, channel_id=channel_id, cycle=cycle
        )
        summary = await self.donations.get_summary(
            guild=self.guild, channel_id=channel_id, cycle=cycle
        )
        if records is None or summary is None or len(records) != summary.donation_count:
            _logger.error(
                "%s Cannot export all donations for channel %s, cycle %s.",
                self.guild.name,
                channel_id,
                cycle,
            )
            return None

        name = configuration.title
        if not name:
            channel = self.guild.get_channel_or_thread(channel_id)
            name = channel.name if channel is not None else str(channel_id)
        donations: list[dict[str, int | str]] = []
        for record in records:
            donation: dict[str, int | str] = {
                "member_id": record.member_id,
                "member_name": record.member_name,
                "amount": format(record.amount, "f"),
                "unit": record.unit,
                "created_at": record.created_at,
            }
            if record.time_reduction is not None:
                donation["time_reduction"] = record.time_reduction
            donations.append(donation)

        filename = f"donation-{channel_id}-cycle-{cycle}"
        if event_type != "cycle-reset":
            filename += f"-{event_type}"
        payload: dict[str, object] = {
            "type": event_type,
            "name": name,
            "channel-id": channel_id,
            "cycle": cycle,
            "donations": donations,
        }
        if configuration.target_at is not None:
            payload["target_at"] = configuration.target_at.isoformat()
            if configuration.rush_start_at is not None:
                payload["end_at"] = rush_end_at(
                    configuration.rush_start_at, summary.time_reduction_hours
                ).isoformat()
        return Snapshot(
            destination_channel_id=destination_channel_id,
            filename=f"{filename}.json",
            payload=payload,
        )
