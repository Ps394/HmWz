import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from hmwz.hm_client import Client
from hmwz.i18n.loader import load_translations
from hmwz.modules.hs.qs.module import QsRegistrationModule
from hmwz.modules.hs.qs.commands.reset_roles import QsRolesResetConfirmation
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
from hmwz.modules.registration.commands import RegistrationGroup
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
    assert "qs.overview.registration.new_registration" in hs_catalogs[1]["de"]


def test_hs_command_registration_includes_separate_wz_and_qs_groups() -> None:
    client = Client.__new__(Client)
    client.CommandTree = discord.app_commands.CommandTree(
        discord.Client(intents=discord.Intents.none())
    )
    client.registered_commands = 0

    asyncio.run(Client.register_commands(client))

    assert {command.name for command in client.CommandTree.get_commands()} == {
        "about-bot",
        "purge",
        "account",
        "wz",
        "qs",
        "registration",
        "donation",
        "queue",
    }
    wz = next(
        command for command in client.CommandTree.get_commands() if command.name == "wz"
    )
    qs = next(
        command for command in client.CommandTree.get_commands() if command.name == "qs"
    )
    assert {command.name for command in wz.commands} == {
        "setup",
        "reset-channels",
        "reset-roles",
    }
    assert {command.name for command in qs.commands} == {
        "setup",
        "reset-wz-roles",
        "reset-qs-roles",
    }


def test_registration_command_group_uses_requested_hierarchy() -> None:
    group = RegistrationGroup()

    assert {command.name for command in group.commands} == {
        "csv",
        "deregister",
        "register",
        "reset",
        "setup",
        "remove",
    }
    setup = next(command for command in group.commands if command.name == "setup")
    assert isinstance(setup, discord.app_commands.Command)
    assert not setup.parameters


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


@pytest.mark.asyncio
async def test_qs_role_reset_removes_only_qs_configured_roles() -> None:
    wz_role = Mock(spec=discord.Role)
    wz_role.id = 20
    wz_role.is_default.return_value = False
    wz_role.managed = False
    qs_role = Mock(spec=discord.Role)
    qs_role.id = 21
    qs_role.is_default.return_value = False
    qs_role.managed = False
    member = Mock(spec=discord.Member)
    member.id = 30
    member.roles = [wz_role, qs_role]
    member.remove_roles = AsyncMock()

    async def fetch_members(*, limit: int):
        assert limit is None
        yield member

    guild = Mock(spec=discord.Guild)
    guild.id = 10
    guild.fetch_members = fetch_members
    guild.get_role.side_effect = {21: qs_role}.get
    module = SimpleNamespace(
        roles=SimpleNamespace(
            get=AsyncMock(return_value=[SimpleNamespace(role=21)])
        )
    )
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    message = SimpleNamespace(delete=AsyncMock())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            user=SimpleNamespace(id=1),
            locale=discord.Locale.german,
            client=SimpleNamespace(module_manager=manager),
            response=SimpleNamespace(defer=AsyncMock(), is_done=Mock(return_value=True)),
            message=message,
            followup=SimpleNamespace(send=AsyncMock()),
        ),
    )
    view = QsRolesResetConfirmation(guild=guild, channel_id=40, owner_id=1)
    confirm = next(
        item for item in view.children if item.custom_id == "qs_reset_roles_confirm"
    )

    with patch(
        "hmwz.modules.hs.ephemeral_view.send_temporary_followup",
        new_callable=AsyncMock,
    ):
        await confirm.callback(interaction)

    member.remove_roles.assert_awaited_once_with(
        qs_role, reason="QS Reset Roles"
    )
    module.roles.get.assert_awaited_once_with(guild=guild, channel_id=40)
    message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_qs_role_reset_cancel_deletes_confirmation() -> None:
    guild = Mock(spec=discord.Guild)
    message = SimpleNamespace(delete=AsyncMock())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            locale=discord.Locale.german,
            response=SimpleNamespace(
                defer=AsyncMock(), is_done=Mock(return_value=False)
            ),
            message=message,
            delete_original_response=AsyncMock(),
            followup=SimpleNamespace(send=AsyncMock()),
        ),
    )
    view = QsRolesResetConfirmation(guild=guild, channel_id=40, owner_id=1)
    cancel = next(
        item for item in view.children if item.custom_id == "qs_reset_roles_cancel"
    )

    with patch(
        "hmwz.modules.hs.ephemeral_view.send_temporary_followup",
        new_callable=AsyncMock,
    ):
        await cancel.callback(interaction)

    interaction.response.defer.assert_awaited_once_with(
        ephemeral=True, thinking=True
    )
    message.delete.assert_awaited_once()
    interaction.delete_original_response.assert_awaited_once()
