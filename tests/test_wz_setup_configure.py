from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz import emojis
from hmwz.i18n import RuntimeLocalizations, t
from hmwz.modules.registration.commands.setup.configure import configure
from hmwz.modules.registration.repositories import RegistrationSettingsRepository
from hmwz.sqlite_db import Database


@pytest.mark.asyncio
async def test_configure_rejects_an_existing_registration() -> None:
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    registration = SimpleNamespace(get=AsyncMock(return_value=object()))
    module = SimpleNamespace(registration=registration)
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    response = SimpleNamespace(defer=AsyncMock())
    followup = SimpleNamespace(send=AsyncMock())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            guild=guild,
            channel_id=20,
            client=SimpleNamespace(module_manager=manager),
            response=response,
            followup=followup,
        ),
    )

    await configure.callback(interaction, Mock(spec=discord.Role))

    registration.get.assert_awaited_once_with(guild=guild, channel_id=20)
    followup.send.assert_awaited_once()
    message = followup.send.await_args.args[0]
    assert message.startswith(emojis.WARNING)
    assert "besteht bereits" in message
    assert followup.send.await_args.kwargs["ephemeral"] is True


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
    assert await database.execute(
        "CREATE TABLE DiscordChannels (Guild INTEGER, Channel INTEGER, Name TEXT)"
    )
    assert await database.execute(repository.table)
    assert await database.execute("INSERT INTO Servers (Guild) VALUES (?)", (guild.id,))

    assert await repository.create(guild=guild, channel_id=20)
    assert not await repository.create(guild=guild, channel_id=20)
    assert await repository.create(guild=guild, channel_id=21)


def test_configure_command_uses_invocation_channel_and_role_parameters() -> None:
    parameters = {parameter.name: parameter for parameter in configure.parameters}

    assert set(parameters) == {"role", "permanent"}
    assert parameters["role"].required is True
    assert parameters["permanent"].required is False
    assert parameters["permanent"].default is False


def test_runtime_translation_emojis_are_kept_in_translation_files() -> None:
    context = SimpleNamespace(locale=discord.Locale.german)
    translation = RuntimeLocalizations["de"]["wz.setup.registration.remove.success"]

    assert translation.startswith(emojis.SUCCESS)
    assert t(context, "wz.setup.registration.remove.success") == translation
