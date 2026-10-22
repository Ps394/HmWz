from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.modules.registration.commands.setup.remove import (
    RegistrationRemoveConfirmation,
    remove,
)


@pytest.mark.asyncio
async def test_remove_command_requires_confirmation() -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=10))
    registration = SimpleNamespace(get=AsyncMock(return_value=object()))
    module = SimpleNamespace(registration=registration)
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    response = SimpleNamespace(send_message=AsyncMock())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            guild=guild,
            channel_id=20,
            user=SimpleNamespace(id=30),
            client=SimpleNamespace(module_manager=manager),
            locale=discord.Locale.german,
            response=response,
        ),
    )

    await remove.callback(interaction)

    response.send_message.assert_awaited_once()
    arguments = response.send_message.await_args
    assert arguments.kwargs["ephemeral"] is True
    assert isinstance(arguments.kwargs["view"], RegistrationRemoveConfirmation)
    assert "Teilnahmen" in arguments.args[0]
    registration.get.assert_awaited_once_with(guild=guild, channel_id=20)
