import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import discord
import pytest

from hmwz.ui.messages import (
    edit_interaction_response,
    edit_original_response,
    send_followup,
    send_interaction_response,
    send_interaction_message,
    send_temporary_followup,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("acknowledged", [False, True])
async def test_interaction_message_uses_current_response_state(
    acknowledged: bool,
) -> None:
    message = SimpleNamespace()
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            response=SimpleNamespace(
                is_done=lambda: acknowledged, send_message=AsyncMock()
            ),
            original_response=AsyncMock(return_value=message),
            followup=SimpleNamespace(send=AsyncMock(return_value=message)),
        ),
    )
    assert await send_interaction_message(interaction, "Result") is message
    if acknowledged:
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_awaited_once_with(
            "Result", ephemeral=True, wait=True
        )
    else:
        interaction.response.send_message.assert_awaited_once_with(
            "Result", ephemeral=True
        )
        interaction.followup.send.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_dialog_helpers_render_content_and_preserve_views_and_embeds() -> None:
    message = SimpleNamespace()
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            response=SimpleNamespace(
                send_message=AsyncMock(), edit_message=AsyncMock()
            ),
            original_response=AsyncMock(return_value=message),
            edit_original_response=AsyncMock(return_value=message),
            followup=SimpleNamespace(send=AsyncMock(return_value=message)),
        ),
    )
    view = SimpleNamespace()
    embed = discord.Embed(title="Preview")
    with patch("hmwz.ui.messages.emojis.render", return_value="Rendered") as render:
        assert (
            await send_interaction_response(interaction, "Content", view=view)
            is message
        )
        assert await send_followup(interaction, "Content", view=view) is message
        await edit_interaction_response(interaction, content="Content", view=view)
        assert (
            await edit_original_response(interaction, content="Content", view=view)
            is message
        )
        assert render.call_count == 4
    interaction.response.send_message.assert_awaited_once_with(
        "Rendered", ephemeral=True, view=view
    )
    interaction.followup.send.assert_awaited_once_with(
        "Rendered", ephemeral=True, wait=True, view=view
    )
    interaction.response.edit_message.assert_awaited_once_with(
        content="Rendered", view=view
    )
    interaction.edit_original_response.assert_awaited_once_with(
        content="Rendered", view=view
    )
    with patch("hmwz.ui.messages.emojis.render") as render:
        await send_followup(interaction, embed=embed, view=view)
        await edit_interaction_response(
            interaction, content=None, embed=embed, view=view
        )
        render.assert_not_called()
    assert interaction.followup.send.await_args.kwargs["embed"] is embed
    assert interaction.response.edit_message.await_args.kwargs["content"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("helper", "method"),
    [
        (send_interaction_response, "initial"),
        (send_followup, "followup"),
        (edit_interaction_response, "edit"),
        (edit_original_response, "original"),
    ],
)
async def test_dialog_helpers_propagate_discord_failures(
    helper: Callable[[discord.Interaction], Awaitable[object]], method: str
) -> None:
    error = discord.Forbidden(SimpleNamespace(status=403, reason="Denied"), "Denied")
    failing = AsyncMock(side_effect=error)
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            response=SimpleNamespace(
                send_message=failing if method == "initial" else AsyncMock(),
                edit_message=failing if method == "edit" else AsyncMock(),
            ),
            original_response=AsyncMock(),
            edit_original_response=failing if method == "original" else AsyncMock(),
            followup=SimpleNamespace(
                send=failing if method == "followup" else AsyncMock()
            ),
        ),
    )
    with pytest.raises(discord.Forbidden):
        await helper(interaction)
