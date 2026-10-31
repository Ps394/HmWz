import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.client import Client
from hmwz.client.repositories import ServerRepository
from hmwz.modules import manager as manager_module
from hmwz.modules.hs.wz import WzModule
from hmwz.modules.hs.wz.models import Role
from hmwz.modules.hs.wz.repositories import RoleRepository
from hmwz.modules.hs.wz.commands.setup.channel.add import add as add_channel
from hmwz.modules.hs.wz.commands.setup.channel.remove import remove as remove_channel
from hmwz.modules.hs.wz.commands.setup.menu import setup
from hmwz.modules.hs.wz.commands.setup.role.add import add as add_role
from hmwz.modules.hs.wz.commands.setup.role.operations import RoleSetupOperations
from hmwz.modules.hs.wz.commands.setup.role.remove import remove as remove_role
from hmwz.modules.manager import Manager
from hmwz.modules.registry import REGISTRY
from hmwz.modules.registration import RegistrationModule
from hmwz.sqlite_db import Database


async def make_module(tmp_path: Path) -> WzModule:
    database = Database(folder=str(tmp_path), filename="independent-wz.db")
    guild = Mock(spec=discord.Guild)
    guild.id = 123
    guild.name = "test guild"
    guild.me = None
    guild.get_channel_or_thread.return_value = None
    client = cast(Client, SimpleNamespace(_database=database))
    assert await database.execute(ServerRepository(database).table)
    assert await ServerRepository(database).add(guild=guild)
    module = WzModule(guild, client)
    assert await module.sync(startup=True)
    return module


@pytest.mark.asyncio
async def test_wz_is_registered_and_manager_can_create_it_without_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = await make_module(tmp_path)
    assert WzModule in REGISTRY
    assert not isinstance(module, RegistrationModule)
    monkeypatch.setattr(manager_module, "REGISTRY", [WzModule])
    manager = Manager(module.client)
    managed = await manager.get_module(module.guild, WzModule)
    assert isinstance(managed, WzModule)
    assert await managed.sync()
    assert await manager.get_module(module.guild, WzModule) is managed
    tables = await module.database.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )
    assert {row["name"] for row in tables} == {"Servers", "HsWzChannels", "HsWzRoles"}
    assert not hasattr(managed, "registration")
    assert not hasattr(managed, "registrations")
    assert not hasattr(managed, "game_accounts")
    assert not hasattr(managed, "compose_registration_overview")


@pytest.mark.asyncio
async def test_wz_role_removal_and_guild_cleanup_leave_registration_data_untouched(
    tmp_path: Path,
) -> None:
    module = await make_module(tmp_path)
    database = module.database
    assert await database.execute(
        "CREATE TABLE Registration_Roles (Guild INTEGER, Role INTEGER)"
    )
    assert await database.execute(
        "INSERT INTO Registration_Roles VALUES (?, ?)", (123, 800)
    )
    assert await module.roles.add(guild=module.guild, role=800)
    assert await module.roles.add(guild=module.guild, role=801)
    assert await module.channels.add(guild=module.guild, channel_id=900)
    role = SimpleNamespace(id=800, mention="<@&800>")
    module.guild.get_role.side_effect = {800: role}.get
    member = SimpleNamespace(id=1, roles=[role], remove_roles=AsyncMock())

    async def fetch_members(*, limit: None):
        yield member

    module.guild.fetch_members = fetch_members
    operations = RoleSetupOperations(guild=module.guild, module=module)
    await operations.remove(cast(discord.Interaction, SimpleNamespace()), [800])
    member.remove_roles.assert_awaited_once_with(role, reason="WZ Setup Role Removal")
    assert [record.role for record in await module.roles.get(guild=module.guild)] == [
        801
    ]
    assert await module.on_guild_remove(module.guild)
    assert await module.roles.get(guild=module.guild) is None
    assert await module.channels.get(guild=module.guild) is None
    rows = await database.fetch_all("SELECT Guild, Role FROM Registration_Roles")
    assert [tuple(row) for row in rows] == [(123, 800)]


@pytest.mark.asyncio
async def test_wz_deleted_discord_entities_only_remove_own_settings(
    tmp_path: Path,
) -> None:
    module = await make_module(tmp_path)
    assert await module.roles.add(guild=module.guild, role=800)
    assert await module.channels.add(guild=module.guild, channel_id=900)
    other_guild = SimpleNamespace(id=456)
    assert not await module.on_guild_role_delete(
        cast(discord.Role, SimpleNamespace(guild=other_guild, id=800))
    )
    assert not await module.on_guild_channel_delete(
        cast(discord.abc.GuildChannel, SimpleNamespace(guild=other_guild, id=900))
    )
    assert await module.on_guild_role_delete(
        cast(discord.Role, SimpleNamespace(guild=module.guild, id=800))
    )
    assert await module.on_guild_channel_delete(
        cast(discord.abc.GuildChannel, SimpleNamespace(guild=module.guild, id=900))
    )
    assert await module.roles.get(guild=module.guild) is None
    assert await module.channels.get(guild=module.guild) is None


