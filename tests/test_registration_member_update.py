from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.modules.hs.qs.module import QsRegistrationModule
from hmwz.sqlite_db import Database


def _member(
    guild: discord.Guild, member_id: int, roles: list[object]
) -> discord.Member:
    return cast(
        discord.Member,
        SimpleNamespace(
            guild=guild,
            id=member_id,
            name="member",
            display_name="Member",
            roles=roles,
        ),
    )


def _role(role_id: int) -> discord.Role:
    return cast(discord.Role, SimpleNamespace(id=role_id, name="Player"))


@pytest.mark.asyncio
async def test_added_registration_role_is_recorded_and_published(
    tmp_path: Path,
) -> None:
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=10,
            name="test guild",
            get_role=lambda role_id: _role(role_id),
        ),
    )
    module = QsRegistrationModule(
        guild,
        cast(
            discord.Client,
            SimpleNamespace(
                _database=Database(folder=str(tmp_path), filename="added-role.db")
            ),
        ),
    )
    module.migrate_schema = AsyncMock(return_value=True)
    module.roles.get = AsyncMock(
        return_value=(SimpleNamespace(role=30, channel_id=40),)
    )
    module.registrations.get = AsyncMock(side_effect=[(), None])
    module.registrations.add = AsyncMock(return_value=True)
    module.export_registration_snapshot = AsyncMock(return_value=True)
    module.compose_registration_overview = AsyncMock(return_value=True)
    before = _member(guild, 20, [])
    after = _member(guild, 20, [_role(30)])

    assert await module.on_member_update(before, after)

    module.registrations.add.assert_awaited_once_with(
        guild=guild,
        member=20,
        role=30,
        account="",
        channel_id=40,
        member_username="member",
        member_display_name="Member",
        role_name="Player",
    )
    module.export_registration_snapshot.assert_awaited_once_with(40, "sync")
    module.compose_registration_overview.assert_awaited_once_with(
        force=True, channel_id=40
    )


@pytest.mark.asyncio
async def test_removed_registration_role_is_unlinked_and_published(
    tmp_path: Path,
) -> None:
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=10, name="test guild", get_role=lambda role_id: _role(role_id)
        ),
    )
    module = QsRegistrationModule(
        guild,
        cast(
            discord.Client,
            SimpleNamespace(
                _database=Database(folder=str(tmp_path), filename="removed-role.db")
            ),
        ),
    )
    module.migrate_schema = AsyncMock(return_value=True)
    module.roles.get = AsyncMock(
        return_value=(SimpleNamespace(role=30, channel_id=40),)
    )
    module.registrations.get = AsyncMock(return_value=(SimpleNamespace(role=30),))
    module.registrations.remove_member_role = AsyncMock(return_value=True)
    module.registrations.add = AsyncMock(return_value=True)
    module.export_registration_snapshot = AsyncMock(return_value=True)
    module.compose_registration_overview = AsyncMock(return_value=True)
    before = _member(guild, 20, [_role(30)])
    after = _member(guild, 20, [])

    assert await module.on_member_update(before, after)

    module.registrations.remove_member_role.assert_awaited_once_with(
        guild=guild,
        member=20,
        role=30,
        channel_id=40,
    )
    module.registrations.add.assert_not_awaited()
    module.export_registration_snapshot.assert_awaited_once_with(40, "sync")
    module.compose_registration_overview.assert_awaited_once_with(
        force=True, channel_id=40
    )
