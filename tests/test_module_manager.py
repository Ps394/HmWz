from types import SimpleNamespace
from typing import ClassVar, cast

import discord
import pytest

from hmwz.modules import manager as manager_module
from hmwz.modules.manager import Manager


class RecordingModule:
    created_guild_ids: ClassVar[list[int]] = []

    def __init__(self, guild: discord.Guild) -> None:
        self.guild = guild
        self.deleted_guild_ids: list[int] = []

    @classmethod
    async def create(cls, guild: discord.Guild, client: object) -> "RecordingModule":
        cls.created_guild_ids.append(guild.id)
        return cls(guild)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        assert channel.guild is not None
        self.deleted_guild_ids.append(channel.guild.id)
        return True


@pytest.mark.asyncio
async def test_modules_are_cached_and_events_are_scoped_to_the_guild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    RecordingModule.created_guild_ids.clear()
    monkeypatch.setattr(manager_module, "REGISTRY", [RecordingModule])
    manager = Manager(client=object())
    first_guild = cast(discord.Guild, SimpleNamespace(id=123, name="first guild"))
    second_guild = cast(discord.Guild, SimpleNamespace(id=456, name="second guild"))

    first_modules = await manager.get_modules(first_guild)
    assert await manager.get_modules(first_guild) is first_modules
    second_modules = await manager.get_modules(second_guild)

    assert RecordingModule.created_guild_ids == [123, 456]
    assert first_modules[0] is not second_modules[0]

    channel = cast(discord.abc.GuildChannel, SimpleNamespace(guild=first_guild))
    assert await manager.on_guild_channel_delete(channel)
    assert first_modules[0].deleted_guild_ids == [123]
    assert second_modules[0].deleted_guild_ids == []
