from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from hmwz.modules.hs.wz.commands.setup.channel.selection import ChannelSelection
from hmwz.modules.hs.wz.commands.setup.menu import (
    WzSetupMenu,
    WzSetupDraft,
    WzSetupSelectionView,
    configuration_embed,
    setup,
)
from hmwz.modules.hs.wz.commands.setup.role.selection import SetupRoleSelection


def make_interaction() -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(id=1),
        locale=discord.Locale.german,
        response=SimpleNamespace(
            edit_message=AsyncMock(),
            defer=AsyncMock(),
            send_message=AsyncMock(),
        ),
        message=SimpleNamespace(delete=AsyncMock()),
        edit_original_response=AsyncMock(),
        delete_original_response=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("acknowledged", [False, True])
async def test_setup_errors_use_temporary_helpers_without_action_buttons(
    acknowledged: bool,
) -> None:
    context = make_interaction()
    context.guild = None
    context.client = SimpleNamespace(module_manager=None)
    context.response.is_done = lambda: acknowledged
    with (
        patch(
            "hmwz.modules.hs.wz.commands.setup.menu.send_interaction_response",
            new_callable=AsyncMock,
        ) as initial_response,
        patch(
            "hmwz.modules.hs.wz.commands.setup.menu.send_temporary_followup",
            new_callable=AsyncMock,
        ) as followup,
    ):
        await setup.callback(context)
        selected = followup if acknowledged else initial_response
        other = initial_response if acknowledged else followup
        selected.assert_awaited_once()
        other.assert_not_awaited()
        assert "view" not in selected.await_args.kwargs


@pytest.mark.asyncio
async def test_setup_overview_groups_roles_and_bounds_large_legacy_channel_lists() -> (
    None
):
    context = make_interaction()
    guild = Mock(spec=discord.Guild)
    module = SimpleNamespace(
        guild=guild,
        roles=SimpleNamespace(
            get=AsyncMock(
                return_value=[
                    SimpleNamespace(role=10),
                    SimpleNamespace(role=11),
                ]
            )
        ),
        channels=SimpleNamespace(
            get=AsyncMock(
                return_value=[
                    SimpleNamespace(channel_id=10**18 + index) for index in range(80)
                ]
            )
        ),
    )
    embed = await configuration_embed(module, context)
    assert embed.fields[0].value == "<@&10>\n<@&11>"
    assert "55 weitere" in embed.fields[1].value
    assert all(len(field.value) <= 1024 and not field.inline for field in embed.fields)
    assert len(embed) <= 6000
    assert "**2/25**" in embed.description
    assert "**80/25**" in embed.description
    draft = WzSetupDraft(
        module=module,
        original_role_ids={10, 11},
        original_channel_ids={10**18 + index for index in range(80)},
        role_ids={10, 11},
        channel_ids={10**18 + index for index in range(80)},
    )
    view = WzSetupMenu(owner_id=1, context=context, draft=draft)
    assert view.add_role_button.row == view.remove_role_button.row == 0
    assert view.add_channel_button.row == view.remove_channel_button.row == 1
    assert view.save_button.row == view.cancel_button.row == 2


