from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.i18n import RuntimeLocalizations
from hmwz.ui.components.localized import (
    LocalizedButton,
    LocalizedSelect,
    localize_buttons,
)
from hmwz.ui.messages import (
    defer_interaction,
    send_modal,
    dismiss_dialog,
    delete_temporary_message,
)
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.threads import create_thread, delete_thread, edit_thread, purge_messages
from hmwz.utils.loaders import fetch_thread
from hmwz.utils.text import escape_discord_text


def discord_error(status: int) -> discord.HTTPException | discord.RateLimited:
    if status == 429:
        return discord.RateLimited(retry_after=1)
    response = SimpleNamespace(status=status, reason="test error")
    error_type = {
        403: discord.Forbidden,
        404: discord.NotFound,
        500: discord.HTTPException,
    }[status]
    return error_type(response, "test error")


@pytest.fixture
def guild() -> Mock:
    guild = Mock(spec=discord.Guild, id=10)
    guild.name = "Guild"
    guild.preferred_locale = discord.Locale.german
    guild.get_thread.return_value = None
    guild.fetch_channel = AsyncMock()
    return guild


@pytest.fixture
def thread(guild: Mock) -> Mock:
    thread = Mock(spec=discord.Thread, id=20, guild=guild)
    thread.edit = AsyncMock(return_value=thread)
    thread.delete = AsyncMock()
    thread.purge = AsyncMock(return_value=[])
    return thread


@pytest.mark.asyncio
async def test_thread_loader_cache_api_and_missing(guild: Mock, thread: Mock) -> None:
    guild.get_thread.return_value = thread
    assert await fetch_thread(guild, 20) is thread
    guild.fetch_channel.assert_not_awaited()
    guild.get_thread.return_value = None
    guild.fetch_channel.return_value = thread
    assert await fetch_thread(guild, 20) is thread
    guild.fetch_channel.assert_awaited_once_with(20)
    guild.fetch_channel.side_effect = discord_error(404)
    assert await fetch_thread(guild, 20) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True])
async def test_thread_loader_rejects_other_guild(
    guild: Mock, thread: Mock, cached: bool
) -> None:
    thread.guild = Mock(spec=discord.Guild, id=11)
    if cached:
        guild.get_thread.return_value = thread
    else:
        guild.fetch_channel.return_value = thread
    with pytest.raises(RuntimeError, match="another guild"):
        await fetch_thread(guild, 20)


@pytest.mark.asyncio
async def test_thread_loader_rejects_non_thread(guild: Mock) -> None:
    guild.fetch_channel.return_value = Mock(spec=discord.TextChannel)
    with pytest.raises(RuntimeError, match="non-thread"):
        await fetch_thread(guild, 20)


@pytest.mark.asyncio
async def test_thread_operations_forward_options(thread: Mock) -> None:
    channel = Mock(spec=discord.TextChannel, id=30)
    channel.create_thread = AsyncMock(return_value=thread)
    assert await create_thread(channel, name="Test", reason="setup") is thread
    channel.create_thread.assert_awaited_once_with(
        name="Test",
        type=discord.ChannelType.public_thread,
        auto_archive_duration=10080,
        reason="setup",
    )
    assert await edit_thread(thread, name="New", archived=False, locked=False) is thread
    thread.edit.assert_awaited_once_with(name="New", archived=False, locked=False)
    await delete_thread(thread, reason="cleanup")
    thread.delete.assert_awaited_once_with(reason="cleanup")
    thread.delete.side_effect = discord_error(404)
    await delete_thread(thread)


@pytest.mark.asyncio
@pytest.mark.parametrize("in_thread", [False, True])
async def test_purge_disables_bulk_only_for_threads(in_thread: bool) -> None:
    channel = Mock(spec=discord.Thread if in_thread else discord.TextChannel, id=20)
    messages = [Mock(spec=discord.Message)]
    channel.purge = AsyncMock(return_value=messages)
    check = Mock(return_value=True)
    assert (
        await purge_messages(channel, limit=None, check=check, reason="reset")
        == messages
    )
    channel.purge.assert_awaited_once_with(
        limit=None,
        bulk=not in_thread,
        check=channel.purge.await_args.kwargs["check"],
        reason="reset",
    )
    delete_check = channel.purge.await_args.kwargs["check"]
    regular_message = Mock(spec=discord.Message)
    regular_message.is_system.return_value = False
    system_message = Mock(spec=discord.Message)
    system_message.is_system.return_value = True
    assert delete_check(regular_message)
    assert not delete_check(system_message)
    check.assert_called_once_with(regular_message)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["fetch", "create", "edit", "delete", "purge"])
