from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.modules.registration.list_overview import RegistrationListOverview
from hmwz.modules.registration.repositories import (
    MemberRegistrationRepository,
    RegistrationSettingsRepository,
)
from hmwz.sqlite_db import Database


@pytest.mark.asyncio
async def test_lock_emoji_setting_defaults_on_and_can_be_disabled(
    tmp_path,
) -> None:
    database = Database(folder=str(tmp_path), filename="registration-lock-emojis.db")
    repository = RegistrationSettingsRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=10, name="test guild"))

    assert await database.execute(
        "CREATE TABLE Registration_Settings ("
        "Guild INTEGER NOT NULL, Channel INTEGER NOT NULL, Message INTEGER, "
        "Title TEXT, Description TEXT, PRIMARY KEY (Guild, Channel))"
    )
    assert await database.execute(
        "INSERT INTO Registration_Settings (Guild, Channel) VALUES (?, ?)",
        (guild.id, 20),
    )
    assert await repository.migrate_schema()

    settings = await repository.get(guild=guild, channel_id=20)
    assert settings is not None
    assert settings.show_lock_emojis

    assert await repository.upsert(guild=guild, channel_id=20, show_lock_emojis=False)
    settings = await repository.get(guild=guild, channel_id=20)
    assert settings is not None
    assert not settings.show_lock_emojis


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("show_lock_emojis", "expected_title"),
    [
        (True, "1. Anmeldungen: 2 ( 🔒: 1 | 🔓: 1 )"),
        (False, "1. Anmeldungen: 2"),
    ],
)
async def test_registration_list_shows_lock_emojis_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    show_lock_emojis: bool,
    expected_title: str,
) -> None:
    roles = {
        1: SimpleNamespace(name="Permanent"),
        2: SimpleNamespace(name="Temporary"),
    }
    guild = SimpleNamespace(
        id=10,
        get_role=roles.get,
    )
    overview = RegistrationListOverview(
        guild=cast(discord.Guild, guild),
        registrations=cast(MemberRegistrationRepository, SimpleNamespace()),
        overview_module=cast(discord.Client, SimpleNamespace()),
        overview_id="registration-20",
        module_key="registration",
        max_players=None,
    )

    async def fetch_member(_guild: discord.Guild, member_id: int) -> discord.Member:
        return cast(
            discord.Member,
            SimpleNamespace(display_name=f"Member {member_id}"),
        )

    monkeypatch.setattr(
        "hmwz.modules.registration.list_overview.fetch_member", fetch_member
    )
    registrations = SimpleNamespace(
        registrations=(
            SimpleNamespace(
                role=SimpleNamespace(role_id=1, permanent=True),
                member_id=11,
                account="",
            ),
            SimpleNamespace(
                role=SimpleNamespace(role_id=2, permanent=False),
                member_id=12,
                account="",
            ),
        )
    )

    embeds = await overview.create_embeds(
        registrations,
        get_color=discord.Color.blurple,
        get_client_avatar=lambda: None,
        show_lock_emojis=show_lock_emojis,
    )

    assert len(embeds) == 1
    assert embeds[0].title == expected_title
    if show_lock_emojis:
        assert "Permanent 🔒" in (embeds[0].description or "")
        assert "Temporary 🔓" in (embeds[0].description or "")
    else:
        assert "Permanent 🔒" not in (embeds[0].description or "")
        assert "Temporary 🔓" not in (embeds[0].description or "")
