from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from decimal import Decimal

import discord
import pytest

from hmwz.client import Client
from hmwz.configuration import config
from hmwz.modules.donation.commands.snapshot import snapshot as snapshot_command
from hmwz.modules.donation.models import (
    DonationChannel,
    DonationRecord,
    DonationSummary,
    DonationType,
)
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.repositories import DonationRepository
from hmwz.modules.donation.snapshot import (
    DonationSnapshotBuilder,
    DonationSnapshotExporter,
)
from hmwz.modules.manager import Manager
from hmwz.modules.module import Module
from hmwz.modules.protocols import MessageModuleProtocol
from hmwz.modules.registry import REGISTRY
from hmwz.modules.snapshots import Snapshot
from hmwz.sqlite_db import Database


@pytest.fixture
def configuration() -> DonationChannel:
    return DonationChannel(
        channel_id=789,
        overview_message_id=None,
        ranking_message_id=None,
        title="Donations",
        description="",
        goal_hours=None,
        current_cycle=3,
        export_channel_id=321,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["records", "summary", "incomplete"])
async def test_builder_rejects_failed_or_incomplete_reads(
    configuration: DonationChannel, failure: str
) -> None:
    repository = Mock(spec=DonationRepository)
    repository.get_donations_for_export = AsyncMock(
        return_value=None if failure == "records" else ()
    )
    repository.get_summary = AsyncMock(
        return_value=None if failure == "summary" else DonationSummary(1, 0)
    )
    builder = DonationSnapshotBuilder(
        guild=Mock(spec=discord.Guild), donations=repository
    )
    assert (
        await builder.build(
            configuration=configuration,
            destination_channel_id=321,
            event_type="credit-donation",
        )
        is None
    )


@pytest.mark.asyncio
async def test_snapshot_preserves_exact_amounts_and_optional_rush_hours(
    configuration: DonationChannel,
) -> None:
    repository = Mock(spec=DonationRepository)
    repository.get_donations_for_export = AsyncMock(
        return_value=(
            DonationRecord(
                456,
                "Donor",
                Decimal("10000000000000000.50"),
                "Credits",
                None,
                "2026-10-30 12:00:00",
            ),
            DonationRecord(
                457,
                "Rush donor",
                Decimal("242"),
                "crystals",
                "8h",
                "2026-10-30 12:01:00",
            ),
        )
    )
    repository.get_summary = AsyncMock(return_value=DonationSummary(2, 8))
    builder = DonationSnapshotBuilder(
        guild=Mock(spec=discord.Guild), donations=repository
    )
    result = await builder.build(
        configuration=configuration,
        destination_channel_id=321,
        event_type="rushed-donation",
    )
    assert result is not None
    assert result.filename == "donation-789-cycle-3-rushed-donation.json"
    assert result.destination_channel_id == 321
    assert result.payload["type"] == "rushed-donation"
    payload = json.loads(json.dumps(result.payload))
    assert payload["donations"][0]["amount"] == "10000000000000000.50"
    assert "time_reduction" not in payload["donations"][0]
    assert payload["donations"][1]["time_reduction"] == "8h"


@pytest.mark.asyncio
async def test_snapshot_exports_all_current_cycle_records_and_leaves_history_unchanged(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="snapshot.db")
    guild = Mock(spec=discord.Guild)
    guild.id = 123
    client = Mock(spec=Client)
    client._database = database
    module = DonationModule(guild, client)
    assert await module.sync()
    repository = module.donations
    donation_type = DonationType("Credits", "simple", "Credits", "free", (), ())
    for channel_id in (789, 987):
        assert await repository.configure_channel(
            guild=guild,
            channel_id=channel_id,
            title="Credits",
            description="",
            export_channel_id=321,
        )
        assert await repository.configure_type(
            guild=guild,
            channel_id=channel_id,
            donation_type=donation_type,
        )
    member = Mock(spec=discord.Member)
    member.id = 456
    member.display_name = "Donor"
    assert await repository.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=donation_type,
        amount=Decimal(99),
        time_reduction=None,
    )
    assert await repository.reset_cycle(guild=guild, channel_id=789, rush_start_at=None)
    for index in range(25):
        assert await repository.add_donation(
            guild=guild,
            channel_id=789,
            member=member,
            donation_type=donation_type,
            amount=Decimal(index + 1),
            time_reduction=None,
            cycle=2,
        )
    assert await repository.add_donation(
        guild=guild,
        channel_id=987,
        member=member,
        donation_type=donation_type,
        amount=Decimal(999),
        time_reduction=None,
    )
    delivery = Mock()
    delivery.export = AsyncMock(return_value=True)
    module._snapshot_exporter = DonationSnapshotExporter(
        guild=guild,
        donations=repository,
        exporter=delivery,
    )

    assert await module.export_donation_snapshot(789)

    result: Snapshot = delivery.export.await_args.args[0]
    assert result.payload["cycle"] == 2
    records = json.loads(json.dumps(result.payload))["donations"]
    assert len(records) == 25
    assert [item["amount"] for item in records] == [
        str(amount) for amount in range(25, 0, -1)
    ]
    settings = await repository.get_channel(guild=guild, channel_id=789)
    assert settings is not None and settings.current_cycle == 2
    assert (
        len(await repository.get_donations(guild=guild, channel_id=789, limit=None))
        == 26
    )


