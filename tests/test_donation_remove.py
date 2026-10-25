from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz import events
from hmwz.modules.donation.module import DonationModule


@pytest.mark.asyncio
async def test_remove_channel_deletes_setup_and_history_before_messages() -> None:
    operations: list[str] = []
    configuration = SimpleNamespace(
        overview_message_id=501,
        ranking_message_id=502,
    )
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=123,
            name="test guild",
            get_channel=Mock(),
        ),
    )

    async def on_message_delete(message_id: int) -> None:
        operations.append(f"message:{message_id}")
        payload = cast(
            events.RawMessageDeleteEvent,
            SimpleNamespace(
                guild_id=guild.id,
                channel_id=456,
                message_id=message_id,
            ),
        )
        assert await DonationModule.on_raw_message_delete(module, payload)

    def create_message(message_id: int) -> SimpleNamespace:
        async def delete() -> None:
            await on_message_delete(message_id)

        return SimpleNamespace(delete=AsyncMock(side_effect=delete))

    messages = {message_id: create_message(message_id) for message_id in (501, 502)}
    channel = Mock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(side_effect=messages.__getitem__)
    guild.get_channel.return_value = channel
    donations = SimpleNamespace(
        get_channel=AsyncMock(side_effect=(configuration, None, None)),
        delete_channel=AsyncMock(
            side_effect=lambda **_: operations.append("setup") or True
        ),
    )
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=guild,
            donations=donations,
            _views={},
            _registered_message_ids={501},
            _rush_view_states={},
        ),
    )

    assert await DonationModule._remove_channel(module, 456)

    assert operations == ["setup", "message:501", "message:502"]
    donations.delete_channel.assert_awaited_once_with(guild=guild, channel_id=456)
