from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.hm_client.repositories import ServerRepository
from hmwz.modules.wz_registration.repositories import (
    MemberRegistrationRepository,
    PurgeChannelRepository,
    RegistrationMessageRepository,
    RegistrationRoleRepository,
    RegistrationSettingsRepository,
    WzConfigurationRepository,
)
from hmwz.sqlite_db import Database


async def initialize_database(database: Database) -> None:
    repositories = (
        ServerRepository(database),
        WzConfigurationRepository(database),
        RegistrationRoleRepository(database),
        RegistrationSettingsRepository(database),
        MemberRegistrationRepository(database),
        RegistrationMessageRepository(database),
        PurgeChannelRepository(database),
    )
    for repository in repositories:
        assert await database.execute(repository.table)


@pytest.mark.asyncio
async def test_repositories_create_read_update_and_remove_records(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="repositories.db")
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))
    await initialize_database(database)

    servers = ServerRepository(database)
    assert await servers.add(guild=guild)
    assert await servers.count_all() == 1

    configuration = WzConfigurationRepository(database)
    assert await configuration.upsert(
        guild=guild,
        channel_id=456,
        score_mod_lvl=True,
        matchmaker=False,
    )
    configured = await configuration.get(guild=guild)
    assert configured is not None
    assert configured.channel_id == 456
    assert configured.score_mod_lvl is True
    assert configured.matchmaker is False
    assert await configuration.remove(guild=guild)
    assert await configuration.get(guild=guild) is None

    roles = RegistrationRoleRepository(database)
    assert await roles.add(guild=guild, role=789, permanent=True, score=3)
    role_records = await roles.get(guild=guild, permanent=True)
    assert role_records is not None
    assert role_records[0].role == 789
    assert role_records[0].score == 3
    assert await roles.remove(guild=guild, role=789)
    assert await roles.get(guild=guild) is None

    settings = RegistrationSettingsRepository(database)
    assert await settings.upsert(
        guild=guild,
        channel_id=456,
        message_id=101112,
        title="Registration",
        description="Choose a role",
    )
    settings_record = await settings.get(guild=guild)
    assert settings_record is not None
    assert settings_record.channel == 456
    assert settings_record.message == 101112
    assert await settings.remove(guild=guild)
    assert await settings.get(guild=guild) is None

    registrations = MemberRegistrationRepository(database)
    assert await registrations.add(guild=guild, member=234, role=789)
    assert await registrations.count(guild=guild, role=789) == 1
    member_records = await registrations.get(guild=guild, member=234)
    assert member_records is not None
    assert member_records[0].member == 234
    assert await registrations.remove(guild=guild, member=234)
    assert await registrations.get(guild=guild, member=234) is None

    messages = RegistrationMessageRepository(database)
    assert await messages.add(
        guild=guild,
        channel=456,
        message=101112,
        title="Registration",
        text="Choose a role",
    )
    message_records = await messages.get(guild=guild)
    assert message_records is not None
    assert message_records[0].message == 101112
    assert message_records[0].text == "Choose a role"
    assert await messages.remove(guild=guild, message=101112)
    assert await messages.get(guild=guild) is None

    purge_channels = PurgeChannelRepository(database)
    assert await purge_channels.add(guild=guild, channel_id=456)
    purge_records = await purge_channels.get(guild=guild)
    assert purge_records is not None
    assert purge_records[0].channel_id == 456
    assert await purge_channels.remove(guild=guild, channel_id=456)
    assert await purge_channels.get(guild=guild) is None

    assert await servers.remove(guild=guild)
    assert await servers.count_all() == 0


@pytest.mark.asyncio
async def test_repository_reports_failed_foreign_key_write(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="failed-write.db")
    await initialize_database(database)
    guild = cast(discord.Guild, SimpleNamespace(id=999, name="missing guild"))

    repository = RegistrationSettingsRepository(database)

    assert not await repository.upsert(guild=guild, channel_id=456)
    assert await repository.get(guild=guild) is None