@pytest.mark.asyncio
async def test_empty_cycle_snapshot_is_valid(configuration: DonationChannel) -> None:
    repository = Mock(spec=DonationRepository)
    repository.get_donations_for_export = AsyncMock(return_value=())
    repository.get_summary = AsyncMock(return_value=DonationSummary(0, 0))
    builder = DonationSnapshotBuilder(
        guild=Mock(spec=discord.Guild), donations=repository
    )
    result = await builder.build(
        configuration=configuration,
        destination_channel_id=321,
        event_type="credit-donation",
    )
    assert result is not None and result.payload["donations"] == []


@pytest.mark.asyncio
async def test_manual_export_without_destination_is_not_reported_as_success() -> None:
    repository = Mock(spec=DonationRepository)
    repository.get_channel = AsyncMock(
        return_value=DonationChannel(
            channel_id=789,
            overview_message_id=None,
            ranking_message_id=None,
            title="Credits",
            description="",
            goal_hours=None,
        )
    )
    delivery = Mock()
    delivery.export = AsyncMock()
    exporter = DonationSnapshotExporter(
        guild=Mock(spec=discord.Guild),
        donations=repository,
        exporter=delivery,
    )
    assert not await exporter.export(789, "credit-donation")
    assert await exporter.export(789, "cycle-reset")
    delivery.export.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_snapshot_waits_for_cycle_writes(tmp_path: Path) -> None:
    client = Mock(spec=Client)
    client._database = Database(folder=str(tmp_path), filename="lock.db")
    module = DonationModule(Mock(spec=discord.Guild), client)
    module.donations.get_type = AsyncMock(
        return_value=SimpleNamespace(kind="time_reduction")
    )
    export = AsyncMock(return_value=True)
    module._snapshot_exporter = cast(
        DonationSnapshotExporter, SimpleNamespace(export=export)
    )
    lock = module._cycle_lock(789)
    async with lock:
        task = asyncio.create_task(module.export_donation_snapshot(789))
        await asyncio.sleep(0)
        export.assert_not_awaited()
    assert await task
    export.assert_awaited_once_with(789, "rushed-donation")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("destination", "exported", "result_key"),
    [
        (321, True, "donation.success.snapshot"),
        (321, False, "donation.error.snapshot"),
        (None, False, "donation.error.snapshot_destination"),
    ],
)
async def test_snapshot_command_reports_success_and_errors(
    destination: int | None,
    exported: bool,
    result_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = SimpleNamespace(
        donations=SimpleNamespace(
            get_channel=AsyncMock(
                return_value=SimpleNamespace(export_channel_id=destination)
            )
        ),
        export_donation_snapshot=AsyncMock(return_value=exported),
    )
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    interaction = Mock(spec=discord.Interaction)
    interaction.guild = Mock(spec=discord.Guild)
    interaction.channel_id = 789
    interaction.client = SimpleNamespace(module_manager=manager)
    interaction.response = SimpleNamespace(defer=AsyncMock())
    followup = AsyncMock()
    monkeypatch.setattr(
        "hmwz.modules.donation.commands.snapshot.send_temporary_followup", followup
    )
    monkeypatch.setattr(
        "hmwz.modules.donation.commands.snapshot.t", lambda context, key: key
    )
    await snapshot_command.callback(interaction)
    followup.assert_awaited_once_with(interaction, result_key)
    if destination is None:
        module.export_donation_snapshot.assert_not_awaited()
    else:
        module.export_donation_snapshot.assert_awaited_once_with(789)


@pytest.mark.asyncio
async def test_manager_restores_donation_messages_without_startup_exports(
    tmp_path: Path,
) -> None:
    guild = Mock(spec=discord.Guild)
    guild.id = 123
    client = Mock(spec=Client)
    client._database = Database(folder=str(tmp_path), filename="startup.db")
    module = DonationModule(guild, client)
    assert isinstance(module, Module)
    assert isinstance(module, MessageModuleProtocol)
    module.ensure = AsyncMock(return_value=True)
    export = AsyncMock()
    module._snapshot_exporter = cast(
        DonationSnapshotExporter, SimpleNamespace(export=export)
    )
    manager = Manager(client)
    manager._modules_by_guild[guild.id] = [module]
    await manager.init_guild(guild)
    module.ensure.assert_awaited_once()
    export.assert_not_awaited()


@pytest.mark.asyncio
async def test_donation_module_and_commands_are_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert DonationModule in REGISTRY
    monkeypatch.setitem(
        config, "database", {"folder": str(tmp_path), "filename": "commands.db"}
    )
    client = Client(intents=discord.Intents.none())
    try:
        await client.register_commands()
        group = client.CommandTree.get_command("donation")
        assert isinstance(group, discord.app_commands.Group)
        assert {command.name for command in group.commands} == {
            "setup",
            "remove",
            "reset",
            "snapshot",
        }
    finally:
        await client.close()
