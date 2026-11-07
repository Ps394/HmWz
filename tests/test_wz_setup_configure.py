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
from hmwz.modules.registration.commands.setup.config.draft import (
    RegistrationSetupDraft,
)
from hmwz.modules.registration.repositories import RegistrationSettingsRepository
from hmwz.sqlite_db import Database


def registration_draft(
    module: SimpleNamespace,
    *,
    roles: dict[int, bool] | None = None,
    export_channel_id: int | None = None,
) -> RegistrationSetupDraft:
    configured_roles = roles or {}
    return RegistrationSetupDraft(
        module=module,
        channel_id=20,
        owner_id=1,
        title="Title",
        original_title="Title",
        description="Description",
        original_description="Description",
        show_lock_emojis=True,
        original_show_lock_emojis=True,
        roles=configured_roles.copy(),
        original_roles=configured_roles.copy(),
        export_channel_id=export_channel_id,
        original_export_channel_id=export_channel_id,
    )


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
            get=AsyncMock(
                return_value=SimpleNamespace(
                    title="Title", description="", show_lock_emojis=True
                )
            )
        ),
        roles=SimpleNamespace(get=AsyncMock(return_value=None)),
        registration_event_channel=SimpleNamespace(get=AsyncMock(return_value=30)),
    )
    interaction = SimpleNamespace(
        guild=guild,
        locale=discord.Locale.german,
    )

    draft = registration_draft(module, roles={11: True}, export_channel_id=30)
    view = RegistrationConfigView(draft)
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
    assert any(
        item.custom_id == "wz_registration_config_lock_emojis" for item in view.children
    )
    assert any(
        field.name == "🔐 Schlossemojis in der Übersicht" for field in message.fields
    )
    apply_button = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_config_apply"
    )
    assert apply_button.emoji.name == "✅"
    assert any(
        item.custom_id == "wz_registration_config_cancel" for item in view.children
    )


@pytest.mark.asyncio
async def test_registration_setup_save_persists_the_draft_and_closes_the_menu() -> None:
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    guild.me = None
    role = Mock(spec=discord.Role)
    role.is_default.return_value = False
    role.managed = False
    guild.get_role.return_value = role
    settings = SimpleNamespace(
        title="Title", description="Description", show_lock_emojis=True
    )
    module = SimpleNamespace(
        guild=guild,
        module_key="registration",
        registration=SimpleNamespace(
            get=AsyncMock(return_value=settings),
            upsert=AsyncMock(return_value=True),
        ),
        roles=SimpleNamespace(
            get=AsyncMock(return_value=(SimpleNamespace(role=11, permanent=True),)),
            add=AsyncMock(return_value=True),
        ),
        registrations=SimpleNamespace(),
        registration_event_channel=SimpleNamespace(get=AsyncMock(return_value=None)),
        compose_registration_overview=AsyncMock(return_value=True),
    )
    interaction = SimpleNamespace(
        locale=discord.Locale.german,
        response=SimpleNamespace(defer=AsyncMock()),
        delete_original_response=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    view = RegistrationConfigView(registration_draft(module, roles={11: True}))
    apply_button = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_config_apply"
    )

    await apply_button.callback(interaction)

    interaction.response.defer.assert_awaited_once_with()
    interaction.delete_original_response.assert_awaited_once_with()
    module.registration.upsert.assert_awaited_once_with(
        guild=guild,
        channel_id=20,
        title="Title",
        description="Description",
        show_lock_emojis=True,
    )


