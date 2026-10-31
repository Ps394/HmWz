from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.client import Client
from hmwz.modules.overview import OverviewModule
from hmwz.modules.overview.models import Overview, OverviewButton
from hmwz.modules.overview.repositories import OverviewRepository
from hmwz.modules.overview.views import OverviewView
from hmwz.sqlite_db import Database
from hmwz.ui.embeds import create_embed


@pytest.mark.asyncio
async def test_overview_repository_saves_and_loads_configuration(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="overview.db")
    repository = OverviewRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=123))
    overview = Overview(
        guild_id=guild.id,
        overview_id="registration",
        channel_id=456,
        message_id=789,
        title="Registrierung",
        description="Wähle deine Rolle.",
        buttons=(
            OverviewButton(
                button_id="register",
                label="Anmelden",
                style=discord.ButtonStyle.success,
                row=0,
            ),
        ),
    )

    assert await repository.ensure_schema()
    assert await repository.save(overview)
    assert await repository.get(guild=guild, overview_id="registration") == overview
    assert await repository.get_all(guild=guild) == (overview,)

    assert await repository.set_message(
        guild=guild, overview_id="registration", message_id=None
    )
    saved = await repository.get(guild=guild, overview_id="registration")
    assert saved is not None
    assert saved.message_id is None


@pytest.mark.asyncio
async def test_overview_repository_removes_guild_records(tmp_path: Path) -> None:
    database = Database(folder=str(tmp_path), filename="overview.db")
    repository = OverviewRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=321))
    overview = Overview(
        guild_id=guild.id,
        overview_id="welcome",
        channel_id=654,
        message_id=None,
        title="Willkommen",
        description="",
    )

    assert await repository.ensure_schema()
    assert await repository.save(overview)
    assert await repository.remove_guild(guild=guild)
    assert await repository.get_all(guild=guild) == ()


@pytest.fixture
async def overview_service(tmp_path: Path) -> tuple[OverviewModule, Mock, Mock]:
    message = Mock(spec=discord.Message)
    message.id = 789
    message.embeds = [
        create_embed(
            title="Title",
            description="Description",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    message.components = []
    message.edit = AsyncMock(return_value=message)
    channel = Mock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    channel.send = AsyncMock(return_value=message)
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=123, name="guild", get_channel_or_thread=lambda _channel_id: channel
        ),
    )
    client = cast(
        Client,
        SimpleNamespace(
            _database=Database(folder=str(tmp_path), filename="overview-service.db"),
            add_view=Mock(),
        ),
    )
    module = OverviewModule(guild, client)
    assert await module.sync()
    assert await module.overviews.save(
        Overview(
            guild_id=123,
            overview_id="registration",
            channel_id=456,
            message_id=789,
            title="Title",
            description="Description",
        )
    )
    return module, message, channel