@pytest.mark.asyncio
async def test_wz_setup_selection_stages_changes_until_save() -> None:
    context = make_interaction()
    role = SimpleNamespace(id=42, name="Test role", mention="<@&42>")
    module = SimpleNamespace(
        guild=SimpleNamespace(),
        roles=SimpleNamespace(add=AsyncMock()),
        channels=SimpleNamespace(add=AsyncMock()),
    )
    draft = WzSetupDraft(
        module=module,
        original_role_ids=set(),
        original_channel_ids=set(),
        role_ids=set(),
        channel_ids=set(),
    )
    menu = WzSetupMenu(owner_id=1, context=context, draft=draft)
    selection = WzSetupSelectionView(
        menu,
        kind="role",
        action="add",
        entities=[role],
        max_selected=1,
        context=context,
    )
    selection.selected_ids.add(role.id)
    await selection.stage.callback(context)

    assert draft.role_ids == {role.id}
    module.roles.add.assert_not_awaited()
    assert context.response.edit_message.await_args.kwargs["view"] is menu
    await menu.cancel_button.callback(context)
    module.roles.add.assert_not_awaited()
    context.delete_original_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_wz_setup_save_persists_staged_role_and_channel_changes() -> None:
    role = SimpleNamespace(
        id=42,
        mention="<@&42>",
        is_default=lambda: False,
        managed=False,
    )
    guild = SimpleNamespace(
        id=10,
        me=None,
        get_role=lambda role_id: role if role_id == role.id else None,
    )
    persisted_role_ids: set[int] = set()
    persisted_channel_ids: set[int] = set()

    async def get_roles(*, guild):
        return tuple(SimpleNamespace(role=role_id) for role_id in persisted_role_ids)

    async def add_role(*, guild, role):
        persisted_role_ids.add(role)
        return True

    async def get_channels(*, guild):
        return tuple(
            SimpleNamespace(channel_id=channel_id)
            for channel_id in persisted_channel_ids
        )

    async def add_channel(*, guild, channel_id):
        persisted_channel_ids.add(channel_id)
        return True

    module = SimpleNamespace(
        guild=guild,
        roles=SimpleNamespace(
            get=AsyncMock(side_effect=get_roles), add=AsyncMock(side_effect=add_role)
        ),
        channels=SimpleNamespace(
            get=AsyncMock(side_effect=get_channels),
            add=AsyncMock(side_effect=add_channel),
        ),
    )
    draft = WzSetupDraft(
        module=module,
        original_role_ids=set(),
        original_channel_ids=set(),
        role_ids={42},
        channel_ids={30},
    )
    menu = WzSetupMenu(
        owner_id=1,
        context=make_interaction(),
        draft=draft,
    )
    context = make_interaction()

    with patch(
        "hmwz.modules.hs.wz.commands.setup.menu.send_temporary_followup",
        new_callable=AsyncMock,
    ) as saved:
        await menu.save(context)

    assert persisted_role_ids == {42}
    assert persisted_channel_ids == {30}
    module.roles.add.assert_awaited_once_with(guild=guild, role=42)
    module.channels.add.assert_awaited_once_with(guild=guild, channel_id=30)
    context.delete_original_response.assert_awaited_once()
    saved.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_role_selection_enables_review_and_confirms() -> None:
    context = make_interaction()
    role = SimpleNamespace(id=30, mention="<@&30>")
    guild = Mock(spec=discord.Guild)
    guild.get_role.side_effect = {30: role}.get
    view = SetupRoleSelection(
        guild=guild,
        module=SimpleNamespace(),
        owner_id=1,
        action="add",
        roles=[role],
        max_selected=1,
        context=context,
    )
    assert isinstance(view.entity_select, discord.ui.RoleSelect)
    assert view.review_button.disabled
    assert {
        item.custom_id for item in view.children if isinstance(item, discord.ui.Button)
    } == {"wz_role_select_review", "wz_role_select_cancel"}
    await view.select_entities(context, [30])
    assert not view.review_button.disabled
    preview = context.response.edit_message.await_args.kwargs["embed"]
    assert preview.fields[0].value == "<@&30>"
    assert not view.is_finished()
    await view.review_button.callback(context)
    confirmation = context.response.edit_message.await_args.kwargs["view"]
    assert confirmation.selected_role_ids == [30]
    assert not hasattr(view, "permanent")
    assert "permanent" not in context.response.edit_message.await_args.kwargs["content"]
    assert context.response.edit_message.await_args.kwargs["embed"] is None
    assert view.is_finished()


@pytest.mark.asyncio
async def test_channel_picker_validates_candidates_and_can_clear_selection() -> None:
    context = make_interaction()
    channel = SimpleNamespace(id=30, mention="<#30>")
    view = ChannelSelection(
        guild=Mock(spec=discord.Guild),
        module=SimpleNamespace(),
        owner_id=1,
        action="add",
        channels=[channel],
        max_values=1,
        context=context,
    )
    assert isinstance(view.entity_select, discord.ui.ChannelSelect)
    assert view.review_button.disabled
    view.send_temporary_response = AsyncMock()
    await view.select_entities(context, [31])
    assert view.review_button.disabled
    view.send_temporary_response.assert_awaited_once()
    await view.select_entities(context, [30])
    assert not view.review_button.disabled
    assert (
        context.response.edit_message.await_args.kwargs["embed"].fields[0].value
        == "<#30>"
    )
    await view.select_entities(context, [])
    assert view.review_button.disabled
    assert view.selected_ids == set()


