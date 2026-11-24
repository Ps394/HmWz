import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.client import Client
from hmwz.modules.managed_messages import (
    ManagedMessage,
    ManagedThread,
    ManagedMessagesModule,
)
from hmwz.sqlite_db import Database


@pytest.fixture
async def environment(tmp_path: Path) -> SimpleNamespace:
    database = Database(folder=str(tmp_path), filename="managed-messages.db")
    guild = Mock(spec=discord.Guild)
    guild.id = 123
    guild.name = "Test guild"

    message = Mock(spec=discord.Message)
    message.id = 789
    message.content = ""
    message.embeds = []
    message.components = []
    message.edit = AsyncMock(return_value=message)
    message.delete = AsyncMock()

    old_channel = Mock(spec=discord.TextChannel)
    old_channel.id = 456
    old_channel.fetch_message = AsyncMock(return_value=message)
    old_channel.send = AsyncMock(return_value=message)

    new_channel = Mock(spec=discord.TextChannel)
    new_channel.id = 654
    new_channel.send = AsyncMock(return_value=message)
    new_channel.fetch_message = AsyncMock(return_value=message)

    guild.get_channel_or_thread.side_effect = lambda channel_id: (
        old_channel if channel_id == 456 else new_channel if channel_id == 654 else None
    )

    client = Mock(spec=Client)
    client._database = database
    client.add_view = Mock()

    module = ManagedMessagesModule(cast(discord.Guild, guild), client)
    assert await module.sync()
    return SimpleNamespace(
        module=module,
        guild=guild,
        client=client,
        old_channel=old_channel,
        new_channel=new_channel,
        message=message,
    )


@pytest.mark.asyncio
async def test_managed_message_repository_saves_and_loads_payload(
    environment: SimpleNamespace,
) -> None:
    module = cast(ManagedMessagesModule, environment.module)
    guild = cast(discord.Guild, environment.guild)
    managed = ManagedMessage(
        guild_id=guild.id,
        managed_id="registration-main",
        channel_id=456,
        message_id=789,
        content="Status",
        embeds=({"title": "Overview"},),
    )

    assert await module.messages.save(managed)
    assert (
        await module.messages.get(guild=guild, managed_id="registration-main")
        == managed
    )
    assert await module.messages.get_all(guild=guild) == (managed,)

    assert await module.messages.set_message(
        guild=guild,
        managed_id="registration-main",
        message_id=None,
    )
    restored = await module.messages.get(guild=guild, managed_id="registration-main")
    assert restored is not None
    assert restored.message_id is None


@pytest.mark.asyncio
async def test_publish_creates_and_restores_persistent_message(
    environment: SimpleNamespace,
) -> None:
    module = cast(ManagedMessagesModule, environment.module)
    guild = cast(discord.Guild, environment.guild)
    embed = discord.Embed(title="Overview", description="Current status")

    assert await module.publish(
        managed_id="phase-main",
        channel_id=456,
        embeds=(embed,),
    )

    environment.old_channel.send.assert_awaited_once()
    saved = await module.messages.get(guild=guild, managed_id="phase-main")
    assert saved is not None
    assert saved.channel_id == 456
    assert saved.message_id == 789

    environment.message.embeds = [embed]
    assert await module.publish(
        managed_id="phase-main",
        channel_id=456,
        embeds=(embed,),
    )
    environment.message.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_moves_message_and_deletes_old_location(
    environment: SimpleNamespace,
) -> None:
    module = cast(ManagedMessagesModule, environment.module)
    guild = cast(discord.Guild, environment.guild)

    assert await module.publish(
        managed_id="ranking",
        channel_id=456,
        content="Ranking",
    )
    assert await module.publish(
        managed_id="ranking",
        channel_id=654,
        content="Ranking",
    )

    environment.message.delete.assert_awaited_once()
    environment.new_channel.send.assert_awaited_once()
    saved = await module.messages.get(guild=guild, managed_id="ranking")
    assert saved is not None
    assert saved.channel_id == 654


