from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.interactions import (
    respond,
    safe_delete_message,
    send_temporary_response,
)


@pytest.mark.asyncio
async def test_respond_uses_initial_response_and_retrieves_message() -> None:
    message = object()
    response = SimpleNamespace(is_done=lambda: False, send_message=AsyncMock())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            response=response,
            original_response=AsyncMock(return_value=message),
            followup=SimpleNamespace(send=AsyncMock()),
        ),
    )

    assert await respond(interaction, "Saved", ephemeral=True) is message

    response.send_message.assert_awaited_once_with("Saved", ephemeral=True)
    interaction.followup.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_respond_uses_followup_after_defer() -> None:
    message = object()
    followup = SimpleNamespace(send=AsyncMock(return_value=message))
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            response=SimpleNamespace(is_done=lambda: True),
            followup=followup,
        ),
    )

    assert await respond(interaction, "Saved", ephemeral=True) is message
    followup.send.assert_awaited_once_with("Saved", ephemeral=True, wait=True)


@pytest.mark.asyncio
async def test_temporary_response_uses_followup_and_deletes_after_delay() -> None:
    message = SimpleNamespace(delete=AsyncMock())
    followup = SimpleNamespace(send=AsyncMock(return_value=message))
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            response=SimpleNamespace(is_done=lambda: True),
            followup=followup,
        ),
    )

    await send_temporary_response(interaction, "Try again", delay=3)

    followup.send.assert_awaited_once_with("Try again", ephemeral=True, wait=True)
    message.delete.assert_awaited_once_with(delay=3)


@pytest.mark.asyncio
async def test_safe_delete_ignores_a_deleted_message() -> None:
    response = SimpleNamespace(status=404, reason="Not Found", headers={})
    message = SimpleNamespace(
        delete=AsyncMock(side_effect=discord.NotFound(response, "gone"))
    )

    assert await safe_delete_message(cast(discord.Message, message))
    message.delete.assert_awaited_once_with()
