from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.modules.registration.responses import send_temporary_followup


@pytest.mark.asyncio
async def test_temporary_followup_is_deleted_after_five_seconds() -> None:
    message = SimpleNamespace(delete=AsyncMock())
    followup = SimpleNamespace(send=AsyncMock(return_value=message))
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(followup=followup),
    )

    await send_temporary_followup(interaction, "Saved", ephemeral=True)

    followup.send.assert_awaited_once_with("Saved", ephemeral=True, wait=True)
    message.delete.assert_awaited_once_with(delay=5)
