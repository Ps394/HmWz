from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import discord
import pytest

from hmwz.client.commands.set_timezone import SetTimezone, timezone_autocomplete
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
async def test_timezone_autocomplete_suggests_matching_iana_zones() -> None:
    interaction = cast(discord.Interaction, SimpleNamespace())

    assert SetTimezone._params["timezone"].autocomplete is timezone_autocomplete
    choices = await timezone_autocomplete(interaction, "europe/ber")

    assert [choice.value for choice in choices] == ["Europe/Berlin"]
    offset = datetime.now(UTC).astimezone(ZoneInfo("Europe/Berlin")).strftime("%z")
    assert choices[0].name == f"Europe/Berlin (UTC{offset[:3]}:{offset[3:]})"

    offset_choices = await timezone_autocomplete(
        interaction, f"UTC{offset[:3]}:{offset[3:]}"
    )
    assert any(choice.value == "Europe/Berlin" for choice in offset_choices)


@pytest.mark.asyncio
async def test_timezone_autocomplete_limits_choices_to_discord_maximum() -> None:
    interaction = cast(discord.Interaction, SimpleNamespace())

    choices = await timezone_autocomplete(interaction, "")

    assert len(choices) == 25
    assert choices[0].value == DEFAULT_GUILD_TIMEZONE


@pytest.mark.asyncio
async def test_timezone_autocomplete_omits_iana_aliases() -> None:
    interaction = cast(discord.Interaction, SimpleNamespace())

    us_aliases = await timezone_autocomplete(interaction, "US/")
    utc_choices = await timezone_autocomplete(interaction, "UTC")

    assert us_aliases == []
    assert len(utc_choices) <= 25
    assert all(" (UTC" in choice.name for choice in utc_choices)
    assert any(choice.value == "UTC" for choice in utc_choices)
    assert len({choice.value for choice in utc_choices}) == len(utc_choices)


@pytest.mark.asyncio
async def test_timezone_autocomplete_has_one_common_zone_per_hour_offset() -> None:
    interaction = cast(discord.Interaction, SimpleNamespace())
    negative = await timezone_autocomplete(interaction, "UTC-")
    positive = await timezone_autocomplete(interaction, "UTC+")
    choices = negative + positive
    actual_offsets: list[int] = []
    for choice in choices:
        offset = datetime.now(UTC).astimezone(ZoneInfo(choice.value)).utcoffset()
        assert offset is not None
        offset_minutes = int(offset.total_seconds() // 60)
        if offset_minutes % 60 == 0:
            actual_offsets.append(offset_minutes // 60)

    assert len(negative) <= 25
    assert len(positive) <= 25
    assert set(range(-12, 15)) == set(actual_offsets)
    assert len(actual_offsets) == 27


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
