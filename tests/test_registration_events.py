from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hmwz.modules.registration.repositories import RegistrationEventChannelRepository
from hmwz.modules.snapshots import Snapshot, SnapshotExporter
from hmwz.modules.snapshots.json_discord import DiscordJsonSnapshotExporter
from hmwz.modules.snapshots.registration import RegistrationSnapshotExporter
from hmwz.sqlite_db import Database


@pytest.mark.asyncio
async def test_registration_event_channel_repository_crud(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="event-channel.db")
    repository = RegistrationEventChannelRepository(database)
    assert await database.execute(repository.table)
    guild = SimpleNamespace(id=123, name="test guild")

    assert await repository.get(guild=guild) is None
    assert await repository.set(guild=guild, channel_id=456)
    assert await repository.get(guild=guild) == 456
    assert await repository.set(guild=guild, channel_id=789)
    assert await repository.get(guild=guild) == 789
    assert await repository.remove_channel(guild=guild, channel_id=456)
    assert await repository.get(guild=guild) == 789
    assert await repository.remove(guild=guild)
    assert await repository.get(guild=guild) is None


@pytest.mark.asyncio
async def test_registration_event_sends_required_registration_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_channel = SimpleNamespace(name="event-channel")
    delivery_channel = SimpleNamespace(id=321, name="registration-events")
    delivery_channel.send = AsyncMock()
    records = (
        SimpleNamespace(
            member=12,
            account="Alt account",
            member_username="alt-user",
            member_display_name="Alt User",
        ),
        SimpleNamespace(
            member=34,
            account="",
            member_username="user",
            member_display_name="Display Name",
        ),
    )
    guild = SimpleNamespace(
        id=123,
        name="test guild",
        get_channel_or_thread=lambda channel_id: source_channel,
    )
    snapshot_exporter: SnapshotExporter = DiscordJsonSnapshotExporter(guild)
    registration_exporter = RegistrationSnapshotExporter(
        guild=guild,
        module_key="wz",
        event_channel=SimpleNamespace(get=AsyncMock(return_value=321)),
        registration=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(title="WZ Event"))
        ),
        registrations=SimpleNamespace(
            get=AsyncMock(return_value=records),
            member_names=AsyncMock(
                side_effect=[("alt-user", "Alt User"), ("user", "Display Name")]
            ),
        ),
        exporter=snapshot_exporter,
    )
    monkeypatch.setattr(
        "hmwz.modules.snapshots.json_discord.utils.fetch_channel",
        AsyncMock(return_value=delivery_channel),
    )

    assert await registration_exporter.export(654, "registration")

    sent_file = delivery_channel.send.await_args.kwargs["file"]
    payload = json.loads(sent_file.fp.getvalue())
    assert payload.keys() == {"type", "name", "channel-id", "registrations"}
    assert payload["type"] == "registration"
    assert payload["name"] == "WZ Event"
    assert payload["channel-id"] == 654
    assert payload["registrations"] == [
        {
            "member_id": 12,
            "member_name": "alt-user",
            "registration_alias": "Alt account",
        },
        {
            "member_id": 34,
            "member_name": "user",
            "registration_alias": "Display Name",
        },
    ]


@pytest.mark.asyncio
async def test_registration_sync_events_are_sent_once_per_channel() -> None:
    registration = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                SimpleNamespace(channel=654),
                SimpleNamespace(channel=987),
            ]
        ),
        get=AsyncMock(return_value=SimpleNamespace(title="Event")),
    )
    export = AsyncMock(return_value=True)
    exporter = RegistrationSnapshotExporter(
        guild=SimpleNamespace(
            id=123,
            name="test guild",
            get_channel_or_thread=lambda channel_id: SimpleNamespace(name="Event"),
        ),
        module_key="wz",
        event_channel=SimpleNamespace(get=AsyncMock(return_value=321)),
        registration=registration,
        registrations=SimpleNamespace(get=AsyncMock(return_value=())),
        exporter=SimpleNamespace(export=export),
    )

    await asyncio.gather(
        exporter.export_startup_snapshots(),
        exporter.export_startup_snapshots(),
    )

    snapshots = [call.args[0] for call in export.await_args_list]
    assert [snapshot.destination_channel_id for snapshot in snapshots] == [321, 321]
    assert [snapshot.filename for snapshot in snapshots] == [
        "wz-654-sync.json",
        "wz-987-sync.json",
    ]
    assert all(isinstance(snapshot, Snapshot) for snapshot in snapshots)
