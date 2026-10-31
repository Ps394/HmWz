from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.models import (
    DonationChannel,
    DonationRecord,
    DonationSummary,
)
from hmwz.modules.donation.snapshot import DonationSnapshotExporter
from hmwz.modules.snapshots import Snapshot


@pytest.mark.asyncio
async def test_reset_exports_every_current_cycle_donation_before_advancing() -> None:
    events: list[tuple[str, object]] = []
    records = (
        DonationRecord(
            member_id=123,
            member_name="Donor One",
            amount=Decimal("1000.50"),
            unit="Credits",
            time_reduction=None,
            created_at="2026-10-25 21:00:00",
        ),
        DonationRecord(
            member_id=456,
            member_name="Donor Two",
            amount=Decimal("223"),
            unit="crystals",
            time_reduction="8h",
            created_at="2026-10-25 21:30:00",
        ),
    )
    configuration = DonationChannel(
        channel_id=789,
        overview_message_id=None,
        ranking_message_id=None,
        title="Donations",
        description="",
        goal_hours=None,
        current_cycle=3,
        export_channel_id=321,
    )
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=1,
            name="Test guild",
            get_channel_or_thread=lambda channel_id: None,
        ),
    )
    donations = SimpleNamespace(
        get_channel=AsyncMock(return_value=configuration),
        get_donations_for_export=AsyncMock(return_value=records),
        get_summary=AsyncMock(
            return_value=DonationSummary(
                donation_count=len(records), time_reduction_hours=8
            )
        ),
        reset_cycle=AsyncMock(
            side_effect=lambda **kwargs: events.append(("reset", kwargs)) or True
        ),
    )

    async def export(snapshot: Snapshot) -> bool:
        events.append(("export", snapshot))
        return True

    module = cast(DonationModule, SimpleNamespace())
    module.guild = guild
    module.donations = donations
    module._cycle_locks = {}
    module._snapshot_exporter = DonationSnapshotExporter(
        guild=guild,
        donations=donations,
        exporter=SimpleNamespace(export=AsyncMock(side_effect=export)),
    )
    module._cycle_lock = lambda channel_id: asyncio.Lock()
    module.compose_overview = AsyncMock(return_value=True)

    async def export_current_cycle(channel_id: int) -> bool:
        return await DonationModule.export_current_cycle(module, channel_id)

    module.export_current_cycle = AsyncMock(side_effect=export_current_cycle)

    reset_result = await DonationModule.reset_cycle(module, 789, rush_start_at=None)

    assert reset_result == (True, True, False)
    assert [name for name, _ in events] == ["export", "reset"]
    snapshot = cast(Snapshot, events[0][1])
    assert snapshot.destination_channel_id == 321
    assert snapshot.filename == "donation-789-cycle-3.json"
    assert snapshot.payload == {
        "type": "cycle-reset",
        "name": "Donations",
        "channel-id": 789,
        "cycle": 3,
        "donations": [
            {
                "member_id": 123,
                "member_name": "Donor One",
                "amount": "1000.50",
                "unit": "Credits",
                "created_at": "2026-10-25 21:00:00",
            },
            {
                "member_id": 456,
                "member_name": "Donor Two",
                "amount": "223",
                "unit": "crystals",
                "created_at": "2026-10-25 21:30:00",
                "time_reduction": "8h",
            },
        ],
    }
    donations.get_donations_for_export.assert_awaited_once_with(
        guild=guild, channel_id=789, cycle=3
    )


@pytest.mark.asyncio
async def test_reset_does_not_advance_when_cycle_export_fails() -> None:
    configuration = DonationChannel(
        channel_id=789,
        overview_message_id=None,
        ranking_message_id=None,
        title="Donations",
        description="",
        goal_hours=None,
        export_channel_id=321,
    )
    guild = cast(discord.Guild, SimpleNamespace(id=1, name="Test guild"))
    donations = SimpleNamespace(
        get_channel=AsyncMock(return_value=configuration),
        get_donations_for_export=AsyncMock(
            return_value=(
                DonationRecord(
                    member_id=123,
                    member_name="Donor",
                    amount=Decimal(10),
                    unit="Credits",
                    time_reduction=None,
                    created_at="2026-10-25 21:00:00",
                ),
            )
        ),
        get_summary=AsyncMock(
            return_value=DonationSummary(donation_count=1, time_reduction_hours=0)
        ),
        reset_cycle=AsyncMock(return_value=True),
    )
    module = cast(DonationModule, SimpleNamespace())
    module.guild = guild
    module.donations = donations
    module._snapshot_exporter = DonationSnapshotExporter(
        guild=guild,
        donations=donations,
        exporter=SimpleNamespace(export=AsyncMock(return_value=False)),
    )
    module._cycle_lock = lambda channel_id: asyncio.Lock()
    module.compose_overview = AsyncMock(return_value=True)

    async def export_current_cycle(channel_id: int) -> bool:
        return await DonationModule.export_current_cycle(module, channel_id)

    module.export_current_cycle = AsyncMock(side_effect=export_current_cycle)

    assert await DonationModule.reset_cycle(module, 789, rush_start_at=None) == (
        False,
        False,
        True,
    )
    donations.reset_cycle.assert_not_awaited()
