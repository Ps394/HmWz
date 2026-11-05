from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.client.commands.set_timezone import SetTimezone
from hmwz.client.repositories.server import ServerRepository
from hmwz.sqlite_db import Database
from hmwz.utils.timezones import DEFAULT_GUILD_TIMEZONE, validate_iana_timezone


@pytest.mark.asyncio
async def test_existing_servers_get_default_timezone_and_can_be_updated(
    tmp_path,
) -> None:
    database = Database(folder=str(tmp_path), filename="timezone.db")
    assert await database.execute(
        "CREATE TABLE Servers (Guild INTEGER PRIMARY KEY, Name TEXT)"
    )
    assert await database.execute(
        "INSERT INTO Servers (Guild, Name) VALUES (?, ?)", (123, "Guild")
    )
    repository = ServerRepository(database)

    assert await repository.ensure_schema()
    assert await repository.get_timezone(123) == DEFAULT_GUILD_TIMEZONE

    guild = cast(discord.Guild, SimpleNamespace(id=123, name="Guild"))
    assert await repository.set_timezone(guild, "America/New_York")
    assert await repository.get_timezone(123) == "America/New_York"


def test_validate_iana_timezone_trims_names_and_rejects_offsets() -> None:
    assert validate_iana_timezone(" Europe/Berlin ") == "Europe/Berlin"
    with pytest.raises(ValueError):
        validate_iana_timezone("UTC+1")
    with pytest.raises(ValueError):
        validate_iana_timezone("Not/A_Timezone")


@pytest.mark.asyncio
async def test_set_timezone_command_persists_only_valid_iana_names() -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="Guild"))
    client = SimpleNamespace(
        set_guild_timezone=AsyncMock(return_value=True),
        on_guild_timezone_update=AsyncMock(return_value=True),
    )
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            guild=guild,
            client=client,
            response=SimpleNamespace(send_message=AsyncMock()),
        ),
    )

    await SetTimezone.callback(interaction, "Europe/Paris")

    client.set_guild_timezone.assert_awaited_once_with(guild, "Europe/Paris")
    client.on_guild_timezone_update.assert_awaited_once_with(guild)
    interaction.response.send_message.assert_awaited_once()

    client.set_guild_timezone.reset_mock()
    client.on_guild_timezone_update.reset_mock()
    interaction.response.send_message.reset_mock()
    await SetTimezone.callback(interaction, "UTC+1")
    client.set_guild_timezone.assert_not_awaited()
    client.on_guild_timezone_update.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once()
    assert len(SetTimezone.checks) >= 1
