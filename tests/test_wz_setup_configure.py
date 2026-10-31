from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import discord
import pytest

from hmwz.emojis import emojis
from hmwz.i18n import RuntimeLocalizations, t
from hmwz.modules.registration.commands import RegistrationGroup
from hmwz.modules.registration.commands.setup.config import (
    RegistrationConfigView,
    RegistrationExportChannelSelect,
    RegistrationExportChannelView,
    RegistrationRoleRemovalSelect,
    RegistrationRoleRemovalView,
    _configuration_message,
)
from hmwz.modules.registration.repositories import RegistrationSettingsRepository
from hmwz.sqlite_db import Database


@pytest.mark.asyncio
async def test_registration_settings_create_is_unique_per_guild_and_channel(
    tmp_path,
) -> None:
    database = Database(folder=str(tmp_path), filename="registration-create.db")
    repository = RegistrationSettingsRepository(database)
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=10,
            name="test guild",
            get_channel_or_thread=lambda _channel_id: None,
        ),
    )

    assert await database.execute("CREATE TABLE Servers (Guild INTEGER PRIMARY KEY)")
    assert await database.execute(repository.table)
    assert await database.execute("INSERT INTO Servers (Guild) VALUES (?)", (guild.id,))

    assert await repository.create(guild=guild, channel_id=20)
    assert not await repository.create(guild=guild, channel_id=20)
    assert await repository.create(guild=guild, channel_id=21)


def test_registration_setup_is_a_root_command() -> None:
    group = RegistrationGroup()

    assert {"setup", "remove"}.issubset({command.name for command in group.commands})


@pytest.mark.asyncio
async def test_registration_config_shows_json_export_channel() -> None:
    registration_channel = SimpleNamespace(id=20, mention="<#20>")
    export_channel = SimpleNamespace(id=30, mention="<#30>")
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    guild.me = object()
    guild.get_channel.side_effect = {20: registration_channel, 30: export_channel}.get
    module = SimpleNamespace(
        guild=guild,
        module_key="registration",
        registration=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(title="Title", description=""))
        ),
        roles=SimpleNamespace(get=AsyncMock(return_value=None)),
        registration_event_channel=SimpleNamespace(get=AsyncMock(return_value=30)),
    )
    interaction = SimpleNamespace(
        guild=guild,
        locale=discord.Locale.german,
    )

    view = RegistrationConfigView(module, 20, owner_id=1)
    message = await _configuration_message(module, interaction, 20)

    assert any(field.value == "<#30>" for field in message.fields)
    assert all(not field.inline for field in message.fields)
    assert not any("Individuell festgelegt" in field.value for field in message.fields)
    assert message.footer.text == "|"
    assert message.timestamp is not None
    assert any(
        item.custom_id == "wz_registration_config_export_channel"
        for item in view.children
    )
    apply_button = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_config_apply"
    )
    assert apply_button.emoji.name == "✅"


@pytest.mark.asyncio
async def test_registration_setup_apply_closes_the_menu() -> None:
    guild = Mock(spec=discord.Guild)
    module = SimpleNamespace(guild=guild)
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()),
        delete_original_response=AsyncMock(),
    )
    view = RegistrationConfigView(module, channel_id=20, owner_id=1)
    apply_button = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_config_apply"
    )

    await apply_button.callback(interaction)

    interaction.response.defer.assert_awaited_once_with()
    interaction.delete_original_response.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_registration_role_removal_preserves_minimum_role_count() -> None:
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    module = SimpleNamespace(
        guild=guild,
        module_key="registration",
        roles=SimpleNamespace(
            get=AsyncMock(return_value=(SimpleNamespace(role=11),)),
            remove=AsyncMock(return_value=True),
        ),
        registrations=SimpleNamespace(remove=AsyncMock(return_value=True)),
    )
    interaction = SimpleNamespace(
        locale=discord.Locale.german,
        response=SimpleNamespace(
            send_message=AsyncMock(),
            defer=AsyncMock(),
        ),
    )
    view = RegistrationRoleRemovalView(
        module,
        channel_id=20,
        owner_id=1,
        configured_roles=[(11, "Role", True)],
    )
    confirm = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_config_role_remove_confirm"
    )

    with patch.object(
        RegistrationRoleRemovalSelect,
        "values",
        new_callable=PropertyMock,
        return_value=["11"],
    ):
        await confirm.callback(interaction)

    interaction.response.send_message.assert_awaited_once()
    interaction.response.defer.assert_not_awaited()
    module.roles.remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_registration_role_removal_clears_config_registrations_and_discord_role() -> (
    None
):
    role = Mock(spec=discord.Role)
    member = Mock(spec=discord.Member)
    member.id = 12
    member.roles = [role]
    member.remove_roles = AsyncMock()
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    guild.get_role.side_effect = {11: role}.get
    roles = SimpleNamespace(
        get=AsyncMock(
            return_value=(SimpleNamespace(role=11), SimpleNamespace(role=13))
        ),
        remove=AsyncMock(return_value=True),
    )
    registrations = SimpleNamespace(
        get=AsyncMock(return_value=(SimpleNamespace(member=12),)),
        remove=AsyncMock(return_value=True),
    )
    module = SimpleNamespace(
        guild=guild,
        module_key="registration",
        roles=roles,
        registrations=registrations,
        compose_registration_overview=AsyncMock(return_value=True),
    )
    interaction = SimpleNamespace(
        locale=discord.Locale.german,
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    view = RegistrationRoleRemovalView(
        module,
        channel_id=20,
        owner_id=1,
        configured_roles=[(11, "Role", True), (13, "Other role", False)],
    )
    confirm = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_config_role_remove_confirm"
    )

    with (
        patch.object(
            RegistrationRoleRemovalSelect,
            "values",
            new_callable=PropertyMock,
            return_value=["11"],
        ),
        patch(
            "hmwz.modules.registration.commands.setup.config.fetch_member",
            new=AsyncMock(return_value=member),
        ),
        patch(
            "hmwz.modules.registration.commands.setup.config.configuration_message",
            new=AsyncMock(return_value=discord.Embed()),
        ),
    ):
        await confirm.callback(interaction)

    roles.remove.assert_awaited_once_with(
        guild=guild,
        roles=[11],
        channel_id=20,
    )
    registrations.remove.assert_awaited_once_with(
        guild=guild,
        roles=[11],
        channel_id=20,
    )
    member.remove_roles.assert_awaited_once_with(
        role,
        reason="Registration setup role removal",
    )
    module.compose_registration_overview.assert_awaited_once_with(
        force=True,
        channel_id=20,
    )


