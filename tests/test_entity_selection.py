from types import SimpleNamespace
from typing import Literal
from unittest.mock import AsyncMock, PropertyMock, patch

import discord
import pytest

from hmwz.ui.components.entity_selection import EntitySelectionView


class RecordingSelection(EntitySelectionView):
    def __init__(
        self,
        kind: Literal["role", "channel"] = "role",
        max_selected: int = 3,
        options: list[discord.SelectOption] | None = None,
    ) -> None:
        super().__init__(
            owner_id=1,
            kind=kind,
            allowed_ids=range(100)
            if options is None
            else [int(o.value) for o in options],
            max_selected=max_selected,
            placeholder="Search",
            owner_message="Owner only",
            invalid_message="Invalid selection",
            options=options,
        )
        self.changed = AsyncMock()
        self.send_temporary_response = AsyncMock()

    async def on_selection_changed(self, interaction: discord.Interaction) -> None:
        await self.changed(interaction)


def interaction(user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(user=SimpleNamespace(id=user_id))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["role", "channel"])
async def test_native_pickers_support_more_than_25_candidates_and_callbacks(
    kind: Literal["role", "channel"],
) -> None:
    view = RecordingSelection(kind)
    assert len(view.children) == 1
    select = view.entity_select
    select_type = discord.ui.RoleSelect if kind == "role" else discord.ui.ChannelSelect
    assert isinstance(select, select_type)
    assert select.min_values == 0
    assert select.max_values == 3
    if kind == "channel":
        assert select.channel_types == [discord.ChannelType.text]
    context = interaction()
    with patch.object(
        select_type,
        "values",
        new_callable=PropertyMock,
        return_value=[SimpleNamespace(id=99), SimpleNamespace(id=75)],
    ):
        await select.callback(context)
    assert view.selected_ids == {75, 99}
    assert [value.id for value in select.default_values] == [75, 99]
    view.changed.assert_awaited_once_with(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("selected", [[101], [1, 2, 3, 4], [1, 101]])
async def test_invalid_selection_preserves_last_valid_preview(
    selected: list[int],
) -> None:
    view = RecordingSelection()
    context = interaction()
    await view.select_entities(context, [2])
    view.changed.reset_mock()
    await view.select_entities(context, selected)
    assert view.selected_ids == {2}
    assert [value.id for value in view.entity_select.default_values] == [2]
    view.changed.assert_not_awaited()
    view.send_temporary_response.assert_awaited_once_with(context, "Invalid selection")


@pytest.mark.asyncio
async def test_native_selection_replaces_and_clears_instead_of_accumulating() -> None:
    view = RecordingSelection()
    context = interaction()
    await view.select_entities(context, [1, 2])
    await view.select_entities(context, [3, 3])
    assert view.selected_ids == {3}
    await view.select_entities(context, [])
    assert view.selected_ids == set()
    assert view.entity_select.default_values == []


@pytest.mark.asyncio
async def test_picker_rejects_other_users() -> None:
    view = RecordingSelection()
    context = interaction(user_id=2)
    await view.select_entities(context, [1])
    assert view.selected_ids == set()
    view.changed.assert_not_awaited()
    view.send_temporary_response.assert_awaited_once_with(context, "Owner only")


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 26])
async def test_picker_rejects_invalid_discord_limits(limit: int) -> None:
    with pytest.raises(ValueError):
        RecordingSelection(max_selected=limit)


@pytest.mark.asyncio
async def test_filtered_picker_pages_preserve_defaults_and_enforce_global_limit() -> (
    None
):
    view = RecordingSelection(
        max_selected=2,
        options=[
            discord.SelectOption(label=f"Role {index}", value=str(index))
            for index in range(30)
        ],
    )
    select = view.entity_select
    assert isinstance(select, discord.ui.Select)
    assert len(select.options) == 25
    assert view.page_buttons[0].disabled
    context = interaction()
    with patch.object(
        discord.ui.Select, "values", new_callable=PropertyMock, return_value=["1"]
    ):
        await select.callback(context)
    await view.page_buttons[1].callback(context)
    assert [option.value for option in select.options] == [
        str(i) for i in range(25, 30)
    ]
    assert view.page_buttons[1].disabled
    with patch.object(
        discord.ui.Select, "values", new_callable=PropertyMock, return_value=["25"]
    ):
        await select.callback(context)
    assert view.selected_ids == {1, 25}
    with patch.object(
        discord.ui.Select,
        "values",
        new_callable=PropertyMock,
        return_value=["25", "26"],
    ):
        await select.callback(context)
    assert view.selected_ids == {1, 25}
    view.send_temporary_response.assert_awaited_once_with(context, "Invalid selection")
    await view.page_buttons[0].callback(context)
    assert select.options[1].default
    with patch.object(
        discord.ui.Select, "values", new_callable=PropertyMock, return_value=[]
    ):
        await select.callback(context)
    assert view.selected_ids == {25}


@pytest.mark.asyncio
async def test_filtered_picker_rejects_other_users_on_selection_and_paging() -> None:
    view = RecordingSelection(
        options=[
            discord.SelectOption(label=str(index), value=str(index))
            for index in range(26)
        ],
    )
    context = interaction(user_id=2)
    await view.page_buttons[1].callback(context)
    await view.select_entities(context, [1])
    assert view.page == 0
    assert not view.selected_ids
    view.changed.assert_not_awaited()
    assert view.send_temporary_response.await_count == 2


@pytest.mark.asyncio
async def test_filtered_picker_requires_options_matching_allowed_ids() -> None:
    with pytest.raises(ValueError, match="match the allowed"):
        EntitySelectionView(
            owner_id=1,
            kind="role",
            allowed_ids=[1, 2],
            max_selected=2,
            placeholder="Select",
            owner_message="Owner only",
            invalid_message="Invalid",
            options=[discord.SelectOption(label="Role", value="1")],
        )
