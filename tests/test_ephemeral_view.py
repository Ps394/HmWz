from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.ui import EphemeralView
from hmwz.ui import ephemeral_view


@pytest.mark.asyncio
async def test_ephemeral_view_timeout_deletes_its_message(monkeypatch) -> None:
    delete_message = AsyncMock()
    monkeypatch.setattr(ephemeral_view, "delete_temporary_message", delete_message)
    message = cast(discord.Message, object())
    view = EphemeralView()
    view.message = message

    await view.on_timeout()

    delete_message.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_ephemeral_view_finish_defers_cleans_up_and_sends_followup(
    monkeypatch,
) -> None:
    defer = AsyncMock()
    delete_message = AsyncMock()
    delete_original = AsyncMock()
    send_followup = AsyncMock()
    monkeypatch.setattr(ephemeral_view, "defer_interaction", defer)
    monkeypatch.setattr(ephemeral_view, "delete_temporary_message", delete_message)
    monkeypatch.setattr(
        ephemeral_view, "safe_delete_original_response", delete_original
    )
    monkeypatch.setattr(ephemeral_view, "send_temporary_followup", send_followup)
    message = cast(discord.Message, object())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            response=SimpleNamespace(is_done=Mock(return_value=False)),
            message=message,
        ),
    )
    view = EphemeralView()

    await view.finish(interaction, "Complete", delay=7)

    assert view.is_finished()
    defer.assert_awaited_once_with(interaction, ephemeral=True, thinking=True)
    delete_message.assert_awaited_once_with(message)
    delete_original.assert_awaited_once_with(interaction)
    send_followup.assert_awaited_once_with(interaction, "Complete", delay=7)
