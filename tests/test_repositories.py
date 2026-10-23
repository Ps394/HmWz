from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.hm_client.repositories import ServerRepository
from hmwz.modules.hs.account.repositories import MemberGameAccountRepository
from hmwz.modules.hs.wz.repositories import (
    MemberRegistrationRepository,
    PurgeChannelRepository,
    RegistrationMessageRepository,
    RegistrationRoleRepository,
    RegistrationSettingsRepository,
)
from hmwz.sqlite_db import Database


async def initialize_database(database: Database) -> None:
    repositories = (
        ServerRepository(database),
        RegistrationRoleRepository(database),
        RegistrationSettingsRepository(database),
        MemberRegistrationRepository(database),
        MemberGameAccountRepository(database),
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
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=123,
            name="test guild",
            get_channel_or_thread=lambda channel_id: SimpleNamespace(
                id=channel_id, name="registration-channel"
            ),
            get_member=lambda member_id: SimpleNamespace(
                id=member_id, name="player", display_name="Player One"
            ),
            get_role=lambda role_id: SimpleNamespace(
                id=role_id, name="Registration Role"
            ),
        ),
    )
    await initialize_database(database)

    servers = ServerRepository(database)
    assert await servers.add(guild=guild)
    assert await servers.count_all() == 1

    roles = RegistrationRoleRepository(database)
    assert await roles.add(guild=guild, role=789, permanent=True, score=3)
    role_records = await roles.get(guild=guild, permanent=True)
    assert role_records is not None
    assert role_records[0].role == 789
    assert role_records[0].score == 3
    saved_role = await database.fetch_one(
        "SELECT Guild, Role, Permanent, Score FROM Registration_Roles "
        "WHERE Guild = ? AND Role = ?",
        (123, 789),
    )
    assert saved_role is not None
    assert tuple(saved_role) == (123, 789, 1, 3)
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
    saved_settings = await database.fetch_one(
        "SELECT Guild, Channel FROM Registration_Settings WHERE Guild = ?",
        (123,),
    )
    assert saved_settings is not None
    assert tuple(saved_settings) == (123, 456)
    assert await settings.remove(guild=guild)
    assert await settings.get(guild=guild) is None

    registrations = MemberRegistrationRepository(database)
    assert await registrations.add(guild=guild, member=234, role=789)
    assert await registrations.count(guild=guild, role=789) == 1
    member_records = await registrations.get(guild=guild, member=234)
    assert member_records is not None
    assert member_records[0].member == 234
    saved_registration = await database.fetch_one(
        """
        SELECT Guild, Channel, Member, Alias, Role
        FROM Registration_Members WHERE Guild = ? AND Member = ?
        """,
        (123, 234),
    )
    assert saved_registration is not None
    assert tuple(saved_registration) == (123, 0, 234, "", 789)
    assert await registrations.remove(guild=guild, member=234)
    assert await registrations.get(guild=guild, member=234) is None

    assert await registrations.add(guild=guild, member=234, role=789, account="Main")
    assert await registrations.add(guild=guild, member=234, role=789, account="Alt")
    multi_account_records = await registrations.get(guild=guild, member=234)
    assert multi_account_records is not None
    assert {record.account for record in multi_account_records} == {"Main", "Alt"}

    game_accounts = MemberGameAccountRepository(database)
    assert await game_accounts.add(guild=guild, member=234, account="Main")
    assert await game_accounts.add(guild=guild, member=234, account="Alt")
    assert not await game_accounts.add(guild=guild, member=345, account="main")
    linked_accounts = await game_accounts.get(guild=guild, member=234)
    assert linked_accounts is not None
    assert [record.account for record in linked_accounts] == ["Alt", "Main"]
    assert await game_accounts.remove(guild=guild, member=234, account="main")
    assert await game_accounts.get(guild=guild, member=234, account="Main") is None
    assert await registrations.remove_member_role(guild=guild, member=234, role=789)
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
    saved_purge_channel = await database.fetch_one(
        "SELECT Guild, RegistrationChannel, Channel FROM WzPurgeChannels "
        "WHERE Guild = ? AND Channel = ?",
        (123, 456),
    )
    assert saved_purge_channel is not None
    assert tuple(saved_purge_channel) == (123, 0, 456)
    assert await purge_channels.remove(guild=guild, channel_id=456)
    assert await purge_channels.get(guild=guild) is None

    assert await servers.remove(guild=guild)
    assert await servers.count_all() == 0


