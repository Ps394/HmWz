from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

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
    wz = WzGroup()
    command_names = {command.name for command in wz.commands}
    assert command_names == {"setup", "reset-channels", "reset-roles"}

    client = discord.Client(intents=discord.Intents.none())
    tree = discord.app_commands.CommandTree(client)
    tree.add_command(wz)
    payload = wz.to_dict(tree)
    assert all(option["type"] == 1 for option in payload["options"])


def test_wz_maintenance_commands_and_defaults() -> None:
    wz = WzGroup()
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
        channels=SimpleNamespace(
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
    message = followup.send.await_args.kwargs["embed"]
    view = followup.send.await_args.kwargs["view"]
    assert "<#20>" in message.fields[0].value
    assert "<#21>" in message.fields[0].value
    assert "ausgenommen" in message.fields[2].value
    assert isinstance(view.entity_select, discord.ui.Select)
    assert {option.value for option in view.entity_select.options} == {"20", "21"}
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
        in toggle_interaction.response.edit_message.await_args.kwargs["embed"]
        .fields[2]
        .value
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
        channels=SimpleNamespace(
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
    view.selected_ids.add(21)
    content = view.confirmation_embed(context)

    assert content.fields[0].value == "<@&20>"
    assert content.fields[1].value == "<@&21>"
    assert view.confirm_button is not None
    assert view.confirm_button.disabled is False

    view.selected_ids.add(20)
    view._update_confirm_button()
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
    view.selected_ids.add(21)
    confirm = next(
        item for item in view.children if item.custom_id == "wz_reset_roles_confirm"
    )

    await confirm.callback(context)

    member.remove_roles.assert_awaited_once_with(roles[20], reason="WZ Reset Roles")
    assert roles[21] not in member.remove_roles.await_args.args
    context.message.delete.assert_awaited_once()
    context.followup.send.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["role", "channel"])
async def test_reset_exception_picker_preview_clear_and_validation(kind: str) -> None:
    guild = Mock(spec=discord.Guild)
    roles = {
        index: SimpleNamespace(id=index, name=f"Role {index}", mention=f"<@&{index}>")
        for index in [20, 21]
    }
    guild.get_role.side_effect = roles.get
    context = SimpleNamespace(
        user=SimpleNamespace(id=1),
        locale=discord.Locale.german,
        response=SimpleNamespace(edit_message=AsyncMock()),
    )
    if kind == "role":
        view = ResetRolesConfirmation(
            guild=guild, owner_id=1, role_ids=[20, 21], context=context
        )
    else:
        view = CleanChannelsConfirmation(
            guild=guild, owner_id=1, channel_ids=[20, 21], context=context
        )
    select = view.entity_select
    assert isinstance(select, discord.ui.Select)
    assert {option.value for option in select.options} == {"20", "21"}
    assert select.min_values == 0 and select.max_values == 2
    await view.select_entities(context, [21])
    embed = context.response.edit_message.await_args.kwargs["embed"]
    assert "20>" in embed.fields[0].value and "21>" not in embed.fields[0].value
    assert "21>" in embed.fields[1].value and "20>" not in embed.fields[1].value
    assert embed.fields[1].name == "Ignoriert (1)"
    assert select.options[1].default
    view.send_temporary_response = AsyncMock()
    await view.select_entities(context, [22])
    assert view.selected_ids == {21}
    await view.select_entities(SimpleNamespace(user=SimpleNamespace(id=2)), [20])
    assert view.selected_ids == {21}
    assert view.send_temporary_response.await_count == 2
    await view.select_entities(context, [20, 21])
    confirm = next(
        item
        for item in view.children
        if item.custom_id in {"wz_reset_roles_confirm", "wz_clean_channels_confirm"}
    )
    assert confirm.disabled
    await view.select_entities(context, [])
    assert not confirm.disabled
    assert not any(option.default for option in select.options)


@pytest.mark.asyncio
async def test_channel_reset_skips_exceptions_and_revalidates_configuration() -> None:
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    channels = {
        index: SimpleNamespace(
            id=index,
            name=f"Channel {index}",
            mention=f"<#{index}>",
            purge=AsyncMock(return_value=[]),
        )
        for index in [20, 21, 22]
    }
    module = SimpleNamespace(
        channels=SimpleNamespace(
            get=AsyncMock(
                return_value=[
                    SimpleNamespace(channel_id=20),
                    SimpleNamespace(channel_id=21),
                ]
            )
        )
    )
    context = SimpleNamespace(
        user=SimpleNamespace(id=1),
        locale=discord.Locale.german,
        client=SimpleNamespace(
            module_manager=SimpleNamespace(get_module=AsyncMock(return_value=module))
        ),
        response=SimpleNamespace(defer=AsyncMock(), edit_message=AsyncMock()),
    )
    view = CleanChannelsConfirmation(
        guild=guild, owner_id=1, channel_ids=[20, 21, 22], context=context
    )
    await view.select_entities(context, [21])
    view.finish = AsyncMock()
    with patch(
        "hmwz.modules.hs.wz.commands.clean_channels.fetch_channel",
        new_callable=AsyncMock,
    ) as fetch:
        fetch.side_effect = lambda _guild, channel_id: channels[channel_id]
        await view.confirm.callback(context)
    channels[20].purge.assert_awaited_once()
    channels[21].purge.assert_not_awaited()
    channels[22].purge.assert_not_awaited()
    fetch.assert_awaited_once_with(guild, 20)
    view.finish.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["role", "channel"])
