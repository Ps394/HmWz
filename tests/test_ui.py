from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.modules.donation.overview import DonationOverview
from hmwz.modules.donation.repository import DonationChannel
from hmwz.modules.registration.list_overview import RegistrationListOverview
from hmwz.modules.registration.repositories import (
    MemberRegistrationRepository,
    RegistrationMessageRepository,
)
from hmwz.ui.embeds import DEFAULT_EMBED_COLOR, create_embed
from hmwz.ui.messages import delete_message, edit_message, send_message


def test_create_embed_uses_shared_defaults() -> None:
    before = discord.utils.utcnow()
    embed = create_embed(title="Title", description="Description")
    after = discord.utils.utcnow()

    assert embed.title == "Title"
    assert embed.description == "Description"
    assert embed.color == DEFAULT_EMBED_COLOR
    assert embed.footer is not None
    assert embed.footer.text == "|"
    assert embed.timestamp is not None
    assert before <= embed.timestamp <= after


def test_create_embed_accepts_theme_overrides() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    avatar = SimpleNamespace(url="https://example.test/avatar.png")

    embed = create_embed(
        title="Title",
        color=discord.Color.gold(),
        client_avatar=cast(discord.Asset, avatar),
        footer_text="",
        timestamp=timestamp,
    )

    assert embed.color == discord.Color.gold()
    assert embed.footer is not None
    assert embed.footer.text == ""
    assert embed.footer.icon_url == avatar.url
    assert embed.timestamp == timestamp


def test_donation_overview_uses_shared_embed_theme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hmwz.modules.donation.overview.t",
        lambda _guild, key, **_kwargs: key,
    )
    channel = DonationChannel(
        channel_id=1,
        overview_message_id=None,
        ranking_message_id=None,
        title="Donations",
        description="Overview",
        goal_hours=None,
    )

    embed = DonationOverview.create_embed(
        SimpleNamespace(),
        channel,
        rush_start_at=None,
    )

    assert embed.footer is not None
    assert embed.footer.text == "|"
    assert embed.timestamp is not None
    assert embed.color == discord.Color.gold()


@pytest.mark.asyncio
async def test_registration_list_sends_messages_through_ui_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = SimpleNamespace(id=10)
    channel = SimpleNamespace(id=20)
    lists = SimpleNamespace(add=AsyncMock())
    overview = RegistrationListOverview(
        guild=cast(discord.Guild, SimpleNamespace(id=1)),
        registrations=cast(MemberRegistrationRepository, SimpleNamespace()),
        lists=cast(RegistrationMessageRepository, lists),
        module_key="wz",
        max_players=None,
    )
    send = AsyncMock(return_value=message)
    monkeypatch.setattr("hmwz.modules.registration.list_overview.send_message", send)
    embed = create_embed(title="Title", description="Description")

    await overview._create_message(cast(discord.TextChannel, channel), embed)

    send.assert_awaited_once_with(channel, embed=embed)
    lists.add.assert_awaited_once_with(
        guild=overview.guild,
        channel=channel.id,
        message=message.id,
        title="Title",
        text="Description",
    )


@pytest.mark.asyncio
async def test_message_wrappers_return_discord_results() -> None:
    message = SimpleNamespace()
    target = SimpleNamespace(send=AsyncMock(return_value=message))
    editable = SimpleNamespace(edit=AsyncMock(return_value=message))
    deletable = SimpleNamespace(delete=AsyncMock())

    assert (
        await send_message(cast(discord.abc.Messageable, target), content="hello")
        is message
    )
    assert (
        await edit_message(cast(discord.Message, editable), content="updated")
        is message
    )
    assert await delete_message(cast(discord.Message, deletable))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "status", "expected"),
    [
        ("send", 404, None),
        ("send", 403, None),
        ("send", 429, None),
        ("edit", 404, None),
        ("edit", 403, None),
        ("edit", 429, None),
        ("delete", 404, True),
        ("delete", 403, False),
        ("delete", 429, False),
    ],
)
async def test_message_wrappers_handle_discord_http_errors(
    operation: str,
    status: int,
    expected: discord.Message | bool | None,
) -> None:
    response = SimpleNamespace(status=status, reason="test error")
    if status == 429:
        error = discord.RateLimited(retry_after=1)
    else:
        error_type = {403: discord.Forbidden, 404: discord.NotFound}[status]
        error = error_type(response, "test error")
    method = AsyncMock(side_effect=error)
    target = SimpleNamespace(
        send=method,
        edit=method,
        delete=method,
    )

    if operation == "send":
        result = await send_message(cast(discord.abc.Messageable, target))
    elif operation == "edit":
        result = await edit_message(cast(discord.Message, target))
    else:
        result = await delete_message(cast(discord.Message, target))

    assert result is expected