@pytest.mark.asyncio
async def test_registration_config_toggle_only_changes_the_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = Mock(spec=discord.Guild)
    registration = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(show_lock_emojis=True)),
        upsert=AsyncMock(return_value=True),
    )
    module = SimpleNamespace(
        guild=guild,
        registration=registration,
        roles=SimpleNamespace(get=AsyncMock(return_value=(object(),))),
        compose_registration_overview=AsyncMock(return_value=True),
    )
    rendered = AsyncMock(return_value=discord.Embed())
    monkeypatch.setattr(
        "hmwz.modules.registration.commands.setup.config.configuration_message",
        rendered,
    )
    interaction = SimpleNamespace(
        locale=discord.Locale.german,
        response=SimpleNamespace(edit_message=AsyncMock()),
    )
    draft = registration_draft(module)
    view = RegistrationConfigView(draft)
    button = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_config_lock_emojis"
    )

    await button.callback(interaction)

    assert draft.show_lock_emojis is False
    registration.upsert.assert_not_awaited()
    module.compose_registration_overview.assert_not_awaited()
    interaction.response.edit_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_registration_role_removal_preserves_minimum_role_count() -> None:
    module = SimpleNamespace(
        guild=Mock(spec=discord.Guild),
        module_key="registration",
        roles=SimpleNamespace(remove=AsyncMock(return_value=True)),
        registrations=SimpleNamespace(remove=AsyncMock(return_value=True)),
    )
    draft = registration_draft(module, roles={11: True})
    interaction = SimpleNamespace(
        locale=discord.Locale.german,
        response=SimpleNamespace(
            send_message=AsyncMock(),
            defer=AsyncMock(),
        ),
    )
    view = RegistrationRoleRemovalView(
        draft,
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
    assert draft.roles == {11: True}
    module.roles.remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_registration_role_removal_stages_changes_until_save() -> None:
    guild = Mock(spec=discord.Guild)
    module = SimpleNamespace(
        guild=guild,
        module_key="registration",
        roles=SimpleNamespace(remove=AsyncMock()),
        registrations=SimpleNamespace(remove=AsyncMock()),
    )
    draft = registration_draft(module, roles={11: True, 13: False})
    interaction = SimpleNamespace(
        locale=discord.Locale.german,
        response=SimpleNamespace(defer=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    view = RegistrationRoleRemovalView(
        draft,
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
            "hmwz.modules.registration.commands.setup.config.configuration_message",
            new=AsyncMock(return_value=discord.Embed()),
        ),
    ):
        await confirm.callback(interaction)

    assert draft.roles == {13: False}
    module.roles.remove.assert_not_awaited()
    module.registrations.remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_registration_export_channel_disable_only_changes_the_draft() -> None:
    guild = Mock(spec=discord.Guild)
    event_channel = SimpleNamespace(
        get=AsyncMock(return_value=None),
        remove=AsyncMock(return_value=True),
    )
    module = SimpleNamespace(
        guild=guild,
        module_key="registration",
        registration_event_channel=event_channel,
    )
    draft = registration_draft(module, export_channel_id=30)
    interaction = SimpleNamespace(
        guild=guild,
        locale=discord.Locale.german,
        response=SimpleNamespace(edit_message=AsyncMock()),
    )
    view = RegistrationExportChannelView(draft)
    disable_button = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_config_export_disable"
    )

    with patch(
        "hmwz.modules.registration.commands.setup.config.configuration_message",
        new=AsyncMock(return_value=discord.Embed()),
    ):
        await disable_button.callback(interaction)

    assert draft.export_channel_id is None
    event_channel.remove.assert_not_awaited()
    interaction.response.edit_message.assert_awaited_once()
    assert isinstance(
        interaction.response.edit_message.await_args.kwargs["view"],
        RegistrationConfigView,
    )


@pytest.mark.asyncio
async def test_registration_export_channel_selection_only_changes_the_draft() -> None:
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
    event_channel = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())
    module = SimpleNamespace(
        guild=guild,
        module_key="registration",
        registration_event_channel=event_channel,
    )
    draft = registration_draft(module)
    interaction = SimpleNamespace(
        guild=guild,
        locale=discord.Locale.german,
        response=SimpleNamespace(edit_message=AsyncMock()),
    )
    view = RegistrationExportChannelView(draft)
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
        with patch(
            "hmwz.modules.registration.commands.setup.config.configuration_message",
            new=AsyncMock(return_value=discord.Embed()),
        ):
            await select.callback(interaction)

    export_channel.permissions_for.assert_called_once_with(guild.me)
    event_channel.set.assert_not_awaited()
    assert draft.export_channel_id == 30
    interaction.response.edit_message.assert_awaited_once()
    assert isinstance(
        interaction.response.edit_message.await_args.kwargs["view"],
        RegistrationConfigView,
    )


def test_runtime_translation_emojis_are_kept_in_translation_files() -> None:
    context = SimpleNamespace(locale=discord.Locale.german)
    translation = RuntimeLocalizations["de"]["registration.setup.remove.success"]

    assert translation.startswith(emojis.SUCCESS)
    assert t(context, "registration.setup.remove.success") == translation