@pytest.mark.asyncio
async def test_wz_setup_menu_needs_no_registration(tmp_path: Path) -> None:
    module = await make_module(tmp_path)
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    interaction = SimpleNamespace(
        guild=module.guild,
        user=SimpleNamespace(id=1),
        client=SimpleNamespace(module_manager=manager),
        response=SimpleNamespace(send_message=AsyncMock()),
        original_response=AsyncMock(),
    )
    await setup.callback(interaction)
    manager.get_module.assert_awaited_once_with(module.guild, WzModule)
    interaction.response.send_message.assert_awaited_once()
    embed = interaction.response.send_message.await_args.kwargs["embed"]
    assert embed.title == "WZ · Server-Einstellungen"
    assert [field.name for field in embed.fields] == [
        "WZ-Rollen",
        "Bereinigungskanäle",
    ]
    assert all(not field.inline for field in embed.fields)
    assert "**0/25**" in embed.description
    assert "Anmeldung" not in embed.description


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command", [add_channel, remove_channel, add_role, remove_role]
)
async def test_wz_setup_actions_use_guild_settings_without_setup_channel(
    tmp_path: Path, command: discord.app_commands.Command
) -> None:
    module = await make_module(tmp_path)
    role = Mock(spec=discord.Role)
    role.id = 800
    role.name = "WZ"
    role.managed = False
    role.is_default.return_value = False
    second_role = Mock(spec=discord.Role)
    second_role.id = 801
    second_role.name = "WZ second"
    second_role.managed = False
    second_role.is_default.return_value = False
    module.guild.roles = [role, second_role]
    module.guild.get_role.side_effect = {800: role, 801: second_role}.get
    channel = Mock(spec=discord.TextChannel)
    channel.id = 900
    channel.name = "cleanup"
    channel.guild = module.guild
    module.guild.me = (
        Mock(spec=discord.Member) if command in [add_channel, remove_channel] else None
    )
    channel.permissions_for.return_value = SimpleNamespace(view_channel=True)
    module.guild.text_channels = [channel]
    module.guild.get_channel.side_effect = {900: channel}.get
    if command is remove_channel:
        assert await module.channels.add(guild=module.guild, channel_id=900)
    if command is remove_role:
        assert await module.roles.add(guild=module.guild, role=800)
        assert await module.roles.add(guild=module.guild, role=801)
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    interaction = SimpleNamespace(
        guild=module.guild,
        channel_id=None,
        user=SimpleNamespace(id=1),
        client=SimpleNamespace(module_manager=manager),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await command.callback(interaction)
    manager.get_module.assert_awaited_once_with(module.guild, WzModule)
    interaction.followup.send.assert_awaited_once()
    assert "view" in interaction.followup.send.await_args.kwargs


@pytest.mark.asyncio
async def test_wz_role_limit_is_atomic_and_scoped_to_each_guild(tmp_path: Path) -> None:
    module = await make_module(tmp_path)
    repository = module.roles
    assert Role.MAX_PER_GUILD == 25
    for role_id in range(24):
        assert await repository.add(guild=module.guild, role=role_id)
    results = await asyncio.gather(
        repository.add(guild=module.guild, role=24),
        repository.add(guild=module.guild, role=25),
    )
    assert sorted(results) == [False, True]
    records = await repository.get(guild=module.guild)
    assert records is not None and len(records) == 25
    assert not await repository.add(guild=module.guild, role=26)
    assert await repository.add(guild=module.guild, role=0)
    other_guild = Mock(spec=discord.Guild)
    other_guild.id = 124
    other_guild.name = "other guild"
    assert await ServerRepository(module.database).add(guild=other_guild)
    assert await repository.add(guild=other_guild, role=26)
    assert await repository.get(guild=other_guild) == (Role(guild_id=124, role=26),)
    assert await repository.remove(guild=module.guild, role=0)
    assert await repository.add(guild=module.guild, role=26)


@pytest.mark.asyncio
async def test_role_migration_removes_permanence_without_dropping_roles(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="old-wz-roles.db")
    assert await database.execute(ServerRepository(database).table)
    assert await database.execute(
        "INSERT INTO Servers (Guild, Name) VALUES (123, 'test guild')"
    )
    assert await database.execute("""
        CREATE TABLE HsWzRoles (
            Guild INTEGER NOT NULL, Role INTEGER NOT NULL,
            Permanent BOOLEAN NOT NULL DEFAULT 0,
            PRIMARY KEY (Guild, Role),
            FOREIGN KEY (Guild) REFERENCES Servers(Guild)
        ) WITHOUT ROWID
    """)
    for role_id in range(26):
        assert await database.execute(
            "INSERT INTO HsWzRoles VALUES (?, ?, ?)", (123, role_id, role_id % 2)
        )
    repository = RoleRepository(database)
    assert await repository.migrate_schema()
    assert await repository.migrate_schema()
    columns = await database.fetch_all("PRAGMA table_info(HsWzRoles)")
    assert {row["name"] for row in columns} == {"Guild", "Role"}
    guild = Mock(spec=discord.Guild)
    guild.id = 123
    guild.name = "test guild"
    records = await repository.get(guild=guild)
    assert records is not None and [record.role for record in records] == list(
        range(26)
    )
    assert not hasattr(records[0], "permanent")
    assert not await repository.add(guild=guild, role=26)


@pytest.mark.asyncio
async def test_last_wz_role_can_be_removed(tmp_path: Path) -> None:
    module = await make_module(tmp_path)
    assert await module.roles.add(guild=module.guild, role=800)
    role = SimpleNamespace(id=800, mention="<@&800>")
    module.guild.get_role.return_value = role
    member = SimpleNamespace(id=1, roles=[role], remove_roles=AsyncMock())

    async def fetch_members(*, limit: None):
        yield member

    module.guild.fetch_members = fetch_members
    operations = RoleSetupOperations(guild=module.guild, module=module)
    await operations.remove(cast(discord.Interaction, SimpleNamespace()), [800])
    member.remove_roles.assert_awaited_once_with(role, reason="WZ Setup Role Removal")
    assert await module.roles.get(guild=module.guild) is None
