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
from hmwz.sqlite_db import Base, Database


def make_repositories(database: Database) -> tuple[Base, ...]:
    return (
        ServerRepository(database),
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
        assert await database.execute(repository.table)
    return repositories


@pytest.mark.asyncio
async def test_schema_is_explicit_idempotent_and_referentially_valid(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="schema.db")
    repositories = await initialize_schema(database)

    for repository in repositories:
        assert await database.execute(repository.table)

    tables = await database.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )
    table_names = {row["name"] for row in tables}
    assert table_names == {
        "Servers",
        "Registration_Roles",
        "Registration_Settings",
        "Registration_Members",
        "WzGameAccounts",
        "Registration_Messages",
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
    assert await database.fetch_one("SELECT 1 FROM Registration_Settings") is None


@pytest.mark.asyncio
async def test_legacy_schema_migrates_without_name_caches_and_keeps_aliases(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="legacy-registration.db")
    assert await database.execute(ServerRepository(database).table)
    assert await database.execute(
        "INSERT INTO Servers (Guild, Name) VALUES (?, ?)", (123, "Guild Name")
    )
    assert await database.execute(
        """
        CREATE TABLE DiscordMembers (
            Guild INTEGER, Member INTEGER, Username TEXT, DisplayName TEXT
        )
        """
    )
    assert await database.execute(
        "CREATE TABLE DiscordChannels (Guild INTEGER, Channel INTEGER, Name TEXT)"
    )
    assert await database.execute(
        "CREATE TABLE DiscordRoles (Guild INTEGER, Role INTEGER, Name TEXT)"
    )
    assert await database.execute(
        """
        CREATE TABLE Registration_Settings (
            Guild INTEGER PRIMARY KEY, Channel INTEGER, Message INTEGER, Title TEXT,
            Description TEXT, GuildName TEXT, ChannelName TEXT
        ) WITHOUT ROWID
        """
    )
    assert await database.execute(
        "INSERT INTO Registration_Settings (Guild, Channel, GuildName, ChannelName) "
        "VALUES (?, ?, ?, ?)",
        (123, 456, "Guild Name", "registration-channel"),
    )
    assert await database.execute(RegistrationRoleRepository(database).table)
    assert await database.execute(
        """
        CREATE TABLE Roles (
            Guild INTEGER, Role INTEGER, Permanent BOOLEAN, Score INTEGER,
            GuildName TEXT, RoleName TEXT, PRIMARY KEY (Guild, Role)
        ) WITHOUT ROWID
        """
    )
    assert await database.execute(
        "INSERT INTO Roles VALUES (?, ?, ?, ?, ?, ?)",
        (123, 789, 1, 3, "Guild Name", "registration-role"),
    )
    assert await database.execute(
        """
        CREATE TABLE Registrations_Member (
            Guild INTEGER, Member INTEGER, Account TEXT, Role INTEGER,
            Timestamp TEXT, GuildName TEXT, MemberUsername TEXT,
            MemberDisplayName TEXT, RoleName TEXT,
            PRIMARY KEY (Guild, Member, Account)
        ) WITHOUT ROWID
        """
    )
    assert await database.execute(
        "INSERT INTO Registrations_Member VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)",
        (123, 234, "", 789, "Guild Name", "player", "Player", "role"),
    )
    assert await database.execute(
        "INSERT INTO Registrations_Member VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)",
        (123, 234, "alt-account", 789, "Guild Name", "player", "Player", "role"),
    )
    assert await database.execute(MemberRegistrationRepository(database).table)
    assert await database.execute(
        """
        CREATE TABLE WzPurgeChannels (
            Guild INTEGER NOT NULL, Channel INTEGER NOT NULL,
            GuildName TEXT, ChannelName TEXT,
            PRIMARY KEY (Guild, Channel)
        ) WITHOUT ROWID
        """
    )
    assert await database.execute(
        "INSERT INTO WzPurgeChannels VALUES (?, ?, ?, ?)",
        (123, 321, "Guild Name", "purge-channel"),
    )

    assert await database.remove_legacy_tables()
    for repository in (
        RegistrationSettingsRepository(database),
        RegistrationRoleRepository(database),
        MemberRegistrationRepository(database),
        PurgeChannelRepository(database),
    ):
        assert await repository.migrate_schema()

    roles = await database.fetch_all("SELECT Channel FROM Registration_Roles")
    registrations = await database.fetch_all(
        "SELECT Channel, Alias FROM Registration_Members ORDER BY Alias"
    )
    purge_channels = await database.fetch_all(
        "SELECT RegistrationChannel FROM WzPurgeChannels"
    )
    assert tuple(roles[0]) == (456,)
    assert tuple(tuple(row) for row in registrations) == (
        (456, ""),
        (456, "alt-account"),
    )
    assert tuple(purge_channels[0]) == (456,)

    for table_name in (
        "DiscordMembers",
        "DiscordChannels",
        "DiscordRoles",
        "Registrations_Member",
    ):
        assert (
            await database.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            )
            is None
        )
    for table_name in (
        "Registration_Roles",
        "Registration_Members",
        "Registration_Settings",
        "WzPurgeChannels",
    ):
        columns = await database.fetch_all(f'PRAGMA table_info("{table_name}")')
        column_names = {column["name"] for column in columns}
        assert not {"GuildName", "ChannelName"}.intersection(column_names)
    registration_columns = await database.fetch_all(
        'PRAGMA table_info("Registration_Members")'
    )
    assert {
        "MemberUsername",
        "MemberDisplayName",
        "RoleName",
    }.issubset(column["name"] for column in registration_columns)
    migrated_names = await database.fetch_all(
        """
        SELECT MemberUsername, MemberDisplayName, RoleName
        FROM Registration_Members ORDER BY Alias
        """
    )
    assert tuple(tuple(row) for row in migrated_names) == (
        ("player", "Player", "role"),
        ("player", "Player", "role"),
    )
    assert (
        await database.fetch_one(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'Roles'"
        )
        is None
    )


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
async def test_legacy_registration_tables_are_removed(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="legacy-registration.db")
    for table_name in (
        "QsList",
        "QsRegistration",
        "QsRegistrations",
        "QsRoles",
        "WzConfiguration",
    ):
        assert await database.execute(
            f'CREATE TABLE "{table_name}" (Guild INTEGER PRIMARY KEY)'
        )

    assert await database.remove_legacy_tables()
    assert await database.remove_legacy_tables()
    tables = await database.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )
    assert not {
        "QsList",
        "QsRegistration",
        "QsRegistrations",
        "QsRoles",
        "WzConfiguration",
    }.intersection(row["name"] for row in tables)