@pytest.mark.asyncio
async def test_identical_overview_ignores_generated_timestamp(
    overview_service: tuple[OverviewModule, Mock, Mock],
) -> None:
    module, message, channel = overview_service
    for _ in range(2):
        assert await module.publish(
            overview_id="registration",
            channel_id=456,
            title="Title",
            description="Description",
        )
    message.edit.assert_not_awaited()
    channel.send.assert_not_awaited()
    assert channel.fetch_message.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "title",
        "description",
        "color",
        "footer",
        "fields",
        "extra_embed",
        "missing_embed",
    ],
)
async def test_different_discord_content_is_edited_even_if_storage_matches(
    overview_service: tuple[OverviewModule, Mock, Mock], change: str
) -> None:
    module, message, _channel = overview_service
    embed = message.embeds[0]
    if change == "title":
        embed.title = "Old title"
    elif change == "description":
        embed.description = "Old description"
    elif change == "color":
        embed.color = discord.Color.red()
    elif change == "footer":
        embed.set_footer(text="Old footer")
    elif change == "fields":
        embed.add_field(name="Extra", value="Field")
    elif change == "extra_embed":
        message.embeds.append(create_embed(title="Extra embed"))
    else:
        message.embeds = []

    assert await module.publish(
        overview_id="registration",
        channel_id=456,
        title="Title",
        description="Description",
    )
    message.edit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", [None, "label", "style", "custom_id", "disabled", "layout", "missing"]
)
async def test_button_content_and_layout_comparison(
    overview_service: tuple[OverviewModule, Mock, Mock], change: str | None
) -> None:
    module, message, _channel = overview_service
    buttons = (
        OverviewButton(
            button_id="register", label="Register", style=discord.ButtonStyle.success
        ),
        OverviewButton(
            button_id="remove", label="Remove", style=discord.ButtonStyle.danger
        ),
    )
    overview = Overview(
        guild_id=123,
        overview_id="registration",
        channel_id=456,
        message_id=789,
        title="Title",
        description="Description",
        buttons=buttons,
    )
    view = OverviewView(overview, module._dispatch_button)
    components = view.to_components()
    components[0]["id"] = 1
    components[0]["components"][0]["id"] = 2
    first_button = components[0]["components"][0]
    if change == "label":
        first_button["label"] = "Old label"
    elif change == "style":
        first_button["style"] = discord.ButtonStyle.primary.value
    elif change == "custom_id":
        first_button["custom_id"] = "old-handler"
    elif change == "disabled":
        first_button["disabled"] = True
    elif change == "layout":
        second_button = components[0]["components"].pop()
        components.append({"type": 1, "components": [second_button], "id": 3})
    elif change == "missing":
        components = []
    message.components = [discord.ActionRow(row) for row in components]

    assert await module.publish(
        overview_id="registration",
        channel_id=456,
        title="Title",
        description="Description",
        buttons=buttons,
    )
    if change is None:
        message.edit.assert_not_awaited()
    else:
        message.edit.assert_awaited_once()
    module.client.add_view.assert_called_once()
    if change is None:
        handler = AsyncMock()
        module.register_handler(
            overview_id="registration", button_id="register", handler=handler
        )
        restored_view = module.client.add_view.call_args.args[0]
        interaction = Mock(spec=discord.Interaction)
        await restored_view.children[0].callback(interaction)
        handler.assert_awaited_once_with(interaction)


@pytest.mark.asyncio
async def test_removed_buttons_are_edited(
    overview_service: tuple[OverviewModule, Mock, Mock],
) -> None:
    module, message, _channel = overview_service
    message.components = [
        discord.ActionRow(
            {
                "type": 1,
                "components": [
                    {"type": 2, "style": 1, "label": "Old", "custom_id": "old"}
                ],
            }
        )
    ]
    assert await module.publish(
        overview_id="registration",
        channel_id=456,
        title="Title",
        description="Description",
    )
    message.edit.assert_awaited_once()
    assert message.edit.await_args.kwargs["view"] is None


@pytest.mark.asyncio
async def test_missing_message_is_recreated(
    overview_service: tuple[OverviewModule, Mock, Mock],
) -> None:
    module, message, channel = overview_service
    channel.fetch_message.side_effect = discord.NotFound(
        SimpleNamespace(status=404, reason="Not found"), "Missing message"
    )
    message.id = 999
    assert await module.publish(
        overview_id="registration",
        channel_id=456,
        title="Title",
        description="Description",
    )
    channel.send.assert_awaited_once()
    message.edit.assert_not_awaited()
    saved = await module.overviews.get(guild=module.guild, overview_id="registration")
    assert saved is not None and saved.message_id == 999


@pytest.mark.asyncio
async def test_failed_edit_is_reported_and_retried(
    overview_service: tuple[OverviewModule, Mock, Mock],
) -> None:
    module, message, _channel = overview_service
    message.embeds[0].title = "Old title"
    message.edit.side_effect = discord.HTTPException(
        SimpleNamespace(status=500, reason="Server error"), "Failed edit"
    )
    assert not await module.publish(
        overview_id="registration",
        channel_id=456,
        title="Title",
        description="Description",
    )
    message.edit.side_effect = None
    assert await module.publish(
        overview_id="registration",
        channel_id=456,
        title="Title",
        description="Description",
    )
    assert message.edit.await_count == 2


@pytest.mark.asyncio
async def test_successful_content_change_is_not_edited_again(
    overview_service: tuple[OverviewModule, Mock, Mock],
) -> None:
    module, message, _channel = overview_service

    async def edit(
        *, embed: discord.Embed, view: OverviewView | None
    ) -> discord.Message:
        message.embeds = [embed]
        message.components = (
            [discord.ActionRow(row) for row in view.to_components()] if view else []
        )
        return cast(discord.Message, message)

    message.edit.side_effect = edit
    for _ in range(2):
        assert await module.publish(
            overview_id="registration",
            channel_id=456,
            title="New title",
            description="New description",
        )
    message.edit.assert_awaited_once()
