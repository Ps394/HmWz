from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.hm_client.repositories import DiscordEntityRepository, ServerRepository
from hmwz.modules.hs.account.repositories import MemberGameAccountRepository
from hmwz.modules.hs.wz.repositories import (
    MemberRegistrationRepository,
    PurgeChannelRepository,
    RegistrationMessageRepository,
    RegistrationRoleRepository,
    RegistrationSettingsRepository,
    WzConfigurationRepository,
)
from hmwz.sqlite_db import Base, Database


def make_repositories(database: Database) -> tuple[Base, ...]:
    return (
        ServerRepository(database),
        DiscordEntityRepository(database),
        WzConfigurationRepository(database),
        RegistrationRoleRepository(database),
        RegistrationSettingsRepository(database),
        MemberRegistrationRepository(database),
        MemberGameAccountRepository(database),
        RegistrationMessageRepository(database),
        PurgeChannelRepository(database),
    )


async def initialize_schema(database: Database) -> tuple[Base, ...]:
    repositories = make_repositories(database)
    for repository in repositories:
        statements = (
            repository.tables
            if isinstance(repository, DiscordEntityRepository)
            else (repository.table,)
        )
        for statement in statements:
            assert await database.execute(statement)
    return repositories


@pytest.mark.asyncio
async def test_schema_is_explicit_idempotent_and_referentially_valid(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="schema.db")
    repositories = await initialize_schema(database)

    for repository in repositories:
        statements = (
            repository.tables
            if isinstance(repository, DiscordEntityRepository)
            else (repository.table,)
        )
        for statement in statements:
            assert await database.execute(statement)

    tables = await database.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )
    table_names = {row["name"] for row in tables}
    assert table_names == {
        "Servers",
        "DiscordMembers",
        "DiscordChannels",
        "DiscordRoles",
        "WzConfiguration",
        "WzRoles",
        "WzRegistration",
        "WzRegistrations",
        "WzGameAccounts",
        "WzList",
        "WzPurgeChannels",
    }

    for table_name in table_names - {"Servers"}:
        foreign_keys = await database.fetch_all(
            f'PRAGMA foreign_key_list("{table_name}")'
        )
        for foreign_key in foreign_keys:
            assert foreign_key["table"] == "Servers"

    assert not await database.fetch_all("PRAGMA foreign_key_check")


@pytest.mark.asyncio
async def test_schema_enforces_server_foreign_keys(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="foreign-keys.db")
    await initialize_schema(database)

    repository = RegistrationSettingsRepository(database)
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=987654321,
            name="missing guild",
            get_channel_or_thread=lambda channel_id: None,
            get_member=lambda member_id: None,
        ),
    )

    executed = await repository.upsert(
        guild=guild,
        channel_id=456,
    )

    assert not executed
    assert await database.fetch_one("SELECT 1 FROM WzRegistration") is None


