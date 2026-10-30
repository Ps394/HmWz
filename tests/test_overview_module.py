from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.modules.overview.models import Overview, OverviewButton
from hmwz.modules.overview.repositories import OverviewRepository
from hmwz.sqlite_db import Database


@pytest.mark.asyncio
async def test_overview_repository_saves_and_loads_configuration(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="overview.db")
    repository = OverviewRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=123))
    overview = Overview(
        guild_id=guild.id,
        overview_id="registration",
        channel_id=456,
        message_id=789,
        title="Registrierung",
        description="Wähle deine Rolle.",
        buttons=(
            OverviewButton(
                button_id="register",
                label="Anmelden",
                style=discord.ButtonStyle.success,
                row=0,
            ),
        ),
    )

    assert await repository.ensure_schema()
    assert await repository.save(overview)
    assert await repository.get(guild=guild, overview_id="registration") == overview
    assert await repository.get_all(guild=guild) == (overview,)

    assert await repository.set_message(
        guild=guild, overview_id="registration", message_id=None
    )
    saved = await repository.get(guild=guild, overview_id="registration")
    assert saved is not None
    assert saved.message_id is None


@pytest.mark.asyncio
async def test_overview_repository_removes_guild_records(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="overview.db")
    repository = OverviewRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=321))
    overview = Overview(
        guild_id=guild.id,
        overview_id="welcome",
        channel_id=654,
        message_id=None,
        title="Willkommen",
        description="",
    )

    assert await repository.ensure_schema()
    assert await repository.save(overview)
    assert await repository.remove_guild(guild=guild)
    assert await repository.get_all(guild=guild) == ()
