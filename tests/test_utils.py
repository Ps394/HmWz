from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.utils.fetchers import fetch_message
from hmwz.utils.interactions import log_guild, log_interaction


def test_log_interaction_formats_context() -> None:
    interaction = SimpleNamespace(
        user=SimpleNamespace(name="User", display_name="Display", id=1),
        guild=SimpleNamespace(name="Guild", id=2),
        channel=SimpleNamespace(name="channel", id=3),
    )

    assert log_interaction(cast(discord.Interaction, interaction)) == (
        "Guild (2) - channel (3) - User / Display (1)"
    )
    assert log_guild(cast(discord.Guild, interaction.guild)) == "Guild (2) =>"


@pytest.mark.asyncio
async def test_fetch_message_returns_none_for_missing_message() -> None:
    error = discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"),
        "message not found",
    )
    channel = SimpleNamespace(
        name="channel",
        id=3,
        guild=SimpleNamespace(name="Guild", id=2),
        fetch_message=AsyncMock(side_effect=error),
    )

    result = await fetch_message(cast(discord.TextChannel, channel), 4, attempts=1)

    assert result is None
    channel.fetch_message.assert_awaited_once_with(4)
