from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.modules.registration.repositories import (
    RegistrationRoleRepository,
    RegistrationSettingsRepository,
)
from hmwz.sqlite_db import Database


@pytest.mark.asyncio
async def test_guild_can_configure_multiple_registrations_with_private_roles(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="multi-channel-roles.db")
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=10,
            name="test guild",
            get_channel_or_thread=lambda channel_id: None,
            get_role=lambda role_id: None,
        ),
    )
    roles = RegistrationRoleRepository(database)
    settings = RegistrationSettingsRepository(database)

    assert await database.execute(
        "CREATE TABLE Servers (Guild INTEGER PRIMARY KEY, Name TEXT)"
    )
    assert await database.execute(
        "INSERT INTO Servers VALUES (?, ?)", (10, "test guild")
    )
    assert await database.execute(settings.table)
    assert await database.execute(roles.table)
    assert await settings.create(guild=guild, channel_id=20)
    assert await settings.create(guild=guild, channel_id=21)

    assert await roles.add(guild=guild, role=99, channel_id=20)
    assert await roles.add(guild=guild, role=100, channel_id=21)
    assert not await roles.add(guild=guild, role=99, channel_id=21)

    registrations = await settings.get_all(guild=guild)
    assert registrations is not None
    assert {registration.channel for registration in registrations} == {20, 21}
    configured_roles = await roles.get(guild=guild)
    assert configured_roles is not None
    assert {(record.channel_id, record.role) for record in configured_roles} == {
        (20, 99),
        (21, 100),
    }