async def test_reset_legacy_exception_pages_can_ignore_more_than_25_entities(
    kind: str,
) -> None:
    guild = Mock(spec=discord.Guild)
    roles = {
        index: SimpleNamespace(id=index, name=f"Role {index}", mention=f"<@&{index}>")
        for index in range(30)
    }
    guild.get_role.side_effect = roles.get
    context = SimpleNamespace(
        user=SimpleNamespace(id=1),
        locale=discord.Locale.german,
        response=SimpleNamespace(edit_message=AsyncMock()),
    )
    if kind == "role":
        view = ResetRolesConfirmation(
            guild=guild, owner_id=1, role_ids=list(roles), context=context
        )
    else:
        view = CleanChannelsConfirmation(
            guild=guild, owner_id=1, channel_ids=list(roles), context=context
        )
    select = view.entity_select
    assert isinstance(select, discord.ui.Select)
    assert len(select.options) == select.max_values == 25
    with patch.object(
        discord.ui.Select,
        "values",
        new_callable=PropertyMock,
        return_value=[str(i) for i in range(25)],
    ):
        await select.callback(context)
    await view.page_buttons[1].callback(context)
    assert len(select.options) == select.max_values == 5
    with patch.object(
        discord.ui.Select,
        "values",
        new_callable=PropertyMock,
        return_value=[str(i) for i in range(25, 30)],
    ):
        await select.callback(context)
    assert view.selected_ids == set(range(30))
    confirm = next(
        item
        for item in view.children
        if item.custom_id in {"wz_reset_roles_confirm", "wz_clean_channels_confirm"}
    )
    assert confirm.disabled
    await view.page_buttons[0].callback(context)
    assert all(option.default for option in select.options)
    assert not view.page_buttons[1].disabled
    with patch.object(
        discord.ui.Select, "values", new_callable=PropertyMock, return_value=[]
    ):
        await select.callback(context)
    assert view.selected_ids == set(range(25, 30))
    assert not confirm.disabled
    embed = context.response.edit_message.await_args.kwargs["embed"]
    assert all(len(field.value) <= 1024 for field in embed.fields)
    assert len(embed) <= 6000


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["role", "channel"])
async def test_reset_ignoring_all_targets_performs_no_discord_changes(
    kind: str,
) -> None:
    guild = Mock(spec=discord.Guild)
    guild.id = 10
    guild.get_role.return_value = SimpleNamespace(id=20, name="Role", mention="<@&20>")
    module = SimpleNamespace(
        roles=SimpleNamespace(get=AsyncMock(return_value=[SimpleNamespace(role=20)])),
        channels=SimpleNamespace(
            get=AsyncMock(return_value=[SimpleNamespace(channel_id=20)])
        ),
    )
    context = SimpleNamespace(
        user=SimpleNamespace(id=1),
        locale=discord.Locale.german,
        client=SimpleNamespace(
            module_manager=SimpleNamespace(get_module=AsyncMock(return_value=module))
        ),
        response=SimpleNamespace(defer=AsyncMock(), edit_message=AsyncMock()),
    )
    if kind == "role":
        view = ResetRolesConfirmation(
            guild=guild, owner_id=1, role_ids=[20], context=context
        )
    else:
        view = CleanChannelsConfirmation(
            guild=guild, owner_id=1, channel_ids=[20], context=context
        )
    await view.select_entities(context, [20])
    view.finish = AsyncMock()
    confirm = next(
        item
        for item in view.children
        if item.custom_id in {"wz_reset_roles_confirm", "wz_clean_channels_confirm"}
    )
    with patch(
        "hmwz.modules.hs.wz.commands.clean_channels.fetch_channel",
        new_callable=AsyncMock,
    ) as fetch:
        await confirm.callback(context)
    fetch.assert_not_awaited()
    guild.fetch_members.assert_not_called()
    view.finish.assert_awaited_once()