@pytest.mark.parametrize("status", [403, 429, 500])
async def test_thread_failures_are_logged_and_propagated(
    guild: Mock,
    thread: Mock,
    operation: str,
    status: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = discord_error(status)
    with pytest.raises(type(error)) as captured:
        if operation == "fetch":
            guild.fetch_channel.side_effect = error
            await fetch_thread(guild, 20)
        elif operation == "create":
            channel = Mock(spec=discord.TextChannel, id=30)
            channel.create_thread = AsyncMock(side_effect=error)
            await create_thread(channel, name="Test")
        elif operation == "edit":
            thread.edit.side_effect = error
            await edit_thread(thread, archived=False)
        elif operation == "delete":
            thread.delete.side_effect = error
            await delete_thread(thread)
        else:
            thread.purge.side_effect = error
            await purge_messages(thread)
    assert captured.value is error
    assert caplog.records


@pytest.mark.asyncio
async def test_interaction_helpers_forward_options_and_modal() -> None:
    interaction = Mock(spec=discord.Interaction)
    interaction.response = SimpleNamespace(defer=AsyncMock(), send_modal=AsyncMock())
    await defer_interaction(interaction, thinking=True)
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    modal = discord.ui.Modal(title="Test")
    await send_modal(interaction, modal)
    interaction.response.send_modal.assert_awaited_once_with(modal)
    await defer_interaction(interaction, ephemeral=False)
    interaction.response.defer.assert_awaited_with(ephemeral=False, thinking=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["defer", "modal"])
@pytest.mark.parametrize("already_responded", [False, True])
async def test_interaction_helpers_propagate_errors(
    operation: str, already_responded: bool
) -> None:
    interaction = Mock(spec=discord.Interaction)
    error = (
        discord.InteractionResponded(interaction)
        if already_responded
        else discord_error(403)
    )
    interaction.response = SimpleNamespace(
        defer=AsyncMock(side_effect=error), send_modal=AsyncMock(side_effect=error)
    )
    with pytest.raises(type(error)) as captured:
        if operation == "defer":
            await defer_interaction(interaction)
        else:
            await send_modal(interaction, discord.ui.Modal(title="Test"))
    assert captured.value is error


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["de", "en"])
async def test_localized_components_preserve_native_options(
    guild: Mock, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    guild.preferred_locale = (
        discord.Locale.german if language == "de" else discord.Locale.american_english
    )
    monkeypatch.setitem(
        RuntimeLocalizations[language], "test.label", f"{language} {{number}}"
    )
    monkeypatch.setitem(
        RuntimeLocalizations[language], "test.placeholder", f"{language} Select"
    )
    button = LocalizedButton(
        guild,
        "test.label",
        values={"number": 2},
        custom_id="test:button",
        style=discord.ButtonStyle.success,
        row=1,
        disabled=True,
    )
    assert button.label == f"{language} 2"
    assert button.custom_id == "test:button"
    assert button.style == discord.ButtonStyle.success
    assert button.row == 1 and button.disabled
    option = discord.SelectOption(label="One", value="1", default=True)
    select = LocalizedSelect(
        guild,
        "test.placeholder",
        options=[option],
        custom_id="test:select",
        min_values=0,
        max_values=1,
        row=2,
    )
    assert select.placeholder == f"{language} Select"
    assert select.options == [option]
    assert select.custom_id == "test:select"
    assert select.min_values == 0 and select.max_values == 1 and select.row == 2
    view = discord.ui.View()
    view.add_item(button)
    link = discord.ui.Button(label="Keep", url="https://example.test")
    view.add_item(link)
    untouched = discord.ui.Button(label="Unchanged", custom_id="other")
    view.add_item(untouched)
    localize_buttons(view, guild, {"test:button": "test.placeholder"})
    assert button.label == f"{language} Select"
    assert link.label == "Keep" and untouched.label == "Unchanged"
    view.stop()


def test_escape_discord_text_masks_markdown_and_mentions_without_truncating() -> None:
    text = "**Player** <@123456789012345678> @everyone @here " + "x" * 100
    escaped = escape_discord_text(text)
    assert "\\*\\*Player\\*\\*" in escaped
    assert "<@123456789012345678>" not in escaped
    assert "@everyone" not in escaped and "@here" not in escaped
    assert escaped.endswith("x" * 100)
    assert escape_discord_text("") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_dismiss_uses_interaction_endpoint_not_channel_delete(
    missing: bool,
) -> None:
    interaction = Mock(spec=discord.Interaction)
    interaction.type = discord.InteractionType.component
    interaction.response = SimpleNamespace(is_done=lambda: False, defer=AsyncMock())
    interaction.message = Mock(spec=discord.Message)
    interaction.message.delete = AsyncMock(side_effect=discord_error(404))
    interaction.delete_original_response = AsyncMock(
        side_effect=discord_error(404) if missing else None
    )
    view = EphemeralView()
    await view.dismiss(interaction)
    assert view.is_finished()
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=False)
    interaction.delete_original_response.assert_awaited_once()
    interaction.message.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_dismiss_failure_is_logged_and_does_not_stop_view(
    caplog: pytest.LogCaptureFixture,
) -> None:
    interaction = Mock(spec=discord.Interaction)
    interaction.type = discord.InteractionType.component
    interaction.response = SimpleNamespace(is_done=lambda: False, defer=AsyncMock())
    interaction.delete_original_response = AsyncMock(side_effect=discord_error(403))
    view = EphemeralView()
    with pytest.raises(discord.Forbidden):
        await view.dismiss(interaction)
    assert not view.is_finished()
    assert caplog.records
    view.stop()


@pytest.mark.asyncio
async def test_dismiss_rejects_already_acknowledged_click() -> None:
    interaction = Mock(spec=discord.Interaction)
    interaction.type = discord.InteractionType.component
    interaction.response = SimpleNamespace(is_done=lambda: True, defer=AsyncMock())
    with pytest.raises(ValueError):
        await dismiss_dialog(interaction)
    interaction.response.defer.assert_not_awaited()


@pytest.mark.asyncio
async def test_immediate_temporary_deletion_does_not_schedule_background_delete() -> (
    None
):
    message = Mock(spec=discord.Message)
    message.delete = AsyncMock()
    await delete_temporary_message(message)
    message.delete.assert_awaited_once_with()