@pytest.mark.asyncio
async def test_registration_export_channel_can_be_disabled() -> None:
    registration_channel = SimpleNamespace(id=20, mention="<#20>")
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    guild.get_channel.return_value = registration_channel
    event_channel = SimpleNamespace(
        get=AsyncMock(return_value=None),
        remove=AsyncMock(return_value=True),
    )
    module = SimpleNamespace(
        guild=guild,
        module_key="registration",
        registration=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(title=None, description=None))
        ),
        roles=SimpleNamespace(get=AsyncMock(return_value=None)),
        registration_event_channel=event_channel,
    )
    interaction = SimpleNamespace(
        guild=guild,
        locale=discord.Locale.german,
        response=SimpleNamespace(edit_message=AsyncMock()),
    )
    view = RegistrationExportChannelView(module, 20, owner_id=1)
    disable_button = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_config_export_disable"
    )

    await disable_button.callback(interaction)

    event_channel.remove.assert_awaited_once_with(guild=guild)
    interaction.response.edit_message.assert_awaited_once()
    assert isinstance(
        interaction.response.edit_message.await_args.kwargs["view"],
        RegistrationConfigView,
    )


@pytest.mark.asyncio
async def test_registration_export_channel_can_be_configured() -> None:
    export_channel = Mock(spec=discord.TextChannel)
    export_channel.id = 30
    export_channel.mention = "<#30>"
    export_channel.permissions_for.return_value = SimpleNamespace(
        send_messages=True,
        attach_files=True,
    )
    selected_channel = Mock(spec=discord.app_commands.AppCommandChannel)
    selected_channel.id = export_channel.id
    registration_channel = SimpleNamespace(id=20, mention="<#20>")
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    guild.me = Mock(spec=discord.Member)
    guild.get_channel.side_effect = {20: registration_channel, 30: export_channel}.get
    event_channel = SimpleNamespace(
        get=AsyncMock(return_value=30),
        set=AsyncMock(return_value=True),
    )
    module = SimpleNamespace(
        guild=guild,
        module_key="registration",
        registration=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(title=None, description=None))
        ),
        roles=SimpleNamespace(get=AsyncMock(return_value=None)),
        registration_event_channel=event_channel,
    )
    interaction = SimpleNamespace(
        guild=guild,
        locale=discord.Locale.german,
        response=SimpleNamespace(edit_message=AsyncMock()),
    )
    view = RegistrationExportChannelView(module, 20, owner_id=1)
    select = next(
        item
        for item in view.children
        if isinstance(item, RegistrationExportChannelSelect)
    )

    with patch.object(
        RegistrationExportChannelSelect,
        "values",
        new_callable=PropertyMock,
        return_value=[selected_channel],
    ):
        await select.callback(interaction)

    export_channel.permissions_for.assert_called_once_with(guild.me)
    event_channel.set.assert_awaited_once_with(guild=guild, channel_id=30)
    interaction.response.edit_message.assert_awaited_once()
    assert isinstance(
        interaction.response.edit_message.await_args.kwargs["view"],
        RegistrationConfigView,
    )


def test_runtime_translation_emojis_are_kept_in_translation_files() -> None:
    context = SimpleNamespace(locale=discord.Locale.german)
    translation = RuntimeLocalizations["de"]["wz.setup.registration.remove.success"]

    assert translation.startswith(emojis.SUCCESS)
    assert t(context, "wz.setup.registration.remove.success") == translation