@pytest.mark.asyncio
async def test_repository_reports_failed_foreign_key_write(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="failed-write.db")
    await initialize_database(database)
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=999,
            name="missing guild",
            get_channel_or_thread=lambda channel_id: None,
            get_member=lambda member_id: None,
            get_role=lambda role_id: None,
        ),
    )

    repository = RegistrationSettingsRepository(database)

    assert not await repository.upsert(guild=guild, channel_id=456)
    assert await repository.get(guild=guild) is None


@pytest.mark.asyncio
async def test_wz_registrations_are_isolated_by_channel(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="scoped-registrations.db")
    await initialize_database(database)
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=123,
            name="test guild",
            get_channel_or_thread=lambda channel_id: SimpleNamespace(
                id=channel_id, name=f"channel-{channel_id}"
            ),
            get_member=lambda member_id: SimpleNamespace(
                id=member_id, name="player", display_name="Player One"
            ),
            get_role=lambda role_id: SimpleNamespace(
                id=role_id, name=f"role-{role_id}"
            ),
        ),
    )
    assert await ServerRepository(database).add(guild=guild)

    settings = RegistrationSettingsRepository(database)
    assert await settings.upsert(guild=guild, channel_id=456)
    assert await settings.upsert(guild=guild, channel_id=457)
    registration_records = await settings.get_all(guild=guild)
    assert registration_records is not None
    assert {record.channel for record in registration_records} == {456, 457}

    roles = RegistrationRoleRepository(database)
    assert await roles.add(guild=guild, role=789, channel_id=456)
    assert not await roles.add(guild=guild, role=789, channel_id=457)
    assert await roles.add(guild=guild, role=790, channel_id=457)
    first_roles = await roles.get(guild=guild, channel_id=456)
    second_roles = await roles.get(guild=guild, channel_id=457)
    assert first_roles is not None and [record.role for record in first_roles] == [789]
    assert second_roles is not None and [record.role for record in second_roles] == [
        790
    ]

    members = MemberRegistrationRepository(database)
    assert await members.add(
        guild=guild,
        member=234,
        role=789,
        channel_id=456,
        member_username="player",
        member_display_name="Player Name",
        role_name="WZ Role",
    )
    assert await members.add(guild=guild, member=234, role=790, channel_id=457)
    first_members = await members.get(guild=guild, channel_id=456)
    second_members = await members.get(guild=guild, channel_id=457)
    assert first_members is not None and first_members[0].role == 789
    assert first_members[0].member_username == "player"
    assert first_members[0].member_display_name == "Player Name"
    assert first_members[0].role_name == "WZ Role"
    assert second_members is not None and second_members[0].role == 790

    purge_channels = PurgeChannelRepository(database)
    assert await purge_channels.add(
        guild=guild, channel_id=800, registration_channel_id=456
    )
    assert await purge_channels.add(
        guild=guild, channel_id=801, registration_channel_id=457
    )
    assert not await purge_channels.add(
        guild=guild, channel_id=800, registration_channel_id=457
    )
    first_purge_channels = await purge_channels.get(
        guild=guild, registration_channel_id=456
    )
    second_purge_channels = await purge_channels.get(
        guild=guild, registration_channel_id=457
    )
    assert first_purge_channels is not None
    assert [record.channel_id for record in first_purge_channels] == [800]
    assert second_purge_channels is not None
    assert [record.channel_id for record in second_purge_channels] == [801]