@pytest.mark.asyncio
async def test_role_picker_supports_all_25_roles_in_one_selection() -> None:
    context = make_interaction()
    roles = [SimpleNamespace(id=index, mention=f"<@&{index}>") for index in range(25)]
    view = SetupRoleSelection(
        guild=Mock(spec=discord.Guild),
        module=SimpleNamespace(),
        owner_id=1,
        action="add",
        roles=roles,
        max_selected=25,
        context=context,
    )
    assert view.entity_select.max_values == 25
    await view.select_entities(context, [role.id for role in roles])
    assert len(view.selected_ids) == 25
    assert not view.review_button.disabled
    preview = context.response.edit_message.await_args.kwargs["embed"]
    assert all(role.mention in preview.fields[0].value for role in roles)


@pytest.mark.asyncio
async def test_remove_roles_picker_only_offers_review_and_cancel() -> None:
    context = make_interaction()
    role = SimpleNamespace(id=30, name="Configured role", mention="<@&30>")
    view = SetupRoleSelection(
        guild=Mock(spec=discord.Guild),
        module=SimpleNamespace(),
        owner_id=1,
        action="remove",
        roles=[role],
        max_selected=1,
        context=context,
    )
    button_ids = {
        item.custom_id for item in view.children if isinstance(item, discord.ui.Button)
    }
    assert button_ids == {"wz_role_select_review", "wz_role_select_cancel"}
    assert isinstance(view.entity_select, discord.ui.Select)
    assert [(option.label, option.value) for option in view.entity_select.options] == [
        ("Configured role", "30")
    ]
    assert view.review_button.disabled
    await view.select_entities(context, [30])
    assert view.entity_select.options[0].default
    assert not view.review_button.disabled
    await view.select_entities(context, [])
    assert view.review_button.disabled


@pytest.mark.asyncio
async def test_remove_channels_picker_only_lists_configured_channels() -> None:
    context = make_interaction()
    channels = [
        SimpleNamespace(id=30, name="configured-channel", mention="<#30>"),
        SimpleNamespace(id=31, name="other-configured-channel", mention="<#31>"),
    ]
    view = ChannelSelection(
        guild=Mock(spec=discord.Guild),
        module=SimpleNamespace(),
        owner_id=1,
        action="remove",
        channels=channels,
        max_values=2,
        context=context,
    )
    assert isinstance(view.entity_select, discord.ui.Select)
    assert [(option.label, option.value) for option in view.entity_select.options] == [
        ("configured-channel", "30"),
        ("other-configured-channel", "31"),
    ]
    view.send_temporary_response = AsyncMock()
    await view.select_entities(context, [32])
    view.send_temporary_response.assert_awaited_once()
    assert not view.selected_ids
    await view.select_entities(context, [30])
    assert view.entity_select.options[0].default
    assert not view.review_button.disabled
    await view.select_entities(context, [])
    assert view.review_button.disabled


@pytest.mark.asyncio
async def test_channel_review_revalidates_before_confirmation() -> None:
    context = make_interaction()
    guild = Mock(spec=discord.Guild)
    guild.get_channel.return_value = None
    channel = SimpleNamespace(id=30, name="configured-channel", mention="<#30>")
    module = SimpleNamespace(
        channels=SimpleNamespace(get=AsyncMock(return_value=[])),
    )
    view = ChannelSelection(
        guild=guild,
        module=module,
        owner_id=1,
        action="remove",
        channels=[channel],
        max_values=1,
        context=context,
    )
    view.finish = AsyncMock()
    await view.select_entities(context, [30])
    await view.review_button.callback(context)
    view.finish.assert_awaited_once()
    module.channels.get.assert_awaited_once_with(guild=guild)
    assert context.response.edit_message.await_count == 1
