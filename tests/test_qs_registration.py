from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.modules.hs.qs.module import QsRegistrationModule
from hmwz.modules.hs.qs.commands import QsGroup
from hmwz.modules.hs.qs.commands.setup import QsSetupGroup
from hmwz.modules.hs.qs.commands.setup.configure import configure
from hmwz.modules.registration.commands import RegistrationGroup
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
from hmwz.i18n.loader import load_translations
from hmwz.sqlite_db import Database


def test_qs_translations_are_owned_by_hs_catalog() -> None:
    modules_dir = Path(__file__).parents[1] / "src" / "hmwz" / "modules"
    registration_catalogs = (
        load_translations(modules_dir / "registration" / "i18n" / "command"),
        load_translations(modules_dir / "registration" / "i18n" / "runtime"),
    )
    hs_catalogs = (
        load_translations(modules_dir / "hs" / "i18n" / "command"),
        load_translations(modules_dir / "hs" / "i18n" / "runtime"),
    )

    assert all(
        not any(
            key.startswith("qs.")
            for translations in catalogs.values()
            for key in translations
        )
        for catalogs in registration_catalogs
    )
    assert "group.description.qs.group" in hs_catalogs[0]["de"]
    assert "qs.registration.error.not_configured" in hs_catalogs[1]["de"]


def test_qs_setup_group_registers_configure_command() -> None:
    group = QsSetupGroup()

    assert {command.name for command in group.commands} == {
        "configure",
        "message",
        "role-add",
        "role-remove",
    }
    assert [parameter.name for parameter in configure.parameters] == ["role"]


def test_qs_commands_remain_registered_in_hs_module() -> None:
    group = QsGroup()

    assert {command.name for command in group.commands} == {"reset", "setup"}


def test_registration_command_group_uses_requested_hierarchy() -> None:
    group = RegistrationGroup()

    assert {command.name for command in group.commands} == {
        "csv",
        "deregister",
        "register",
        "reset",
        "setup",
    }
    setup = next(command for command in group.commands if command.name == "setup")
    assert isinstance(setup, discord.app_commands.Group)
    assert {command.name for command in setup.commands} == {
        "configure",
        "event-log",
        "message",
        "remove",
        "roles-add",
        "roles-delete",
    }


@pytest.mark.asyncio
async def test_qs_registration_repositories_use_shared_tables(
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
        "Registration_Settings",
        "Registration_Roles",
        "Registration_Members",
        "Registration_Messages",
    ):
        assert await database.fetch_one(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        )

    assert QSRegistrationSettingsRepository is RegistrationSettingsRepository
    assert QSRegistrationRoleRepository is RegistrationRoleRepository
    assert QSMemberRegistrationRepository is MemberRegistrationRepository
    assert QSRegistrationMessageRepository is RegistrationMessageRepository
    assert not await database.fetch_all(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name IN (
            'QsList', 'QsRegistration', 'QsRegistrations', 'QsRoles'
        )
        """
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
