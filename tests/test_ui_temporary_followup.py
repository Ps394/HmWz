import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import discord
import pytest

from hmwz.ui.messages import send_temporary_followup


@pytest.mark.asyncio
async def test_temporary_followup_schedules_deletion_after_five_seconds() -> None:
    message = SimpleNamespace()
    followup = SimpleNamespace(send=AsyncMock(return_value=message))
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(followup=followup),
    )
    scheduled_delete = AsyncMock()

    with patch(
        "hmwz.ui.messages._delete_after",
        new=scheduled_delete,
    ):
        await send_temporary_followup(interaction, "Saved", ephemeral=True)
        await asyncio.sleep(0)

    followup.send.assert_awaited_once_with("Saved", ephemeral=True, wait=True)
    scheduled_delete.assert_awaited_once_with(message, 5)


@pytest.mark.asyncio
async def test_temporary_followup_allows_custom_deletion_delay() -> None:
    message = SimpleNamespace()
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(followup=SimpleNamespace(send=AsyncMock(return_value=message))),
    )
    scheduled_delete = AsyncMock()

    with patch("hmwz.ui.messages._delete_after", new=scheduled_delete):
        await send_temporary_followup(interaction, "Saved", delay=10)
        await asyncio.sleep(0)

    scheduled_delete.assert_awaited_once_with(message, 10)
