from collections.abc import Callable
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.utils.commands import moderator_command, user_command


@pytest.mark.parametrize(
    ("decorator", "permission"),
    [
        (moderator_command, "moderate_members"),
        (user_command, "view_channel"),
    ],
)
def test_command_decorator_checks_discord_permissions(
    decorator: Callable[..., object],
    permission: str,
) -> None:
    async def callback(interaction: discord.Interaction) -> None:
        del interaction

    decorated = decorator(callback)
    check = getattr(decorated, "__discord_app_commands_checks__")[0]

    interaction = cast(
        discord.Interaction,
        SimpleNamespace(permissions=discord.Permissions(**{permission: True})),
    )
    assert check(interaction) is True

    interaction = cast(
        discord.Interaction,
        SimpleNamespace(permissions=discord.Permissions.none()),
    )
    with pytest.raises(discord.app_commands.MissingPermissions):
        check(interaction)
