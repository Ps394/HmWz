from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.modules.hs.qs.module import QsRegistrationModule
from hmwz.modules.hs.qs.commands import QsSetupGroup
from hmwz.modules.hs.qs.commands.setup.configure import configure
from hmwz.modules.hs.qs.repositories import (
    QSMemberRegistrationRepository,
    QSRegistrationMessageRepository,
    QSRegistrationRoleRepository,
    QSRegistrationSettingsRepository,
)
from hmwz.modules.hs.wz.repositories import (
    MemberRegistrationRepository,
    RegistrationMessageRepository,
    RegistrationRoleRepository,
    RegistrationSettingsRepository,
)
from hmwz.sqlite_db import Database


def test_qs_setup_group_registers_configure_command() -> None:
    group = QsSetupGroup()

    assert {command.name for command in group.commands} == {
        "configure",
        "message",
        "role-add",
        "role-remove",
    }
    assert [parameter.name for parameter in configure.parameters] == ["role"]


@pytest.mark.asyncio
async def test_qs_registration_repositories_use_independent_tables(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="qs-registration.db")
    repositories = (
        RegistrationSettingsRepository(database),
        RegistrationRoleRepository(database),
        MemberRegistrationRepository(database),
        RegistrationMessageRepository(database),
        QSRegistrationSettingsRepository(database),
        QSRegistrationRoleRepository(database),
        QSMemberRegistrationRepository(database),
        QSRegistrationMessageRepository(database),
    )
    for repository in repositories:
        assert await database.execute(repository.table)

    for table_name in (
        "WzRegistration",
        "WzRoles",
        "WzRegistrations",
        "WzList",
        "QsRegistration",
        "QsRoles",
        "QsRegistrations",
        "QsList",
    ):
        assert await database.fetch_one(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        )

    assert (
        QSRegistrationSettingsRepository.table_name
        != RegistrationSettingsRepository.table_name
    )
    assert (
        QSRegistrationRoleRepository.table_name != RegistrationRoleRepository.table_name
    )
    assert (
        QSMemberRegistrationRepository.table_name
        != MemberRegistrationRepository.table_name
    )
    assert (
        QSRegistrationMessageRepository.table_name
        != RegistrationMessageRepository.table_name
    )


@pytest.mark.asyncio
async def test_qs_registration_has_no_player_limit(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="qs-capacity.db")
    guild = cast(
        discord.Guild,
        SimpleNamespace(id=1, name="test guild"),
    )
    client = SimpleNamespace(_database=database)
    module = QsRegistrationModule(guild, cast(discord.Client, client))

    member = Mock(spec=discord.Member)
    member.id = 20
    role = Mock(spec=discord.Role)
    role.id = 30
    role.name = "Player"
    response = SimpleNamespace(defer=AsyncMock())
    followup = SimpleNamespace(send=AsyncMock())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            guild=guild,
            user=member,
            channel_id=40,
            response=response,
            followup=followup,
        ),
    )
    module.entities.add_member = AsyncMock(return_value=True)
    module.registrations.get = AsyncMock(return_value=None)
    module.registrations.count = AsyncMock(return_value=40)
    module.registrations.add = AsyncMock(return_value=True)
    module.compose_registration_overview = AsyncMock(return_value=True)
    member.add_roles = AsyncMock()

    await module._handle_registration(interaction, role)

    module.registrations.count.assert_not_awaited()
    module.registrations.add.assert_awaited_once()
    member.add_roles.assert_awaited_once()
    followup.send.assert_awaited_once()
