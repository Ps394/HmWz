from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from hmwz.modules.hs.qs.commands import QsGroup
from hmwz.modules.hs.qs.commands.reset_channels import (
    QsChannelsResetConfirmation,
    reset_channels,
)
from hmwz.modules.hs.qs.commands.reset_roles import reset_roles
from hmwz.modules.hs.qs.commands.setup.menu import QsSetupMenu, setup as qs_setup
from hmwz.modules.hs.qs.repositories import QSPurgeChannelRepository
from hmwz.modules.hs.wz.commands.setup.menu import setup as wz_setup
from hmwz.sqlite_db import Database


def test_qs_commands_use_requested_reset_names() -> None:
    group = QsGroup()

    assert {command.name for command in group.commands} == {
        "setup",
        "reset-roles",
        "reset-channels",
    }
    assert reset_roles.name == "reset-roles"
    assert reset_channels.name == "reset-channels"
    assert not reset_channels.parameters


@pytest.mark.asyncio
async def test_qs_setup_shows_configuration_without_overview_button() -> None:
    context = cast(
        discord.Interaction,
        SimpleNamespace(locale=discord.Locale.german),
    )

    view = QsSetupMenu(owner_id=1, context=context)
    button_ids = {
        item.custom_id for item in view.children if isinstance(item, discord.ui.Button)
    }

    assert button_ids == {
        "qs_setup_add_channel",
        "qs_setup_remove_channel",
        "qs_setup_add_role",
        "qs_setup_remove_role",
    }


@pytest.mark.asyncio
async def test_qs_setup_displays_configuration_in_initial_message() -> None:
    guild = Mock(spec=discord.Guild)
    guild.get_role.return_value = None
    module = SimpleNamespace(
        registration=SimpleNamespace(
            get_all=AsyncMock(return_value=[SimpleNamespace(channel=20)])
        ),
        roles=SimpleNamespace(get=AsyncMock(return_value=None)),
        purge_channels=SimpleNamespace(get=AsyncMock(return_value=(30,))),
    )
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            guild=guild,
            user=SimpleNamespace(id=1),
            locale=discord.Locale.german,
            client=SimpleNamespace(module_manager=manager),
            response=SimpleNamespace(send_message=AsyncMock()),
            original_response=AsyncMock(return_value=SimpleNamespace()),
        ),
    )

    await qs_setup.callback(interaction)

    content = interaction.response.send_message.await_args.args[0]
    assert "<#20>" in content
    assert "<#30>" in content


@pytest.mark.asyncio
async def test_wz_setup_displays_configuration_in_initial_message() -> None:
    guild = Mock(spec=discord.Guild)
    guild.get_role.return_value = None
    module = SimpleNamespace(
        registration=SimpleNamespace(
            get_all=AsyncMock(return_value=[SimpleNamespace(channel=20)])
        ),
        roles=SimpleNamespace(get=AsyncMock(return_value=None)),
        purge_channels=SimpleNamespace(
            get=AsyncMock(return_value=[SimpleNamespace(channel_id=30)])
        ),
    )
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            guild=guild,
            user=SimpleNamespace(id=1),
            locale=discord.Locale.german,
            client=SimpleNamespace(module_manager=manager),
            response=SimpleNamespace(send_message=AsyncMock()),
            original_response=AsyncMock(return_value=SimpleNamespace()),
        ),
    )

    await wz_setup.callback(interaction)

    content = interaction.response.send_message.await_args.args[0]
    assert "<#20>" in content
    assert "<#30>" in content


@pytest.mark.asyncio
async def test_qs_purge_channel_repository_persists_channels(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="qs-purge-channels.db")
    assert await database.execute(
        "CREATE TABLE Servers (Guild INTEGER PRIMARY KEY) WITHOUT ROWID"
    )
    assert await database.execute("INSERT INTO Servers (Guild) VALUES (?)", (10,))
    repository = QSPurgeChannelRepository(database)
    assert await database.execute(repository.table)
    guild = cast(
        discord.Guild,
        SimpleNamespace(id=10, name="test guild"),
    )

    assert await repository.get(guild=guild) is None
    assert await repository.add(guild=guild, channel_id=20)
    assert await repository.add(guild=guild, channel_id=21)
    assert await repository.get(guild=guild) == (20, 21)
    assert await repository.remove(guild=guild, channel_id=20)
    assert await repository.get(guild=guild) == (21,)
    assert await repository.remove(guild=guild)
    assert await repository.get(guild=guild) is None


@pytest.mark.asyncio
async def test_qs_channel_reset_cancel_deletes_confirmation() -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=10))
    message = SimpleNamespace(delete=AsyncMock())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            user=SimpleNamespace(id=1),
            locale=discord.Locale.german,
            response=SimpleNamespace(
                defer=AsyncMock(),
                is_done=lambda: False,
            ),
            message=message,
            delete_original_response=AsyncMock(),
            followup=SimpleNamespace(send=AsyncMock()),
        ),
    )
    view = QsChannelsResetConfirmation(
        guild=guild,
        owner_id=1,
        channel_ids=[20],
        context=interaction,
    )
    cancel = next(
        item for item in view.children if item.custom_id == "qs_reset_channels_cancel"
    )

    with patch(
        "hmwz.ui.ephemeral_view.send_temporary_followup",
        new_callable=AsyncMock,
    ):
        await cancel.callback(interaction)

    message.delete.assert_awaited_once()
