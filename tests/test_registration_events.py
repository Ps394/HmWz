from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hmwz.modules.registration.base import RegistrationModuleBase
from hmwz.modules.registration.repositories import RegistrationEventChannelRepository
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
        SimpleNamespace(member=12, account="Alt account"),
        SimpleNamespace(member=34, account=""),
    )
    module = SimpleNamespace(
        guild=SimpleNamespace(get_channel_or_thread=lambda channel_id: source_channel),
        module_key="wz",
        registration_event_channel=SimpleNamespace(get=AsyncMock(return_value=321)),
        registration=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(title="WZ Event"))
        ),
        registrations=SimpleNamespace(
            get=AsyncMock(return_value=records),
            member_names=AsyncMock(
                side_effect=[("alt-user", "Alt User"), ("user", "Display Name")]
            ),
        ),
    )
    monkeypatch.setattr(
        "hmwz.modules.registration.base.utils.fetch_channel",
        AsyncMock(return_value=delivery_channel),
    )

    assert await RegistrationModuleBase.send_registration_event(
        module, 654, "registration"
    )

    sent_file = delivery_channel.send.await_args.kwargs["file"]
    payload = json.loads(sent_file.fp.getvalue())
    assert payload["event"] == {
        "type": "registration",
        "module": "wz",
        "name": "WZ Event",
        "channel_id": 654,
        "channel_name": "event-channel",
    }
    assert payload["registration_channel"] == {
        "id": 654,
        "name": "event-channel",
    }
    assert payload["delivery_channel"] == {
        "id": 321,
        "name": "registration-events",
    }
    assert payload["registrations"] == [
        {
            "member_id": 12,
            "member_name": "Alt User",
            "registration_alias": "Alt account",
        },
        {
            "member_id": 34,
            "member_name": "Display Name",
            "registration_alias": "Display Name",
        },
    ]
