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
from hmwz.sqlite_db import Base, Database


def make_repositories(database: Database) -> tuple[Base, ...]:
    return (
        ServerRepository(database),
        WzConfigurationRepository(database),
        RegistrationRoleRepository(database),
        RegistrationSettingsRepository(database),
        MemberRegistrationRepository(database),
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
        "Configuration",
        "WzRoles",
        "WzRegistration",
        "WzRegistrations",
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
        SimpleNamespace(id=987654321, name="missing guild"),
    )

    executed = await repository.upsert(
        guild=guild,
        channel_id=456,
    )

    assert not executed
    assert await database.fetch_one("SELECT 1 FROM WzRegistration") is None


@pytest.mark.asyncio
async def test_legacy_server_rows_are_copied_without_removing_the_old_table(
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
        "SELECT Guild, Name FROM Server WHERE Guild = ?",
        (123,),
    )
    assert migrated is not None
    assert tuple(migrated) == (123, "legacy guild")
    assert legacy is not None
