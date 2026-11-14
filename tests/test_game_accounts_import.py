import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.configuration import MODERATOR_ROLES
from hmwz.modules.hs.account.commands import import_accounts
from hmwz.modules.hs.account.importer import AccountEntry, import_entries, parse_entries
from hmwz.modules.hs.account.repositories import MemberGameAccountRepository
from hmwz.sqlite_db import Database


@pytest.mark.asyncio
async def test_import_resolves_members_and_preserves_existing_accounts(tmp_path: Path):
    database = Database(folder=str(tmp_path), filename="test.db")
    repository = MemberGameAccountRepository(database)
    assert await database.execute(repository.table)

    class Guild:
        id = 123
        name = "test"

        async def fetch_members(self, *, limit):
            for member in (
                SimpleNamespace(id=1, name="User", discriminator="0"),
                SimpleNamespace(id=2, name="duplicate", discriminator="0"),
                SimpleNamespace(id=3, name="duplicate", discriminator="0"),
            ):
                yield member

    guild = cast(discord.Guild, Guild())
    assert await repository.add(guild=guild, member=99, account="Owned")
    entries: list[AccountEntry] = [
        {"discord_username": "user", "players": ["First", "Second", "Owned"]},
        {"discord_username": "missing", "players": ["Missing"]},
        {"discord_username": "duplicate", "players": ["Ambiguous"]},
    ]
    result = await import_entries(guild, repository, entries)
    assert (result.imported, result.existing, result.skipped) == (2, 0, 3)
    result = await import_entries(guild, repository, entries)
    assert (result.imported, result.existing, result.skipped) == (0, 2, 3)
    records = await repository.get(guild=guild, member=1)
    assert records is not None
    assert [record.account for record in records] == ["First", "Second"]
    owned = await repository.get(guild=guild, account="Owned")
    assert owned is not None
    assert owned[0].member == 99
    assert await repository.get(guild=guild, account="Missing") is None
    assert await repository.get(guild=guild, account="Ambiguous") is None


def test_invalid_json_is_rejected_before_import():
    with pytest.raises(ValueError):
        parse_entries(json.dumps([{"discord_username": "user", "players": ["-"]}]))


def test_import_command_requires_a_moderator_role():
    check = next(
        check
        for check in import_accounts.account_import.checks
        if "has_any_role" in check.__qualname__
    )
    member = SimpleNamespace(roles=[])
    interaction = cast(discord.Interaction, SimpleNamespace(user=member))
    with pytest.raises(discord.app_commands.MissingAnyRole):
        check(interaction)
    member.roles = [SimpleNamespace(name=MODERATOR_ROLES[0])]
    assert check(interaction)
    assert import_accounts.account_import.guild_only


@pytest.mark.asyncio
async def test_import_command_processes_attachment_privately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    database = Database(folder=str(tmp_path), filename="command.db")
    repository = MemberGameAccountRepository(database)
    assert await database.execute(repository.table)

    class Guild:
        id = 456
        name = "test"

        async def fetch_members(self, *, limit):
            yield SimpleNamespace(id=12, name="User", discriminator="0")

    guild = cast(discord.Guild, Guild())
    context = AsyncMock(
        return_value=(guild, None, SimpleNamespace(game_accounts=repository))
    )
    followup = AsyncMock()
    monkeypatch.setattr(import_accounts, "get_member_context", context)
    monkeypatch.setattr(import_accounts, "send_followup", followup)
    monkeypatch.setattr(import_accounts, "t", lambda _i, key, **values: (key, values))
    interaction = SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()))
    attachment = SimpleNamespace(
        filename="accounts.json",
        size=100,
        read=AsyncMock(
            return_value=json.dumps(
                [
                    {"discord_username": "user", "players": ["Alpha", "Beta"]},
                    {"discord_username": "missing", "players": ["Unknown"]},
                ]
            ).encode()
        ),
    )

    callback = cast(
        Callable[[discord.Interaction, discord.Attachment], Awaitable[None]],
        import_accounts.account_import.callback,
    )
    await callback(
        cast(discord.Interaction, interaction), cast(discord.Attachment, attachment)
    )

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    records = await repository.get(guild=guild, member=12)
    assert records is not None
    assert [record.account for record in records] == ["Alpha", "Beta"]
    assert followup.await_args_list[0].args[1] == (
        "wz.account_import.result",
        {"imported": 2, "existing": 0, "skipped": 1},
    )
    report = followup.await_args_list[1].kwargs["file"]
    assert b"missing" in report.fp.read()
    report.close()


@pytest.mark.asyncio
async def test_import_command_rejects_invalid_json_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
):
    context = AsyncMock()
    followup = AsyncMock()
    monkeypatch.setattr(import_accounts, "get_member_context", context)
    monkeypatch.setattr(import_accounts, "send_followup", followup)
    monkeypatch.setattr(import_accounts, "t", lambda _i, key: key)
    interaction = SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()))
    attachment = SimpleNamespace(
        filename="accounts.json",
        size=100,
        read=AsyncMock(
            return_value=b'[{"discord_username": "user", "players": ["-"]}]'
        ),
    )
    callback = cast(
        Callable[[discord.Interaction, discord.Attachment], Awaitable[None]],
        import_accounts.account_import.callback,
    )
    await callback(
        cast(discord.Interaction, interaction), cast(discord.Attachment, attachment)
    )
    context.assert_not_awaited()
    followup.assert_awaited_once_with(interaction, "wz.account_import.invalid")