@pytest.mark.asyncio
async def test_deleted_managed_message_is_recreated(
    environment: SimpleNamespace,
) -> None:
    module = cast(ManagedMessagesModule, environment.module)
    embed = discord.Embed(title="Restored")

    assert await module.publish(
        managed_id="history",
        channel_id=456,
        embeds=(embed,),
    )
    environment.old_channel.fetch_message.side_effect = discord.NotFound(
        SimpleNamespace(status=404, reason="Not found"),
        "Missing message",
    )

    assert await module.restore_deleted({789})
    environment.old_channel.send.assert_awaited()


@pytest.mark.asyncio
async def test_parallel_publish_calls_are_serialized_per_guild(
    environment: SimpleNamespace,
) -> None:
    module = cast(ManagedMessagesModule, environment.module)
    active = 0
    maximum_active = 0

    async def send(**kwargs: object) -> Mock:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1
        message = Mock(spec=discord.Message)
        message.id = 900
        message.content = str(kwargs.get("content", ""))
        message.embeds = list(kwargs.get("embeds", []))
        message.components = []
        message.edit = AsyncMock(return_value=message)
        message.delete = AsyncMock()
        return message

    environment.old_channel.send.side_effect = send

    await asyncio.gather(
        module.publish(
            managed_id="parallel-a",
            channel_id=456,
            content="A",
        ),
        module.publish(
            managed_id="parallel-b",
            channel_id=456,
            content="B",
        ),
    )
    assert maximum_active == 1


@pytest.mark.asyncio
async def test_queue_refresh_batches_managed_ids(
    environment: SimpleNamespace,
) -> None:
    module = cast(ManagedMessagesModule, environment.module)
    refreshed: list[frozenset[str]] = []

    async def refresh(managed_ids: frozenset[str]) -> bool:
        refreshed.append(managed_ids)
        return True

    module.register_batch_refresh_handler(owner_id="qs", handler=refresh)

    first = module.queue_refresh("qs", "phase-1")
    second = module.queue_refresh("qs", "phase-2")

    assert first is second
    assert await first
    assert refreshed == [frozenset({"phase-1", "phase-2"})]


@pytest.mark.asyncio
async def test_channel_delete_uses_registered_owner_cleanup(
    environment: SimpleNamespace,
) -> None:
    module = cast(ManagedMessagesModule, environment.module)
    guild = cast(discord.Guild, environment.guild)
    channel = Mock(spec=discord.TextChannel)
    channel.id = 456
    channel.guild = guild
    operations: list[tuple[int, frozenset[str]]] = []

    async def cleanup(channel_id: int, managed_ids: frozenset[str]) -> bool:
        operations.append((channel_id, managed_ids))
        return True

    module.register_managed_owner(owner_id="qs", managed_id="phase-main")
    module.register_channel_delete_handler(owner_id="qs", handler=cleanup)
    assert await module.publish(
        managed_id="phase-main",
        channel_id=456,
        content="Phase",
    )

    assert await module.on_guild_channel_delete(channel)
    assert operations == [(456, frozenset({"phase-main"}))]


@pytest.mark.asyncio
async def test_thread_repository_supports_multiple_threads(
    environment: SimpleNamespace,
) -> None:
    module = cast(ManagedMessagesModule, environment.module)
    guild = cast(discord.Guild, environment.guild)

    first = ManagedThread(
        guild_id=guild.id,
        managed_id="qs-phase",
        thread_id=700,
        message_id=701,
    )
    second = ManagedThread(
        guild_id=guild.id,
        managed_id="qs-phase",
        thread_id=800,
        message_id=801,
    )

    assert await module.threads.save(first)
    assert await module.threads.save(second)
    assert await module.threads.get_all(guild=guild, managed_id="qs-phase") == (
        first,
        second,
    )

    assert await module.threads.remove(
        guild=guild,
        managed_id="qs-phase",
        thread_id=700,
    )
    assert await module.threads.get_all(guild=guild, managed_id="qs-phase") == (second,)
