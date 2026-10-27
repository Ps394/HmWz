from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

reset = import_module("hmwz.modules.registration.commands.reset")


@pytest.mark.asyncio
async def test_remove_registration_roles_only_removes_roles_for_known_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role = Mock(spec=discord.Role)
    role.id = 20
    member = Mock(spec=discord.Member)
    member.id = 10
    guild = Mock(spec=discord.Guild)
    guild.get_role.side_effect = {20: role, 30: None}.get

    async def fetch_member(
        _guild: discord.Guild, member_id: int
    ) -> discord.Member | None:
        assert _guild is guild
        return {10: member, 11: None}.get(member_id)

    fetch_member_mock = AsyncMock(side_effect=fetch_member)
    sleep = AsyncMock()
    monkeypatch.setattr(reset, "fetch_member", fetch_member_mock)
    monkeypatch.setattr(reset.asyncio, "sleep", sleep)

    await reset._remove_registration_roles(
        guild,
        {
            (10, 20),
            (10, 30),
            (11, 20),
        },
    )

    member.remove_roles.assert_awaited_once_with(role, reason="WZ Registration Reset")
    assert fetch_member_mock.await_count == 3
    sleep.assert_awaited_once_with(0.05)


@pytest.mark.asyncio
async def test_purge_configured_channels_processes_unique_ids_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channels = {
        10: Mock(spec=discord.TextChannel),
        20: Mock(spec=discord.TextChannel),
    }
    for channel_id, channel in channels.items():
        channel.id = channel_id
        channel.purge = AsyncMock(return_value=[])
    guild = Mock(spec=discord.Guild)

    async def fetch_channel(
        _guild: discord.Guild, channel_id: int
    ) -> discord.TextChannel | None:
        assert _guild is guild
        return channels.get(channel_id)

    fetch_channel_mock = AsyncMock(side_effect=fetch_channel)
    monkeypatch.setattr(reset, "fetch_channel", fetch_channel_mock)

    await reset._purge_configured_channels(guild, {20, 10})

    assert [call.args[1] for call in fetch_channel_mock.await_args_list] == [10, 20]
    for channel in channels.values():
        channel.purge.assert_awaited_once()
        arguments = channel.purge.await_args.kwargs
        assert arguments["limit"] == 500
        assert arguments["reason"] == "WZ Registration Reset"
        assert arguments["check"](
            SimpleNamespace(pinned=False, author=SimpleNamespace(bot=False))
        )
        assert not arguments["check"](
            SimpleNamespace(pinned=True, author=SimpleNamespace(bot=False))
        )
        assert not arguments["check"](
            SimpleNamespace(pinned=False, author=SimpleNamespace(bot=True))
        )
