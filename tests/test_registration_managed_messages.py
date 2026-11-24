from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.client import Client
from hmwz.modules.managed_messages import ManagedMessagesModule
from hmwz.modules.registration.managed_messages import (
    RegistrationManagedMessagesAdapter,
)
from hmwz.sqlite_db import Database


@pytest.fixture
async def adapter(tmp_path: Path) -> RegistrationManagedMessagesAdapter:
    guild = Mock(spec=discord.Guild)
    guild.id = 123
    guild.name = "Guild"
    client = Mock(spec=Client)
    client._database = Database(
        folder=str(tmp_path),
        filename="registration-managed-messages.db",
    )
    managed_messages = ManagedMessagesModule(cast(discord.Guild, guild), client)
    assert await managed_messages.sync()
    return RegistrationManagedMessagesAdapter(
        guild=cast(discord.Guild, guild),
        managed_messages=managed_messages,
    )


def test_registration_managed_ids_are_stable() -> None:
    assert RegistrationManagedMessagesAdapter.main_id(456) == "registration-456"
    assert RegistrationManagedMessagesAdapter.list_id(456, 3) == (
        "registration-456-list-3"
    )
    assert (
        RegistrationManagedMessagesAdapter.channel_id("registration-456-list-3") == 456
    )
    assert RegistrationManagedMessagesAdapter.channel_id("donation-456") is None


@pytest.mark.asyncio
async def test_adapter_publishes_main_message_and_removes_obsolete_pages(
    adapter: RegistrationManagedMessagesAdapter,
) -> None:
    guild = adapter.guild
    channel = Mock(spec=discord.TextChannel)
    channel.id = 456
    channel.send = AsyncMock()
    message = Mock(spec=discord.Message)
    message.id = 789
    message.content = ""
    message.embeds = []
    message.components = []
    message.edit = AsyncMock(return_value=message)
    channel.send.return_value = message
    adapter.guild.get_channel_or_thread = Mock(return_value=channel)

    assert await adapter.publish_pages(
        channel_id=456,
        embeds=[
            discord.Embed(title="Page 1"),
            discord.Embed(title="Page 2"),
        ],
    )
    assert (
        await adapter.managed_messages.messages.get(
            guild=guild,
            managed_id="registration-456-list-1",
        )
        is not None
    )
    assert (
        await adapter.managed_messages.messages.get(
            guild=guild,
            managed_id="registration-456-list-2",
        )
        is not None
    )
