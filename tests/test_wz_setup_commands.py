from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from hmwz.modules.hs.wz.commands import WzGroup
from hmwz.modules.hs.wz.commands.clean_channels import (
    CleanChannelsConfirmation,
    clean_channels,
)
from hmwz.modules.hs.wz.commands.reset_roles import (
    ResetRolesConfirmation,
    reset_roles,
)


def test_wz_setup_exposes_only_module_commands() -> None:
    wz = WzGroup(None)
    command_names = {command.name for command in wz.commands}
    assert command_names == {"setup", "reset-channels", "reset-roles"}

    client = discord.Client(intents=discord.Intents.none())
    tree = discord.app_commands.CommandTree(client)
    tree.add_command(wz)
    payload = wz.to_dict(tree)
    assert all(option["type"] == 1 for option in payload["options"])


def test_wz_maintenance_commands_and_defaults() -> None:
    wz = WzGroup(None)
    command_names = {command.name for command in wz.commands}

    assert "setup" in command_names
    assert "reset-channels" in command_names
    assert "reset-roles" in command_names
    assert not clean_channels.parameters
    assert clean_channels.name == "reset-channels"
    assert reset_roles.name == "reset-roles"


@pytest.mark.asyncio
async def test_clean_channels_previews_targets_before_deleting() -> None:
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    module = SimpleNamespace(
        purge_channels=SimpleNamespace(
            get=AsyncMock(
                return_value=[
                    SimpleNamespace(channel_id=20),
                    SimpleNamespace(channel_id=21),
                ]
            )
        )
    )
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    followup = SimpleNamespace(send=AsyncMock())
    interaction = SimpleNamespace(
        guild=guild,
        client=SimpleNamespace(module_manager=manager),
        user=SimpleNamespace(id=1, __str__=lambda _self: "moderator"),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=followup,
    )

    await clean_channels.callback(interaction)

    followup.send.assert_awaited_once()
    message = followup.send.await_args.args[0]
    view = followup.send.await_args.kwargs["view"]
    assert "<#20>" in message
    assert "<#21>" in message
    assert "ausgenommen" in message
    assert isinstance(view, CleanChannelsConfirmation)
    assert view.ignore_pinned is True

    toggle = next(
        item
        for item in view.children
        if item.custom_id == "wz_clean_channels_toggle_pinned"
    )
    toggle_interaction = SimpleNamespace(
        user=SimpleNamespace(id=1),
        response=SimpleNamespace(edit_message=AsyncMock()),
    )
    await toggle.callback(toggle_interaction)
    assert view.ignore_pinned is False
    assert (
        "werden ebenfalls gelöscht"
        in toggle_interaction.response.edit_message.await_args.kwargs["content"]
    )


@pytest.mark.asyncio
async def test_clean_channels_confirmation_applies_pinned_message_exception() -> None:
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    channel = SimpleNamespace(
        purge=AsyncMock(return_value=[object()]),
        mention="<#20>",
        name="cleanup",
        id=20,
    )
    module = SimpleNamespace(
        purge_channels=SimpleNamespace(
            get=AsyncMock(return_value=[SimpleNamespace(channel_id=20)])
        )
    )
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    interaction = SimpleNamespace(
        guild=guild,
        client=SimpleNamespace(module_manager=manager),
        user=SimpleNamespace(id=1, __str__=lambda _self: "moderator"),
        locale=discord.Locale.german,
        response=SimpleNamespace(defer=AsyncMock()),
        message=SimpleNamespace(delete=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    view = CleanChannelsConfirmation(
        guild=guild,
        owner_id=1,
        channel_ids=[20],
        context=interaction,
    )
    confirm = next(
        item for item in view.children if item.custom_id == "wz_clean_channels_confirm"
    )

    with patch(
        "hmwz.modules.hs.wz.commands.clean_channels.fetch_channel",
        new_callable=AsyncMock,
        return_value=channel,
    ):
        await confirm.callback(interaction)

    channel.purge.assert_awaited_once()
    assert channel.purge.await_args.kwargs["limit"] is None
    check = channel.purge.await_args.kwargs["check"]
    assert check(SimpleNamespace(pinned=False)) is True
    assert check(SimpleNamespace(pinned=True)) is False
    interaction.message.delete.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_roles_confirmation_supports_configured_role_exceptions() -> None:
    roles = {
        20: SimpleNamespace(id=20, name="Alpha", mention="<@&20>"),
        21: SimpleNamespace(id=21, name="Bravo", mention="<@&21>"),
    }
    guild = Mock(spec=discord.Guild)
    guild.get_role.side_effect = roles.get
    context = SimpleNamespace(locale=discord.Locale.german)

    view = ResetRolesConfirmation(
        guild=guild,
        owner_id=1,
        role_ids=[20, 21],
        context=context,
    )
    view.exception_ids.add(21)
    content = view.confirmation_content(context)

    assert "<@&20>" in content
    assert "<@&21>" in content
    assert view.confirm_button is not None
    assert view.confirm_button.disabled is False

    view.exception_ids.add(20)
    view._refresh_components(context)
    assert view.confirm_button.disabled is True


@pytest.mark.asyncio
async def test_reset_roles_confirmation_keeps_selected_exceptions() -> None:
    roles = {
        20: SimpleNamespace(
            id=20,
            name="Alpha",
            mention="<@&20>",
            managed=False,
            is_default=lambda: False,
        ),
        21: SimpleNamespace(
            id=21,
            name="Bravo",
            mention="<@&21>",
            managed=False,
            is_default=lambda: False,
        ),
    }
    member = SimpleNamespace(
        id=30,
        roles=list(roles.values()),
        remove_roles=AsyncMock(),
    )

    async def fetch_members(*, limit):
        assert limit is None
        yield member

    guild = Mock(spec=discord.Guild)
    guild.id = 10
    guild.get_role.side_effect = roles.get
    guild.fetch_members = fetch_members
    module = SimpleNamespace(
        roles=SimpleNamespace(
            get=AsyncMock(
                return_value=[
                    SimpleNamespace(role=20),
                    SimpleNamespace(role=21),
                ]
            )
        )
    )
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    context = SimpleNamespace(
        user=SimpleNamespace(id=1),
        locale=discord.Locale.german,
        client=SimpleNamespace(module_manager=manager),
        response=SimpleNamespace(defer=AsyncMock()),
        message=SimpleNamespace(delete=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    view = ResetRolesConfirmation(
        guild=guild,
        owner_id=1,
        role_ids=[20, 21],
        context=context,
    )
    view.exception_ids.add(21)
    confirm = next(
        item for item in view.children if item.custom_id == "wz_reset_roles_confirm"
    )

    await confirm.callback(context)

    member.remove_roles.assert_awaited_once_with(roles[20], reason="WZ Reset Roles")
    assert roles[21] not in member.remove_roles.await_args.args
    context.message.delete.assert_awaited_once()
    context.followup.send.assert_awaited_once()