@pytest.mark.asyncio
async def test_wz_table_name_columns_migrate_and_backfill(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="wz-name-migration.db")
    servers = ServerRepository(database)
    entities = DiscordEntityRepository(database)
    assert await database.execute(servers.table)
    for statement in entities.tables:
        assert await database.execute(statement)

    assert await database.execute(
        "INSERT INTO Servers (Guild, Name) VALUES (?, ?)", (123, "Guild Name")
    )
    assert await database.execute(
        "INSERT INTO DiscordMembers (Guild, Member, Username, DisplayName) "
        "VALUES (?, ?, ?, ?)",
        (123, 234, "player-name", "Player Nickname"),
    )
    assert await database.execute(
        "INSERT INTO DiscordChannels (Guild, Channel, Name) VALUES (?, ?, ?)",
        (123, 456, "registration-channel"),
    )
    assert await database.execute(
        "INSERT INTO DiscordRoles (Guild, Role, Name) VALUES (?, ?, ?)",
        (123, 789, "registration-role"),
    )

    assert await database.execute(
        "CREATE TABLE WzRoles (Guild INTEGER, Role INTEGER, Permanent BOOLEAN, "
        "Score INTEGER DEFAULT 1, PRIMARY KEY (Guild, Role)) WITHOUT ROWID"
    )
    assert await database.execute(
        "INSERT INTO WzRoles (Guild, Role, Permanent, Score) VALUES (?, ?, ?, ?)",
        (123, 789, 1, 3),
    )
    assert await database.execute(
        "CREATE TABLE WzRegistrations (Guild INTEGER, Member INTEGER, Role INTEGER, "
        "Timestamp TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (Guild, Member)) "
        "WITHOUT ROWID"
    )
    assert await database.execute(
        "INSERT INTO WzRegistrations (Guild, Member, Role) VALUES (?, ?, ?)",
        (123, 234, 789),
    )
    assert await database.execute(
        "CREATE TABLE WzRegistration (Guild INTEGER PRIMARY KEY, Channel INTEGER, "
        "Message INTEGER, Title TEXT, Description TEXT) WITHOUT ROWID"
    )
    assert await database.execute(
        "INSERT INTO WzRegistration (Guild, Channel) VALUES (?, ?)", (123, 456)
    )
    assert await database.execute(
        "CREATE TABLE WzPurgeChannels (Guild INTEGER NOT NULL, Channel INTEGER NOT NULL, "
        "PRIMARY KEY (Guild, Channel)) WITHOUT ROWID"
    )
    assert await database.execute(
        "INSERT INTO WzPurgeChannels (Guild, Channel) VALUES (?, ?)", (123, 456)
    )

    repositories = (
        RegistrationRoleRepository(database),
        MemberRegistrationRepository(database),
        RegistrationSettingsRepository(database),
        PurgeChannelRepository(database),
    )
    for repository in repositories:
        assert await repository.migrate_names()

    expected = {
        "WzRoles": (
            "SELECT GuildName, RoleName FROM WzRoles",
            ("Guild Name", "registration-role"),
        ),
        "WzRegistrations": (
            "SELECT GuildName, MemberUsername, MemberDisplayName, RoleName "
            "FROM WzRegistrations",
            ("Guild Name", "player-name", "Player Nickname", "registration-role"),
        ),
        "WzRegistration": (
            "SELECT GuildName, ChannelName FROM WzRegistration",
            ("Guild Name", "registration-channel"),
        ),
        "WzPurgeChannels": (
            "SELECT GuildName, ChannelName FROM WzPurgeChannels",
            ("Guild Name", "registration-channel"),
        ),
    }
    for query, expected_values in expected.values():
        row = await database.fetch_one(query)
        assert row is not None
        assert tuple(row) == expected_values

    migrated_role = await database.fetch_one(
        "SELECT Channel FROM WzRoles WHERE Guild = ? AND Role = ?",
        (123, 789),
    )
    assert migrated_role is not None and migrated_role["Channel"] == 456
    migrated_registration = await database.fetch_one(
        "SELECT Channel FROM WzRegistrations WHERE Guild = ? AND Member = ?",
        (123, 234),
    )
    assert migrated_registration is not None
    assert migrated_registration["Channel"] == 456
    migrated_purge_channel = await database.fetch_one(
        "SELECT RegistrationChannel FROM WzPurgeChannels "
        "WHERE Guild = ? AND Channel = ?",
        (123, 456),
    )
    assert migrated_purge_channel is not None
    assert migrated_purge_channel["RegistrationChannel"] == 456

    migrated_columns = await database.fetch_all('PRAGMA table_info("WzRegistrations")')
    account_column = next(
        column for column in migrated_columns if column["name"] == "Account"
    )
    assert account_column["pk"] > 0
    assert await database.execute(
        """
        INSERT INTO WzRegistrations
        (Guild, Member, Account, Role, Timestamp)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (123, 234, "alt-account", 789),
    )
    account_rows = await database.fetch_all(
        "SELECT Account FROM WzRegistrations WHERE Guild = ? AND Member = ? "
        "ORDER BY Account",
        (123, 234),
    )
    assert tuple(row["Account"] for row in account_rows) == ("", "alt-account")


@pytest.mark.asyncio
async def test_discord_entity_names_are_saved_and_updated(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="entity-names.db")
    servers = ServerRepository(database)
    entities = DiscordEntityRepository(database)
    assert await database.execute(servers.table)
    for statement in entities.tables:
        assert await database.execute(statement)

    guild_data = SimpleNamespace(
        id=123,
        name="test guild",
        members=[],
        channels=[],
        threads=[],
        roles=[],
        get_channel_or_thread=lambda channel_id: None,
        get_member=lambda member_id: None,
        get_role=lambda role_id: None,
    )
    guild = cast(discord.Guild, guild_data)
    member = cast(
        discord.Member,
        SimpleNamespace(id=234, name="player", display_name="Player Nickname"),
    )
    channel = cast(
        discord.TextChannel,
        SimpleNamespace(id=456, name="registration"),
    )
    assert await servers.add(guild=guild)
    assert await entities.add_member(guild=guild, member=member)
    assert await entities.add_channel(guild=guild, channel=channel)
    updated_member = cast(
        discord.Member,
        SimpleNamespace(id=234, name="updated-player", display_name="Updated Nickname"),
    )
    updated_channel = cast(
        discord.TextChannel,
        SimpleNamespace(id=456, name="wz"),
    )
    updated_role = cast(
        discord.Role,
        SimpleNamespace(
            id=789,
            name="Registration",
            guild=guild,
        ),
    )
    assert await entities.add_member(guild=guild, member=updated_member)
    assert await entities.add_channel(guild=guild, channel=updated_channel)
    assert await entities.add_role(role=updated_role)

    guild_data.members = [updated_member]
    guild_data.channels = [updated_channel]
    guild_data.roles = [updated_role]
    assert await entities.sync_guild(guild)

    stored_member = await database.fetch_one(
        "SELECT Username, DisplayName FROM DiscordMembers WHERE Guild = ? AND Member = ?",
        (123, 234),
    )
    stored_channel = await database.fetch_one(
        "SELECT Name FROM DiscordChannels WHERE Guild = ? AND Channel = ?",
        (123, 456),
    )
    stored_role = await database.fetch_one(
        "SELECT Name FROM DiscordRoles WHERE Guild = ? AND Role = ?",
        (123, 789),
    )
    assert stored_member is not None
    assert tuple(stored_member) == ("updated-player", "Updated Nickname")
    assert stored_channel is not None
    assert stored_channel["Name"] == "wz"
    assert stored_role is not None
    assert stored_role["Name"] == "Registration"
    assert await entities.member_log_name(guild, 234) == (
        "updated-player / Updated Nickname (234)"
    )
    assert await entities.channel_log_name(guild, 456) == "wz (456)"
    assert await entities.role_log_name(guild, 789) == "Registration (789)"


@pytest.mark.asyncio
async def test_legacy_server_rows_are_copied_and_old_table_is_removed(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="legacy.db")
    assert await database.execute(
        "CREATE TABLE Server (Guild INTEGER PRIMARY KEY, Name TEXT)"
    )
    assert await database.execute(
        "INSERT INTO Server (Guild, Name) VALUES (?, ?)",
        (123, "legacy guild"),
    )

    repository = ServerRepository(database)
    assert await database.execute(repository.table)
    assert await repository.migrate_legacy_servers()
    assert await repository.migrate_legacy_servers()

    migrated = await database.fetch_one(
        "SELECT Guild, Name FROM Servers WHERE Guild = ?",
        (123,),
    )
    legacy = await database.fetch_one(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("Server",),
    )
    assert migrated is not None
    assert tuple(migrated) == (123, "legacy guild")
    assert legacy is None


@pytest.mark.asyncio
async def test_legacy_configuration_tables_are_migrated_and_removed(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="legacy-configuration.db")
    servers = ServerRepository(database)
    assert await database.execute(servers.table)
    guild = cast(discord.Guild, SimpleNamespace(id=321, name="legacy guild"))
    assert await servers.add(guild=guild)
    other_guild = cast(
        discord.Guild, SimpleNamespace(id=322, name="another legacy guild")
    )
    assert await servers.add(guild=other_guild)
    for table_name in ("Configuration", "WzConfig"):
        assert await database.execute(
            f"""
            CREATE TABLE "{table_name}" (
                Guild INTEGER PRIMARY KEY,
                ChannelID INTEGER,
                ScoreModLvl BOOLEAN DEFAULT 0,
                Matchmaker BOOLEAN DEFAULT 0
            )
            """
        )
    assert await database.execute(
        "INSERT INTO Configuration (Guild, ChannelID, ScoreModLvl, Matchmaker) "
        "VALUES (?, ?, ?, ?)",
        (321, 654, 1, 0),
    )
    assert await database.execute(
        "INSERT INTO WzConfig (Guild, ChannelID, ScoreModLvl, Matchmaker) "
        "VALUES (?, ?, ?, ?)",
        (322, 655, 0, 1),
    )

    configuration = WzConfigurationRepository(database)
    assert await configuration.migrate_legacy_configuration()
    assert await configuration.migrate_legacy_configuration()

    migrated = await database.fetch_all(
        "SELECT Guild, ChannelID, ScoreModLvl, Matchmaker "
        "FROM WzConfiguration ORDER BY Guild"
    )
    assert [tuple(row) for row in migrated] == [
        (321, 654, 1, 0),
        (322, 655, 0, 1),
    ]
    for table_name in ("Configuration", "WzConfig"):
        legacy = await database.fetch_one(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        )
        assert legacy is None
