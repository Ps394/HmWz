from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.modules.registration.repositories import RegistrationEventChannelRepository
from hmwz.modules.snapshots import Snapshot, SnapshotExporter
from hmwz.modules.snapshots.json_discord import DiscordJsonSnapshotExporter
from hmwz.modules.registration.snapshot import RegistrationSnapshotExporter
from hmwz.modules.registration.repositories import (
    RegistrationSnapshotMessageRepository,
)
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
async def test_snapshot_channel_repository_migrates_legacy_table(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="snapshot-channel.db")
    assert await database.execute(
        """
        CREATE TABLE Registration_Event_Channel (
            Guild INTEGER PRIMARY KEY,
            Channel INTEGER NOT NULL
        )
        """
    )
    assert await database.execute(
        "INSERT INTO Registration_Event_Channel (Guild, Channel) VALUES (?, ?)",
        (123, 456),
    )
    repository = RegistrationEventChannelRepository(database)

    assert repository.table_name == "Registration_Snapshot_Channel"
    assert await repository.migrate_schema()
    assert await repository.get(guild=SimpleNamespace(id=123, name="guild")) == 456
    assert (
        await database.fetch_one(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'Registration_Event_Channel'"
        )
        is None
    )


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
        client=discord.Client(intents=discord.Intents.none()),
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
        "hmwz.modules.snapshots.json_discord.fetch_channel",
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
async def test_startup_sync_exports_once_when_wz_and_qs_share_registrations() -> None:
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

    class UnweakrefableGuild:
        __slots__ = ("id", "name")

        def __init__(self) -> None:
            self.id = 123
            self.name = "test guild"

        def get_channel_or_thread(self, channel_id: int) -> SimpleNamespace:
            return SimpleNamespace(name=f"Event {channel_id}")

    guild = cast(
        discord.Guild,
        UnweakrefableGuild(),
    )
    client = discord.Client(intents=discord.Intents.none())
    event_channel = SimpleNamespace(get=AsyncMock(return_value=321))
    registrations = SimpleNamespace(get=AsyncMock(return_value=()))
    exporters = [
        RegistrationSnapshotExporter(
            client=client,
            guild=guild,
            module_key=module_key,
            event_channel=event_channel,
            registration=registration,
            registrations=registrations,
            exporter=SimpleNamespace(export=export),
        )
        for module_key in ("wz", "qs")
    ]

    await asyncio.gather(
        *(exporter.export_startup_snapshots() for exporter in exporters)
    )
    await asyncio.gather(
        *(exporter.export_startup_snapshots() for exporter in exporters)
    )

    snapshots = [call.args[0] for call in export.await_args_list]
    assert len(snapshots) == 2
    assert {snapshot.destination_channel_id for snapshot in snapshots} == {321}
    assert {snapshot.payload["channel-id"] for snapshot in snapshots} == {654, 987}
    assert all(snapshot.filename.endswith("-sync.json") for snapshot in snapshots)
    assert all(isinstance(snapshot, Snapshot) for snapshot in snapshots)


@pytest.mark.asyncio
async def test_startup_sync_updates_persisted_message_instead_of_sending_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(folder=str(tmp_path), filename="snapshot-messages.db")
    repository = RegistrationSnapshotMessageRepository(database)
    assert await database.execute(repository.table)

    message = SimpleNamespace(id=789, edit=AsyncMock())
    message.edit.return_value = message
    channel = Mock(spec=discord.TextChannel)
    channel.id = 321
    channel.send = AsyncMock(return_value=message)
    channel.fetch_message = AsyncMock(return_value=message)
    guild = SimpleNamespace(id=123, name="test guild", me=None)
    monkeypatch.setattr(
        "hmwz.modules.snapshots.json_discord.fetch_channel",
        AsyncMock(return_value=channel),
    )
    snapshot = Snapshot(
        destination_channel_id=321,
        filename="wz-654-sync.json",
        payload={"type": "sync", "channel-id": 654},
    )

    first_exporter = DiscordJsonSnapshotExporter(guild, repository)
    second_exporter = DiscordJsonSnapshotExporter(guild, repository)
    assert await first_exporter.export(snapshot)
    assert await second_exporter.export(snapshot)

    channel.send.assert_awaited_once()
    channel.fetch_message.assert_awaited_once_with(789)
    message.edit.assert_awaited_once()
    assert await repository.get(
        guild=guild,
        source_channel_id=654,
        destination_channel_id=321,
    ) == repository._Data(message_id=789)


@pytest.mark.asyncio
async def test_startup_sync_reuses_legacy_snapshot_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(folder=str(tmp_path), filename="legacy-snapshot-message.db")
    repository = RegistrationSnapshotMessageRepository(database)
    assert await database.execute(repository.table)

    legacy_message = SimpleNamespace(
        id=789,
        author=SimpleNamespace(id=999),
        attachments=[SimpleNamespace(filename="qs-654-sync.json")],
        edit=AsyncMock(),
    )
    legacy_message.edit.return_value = legacy_message

    async def history(*, limit: int):
        assert limit == 100
        yield legacy_message

    channel = Mock(spec=discord.TextChannel)
    channel.id = 321
    channel.history = history
    channel.send = AsyncMock()
    guild = SimpleNamespace(
        id=123,
        name="test guild",
        me=SimpleNamespace(id=999),
    )
    monkeypatch.setattr(
        "hmwz.modules.snapshots.json_discord.fetch_channel",
        AsyncMock(return_value=channel),
    )
    exporter = DiscordJsonSnapshotExporter(guild, repository)
    snapshot = Snapshot(
        destination_channel_id=321,
        filename="wz-654-sync.json",
        payload={"type": "sync", "channel-id": 654},
    )

    assert await exporter.export(snapshot)

    channel.send.assert_not_awaited()
    legacy_message.edit.assert_awaited_once()
    assert await repository.get(
        guild=guild,
        source_channel_id=654,
        destination_channel_id=321,
    ) == repository._Data(message_id=789)
