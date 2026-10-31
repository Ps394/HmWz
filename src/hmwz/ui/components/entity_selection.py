"""Native or filtered Discord entity selection with owner validation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import discord

from .ephemeral_view import EphemeralView


class _RoleSelect(discord.ui.RoleSelect):
    def __init__(self, selection: EntitySelectionView, placeholder: str) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=selection.max_selected,
            row=0,
        )
        self.selection = selection

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selection.select_entities(
            interaction, [role.id for role in self.values]
        )


class _TextChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, selection: EntitySelectionView, placeholder: str) -> None:
        super().__init__(
            placeholder=placeholder,
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=selection.max_selected,
            row=0,
        )
        self.selection = selection

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selection.select_entities(
            interaction, [channel.id for channel in self.values]
        )


class _FilteredSelect(discord.ui.Select):
    def __init__(self, selection: EntitySelectionView, placeholder: str) -> None:
        super().__init__(placeholder=placeholder, min_values=0, row=0)
        self.selection = selection

    async def callback(self, interaction: discord.Interaction) -> None:
        visible_ids = {int(option.value) for option in self.options}
        await self.selection.select_entities(
            interaction,
            (self.selection.selected_ids - visible_ids)
            | {int(value) for value in self.values},
        )


class _PageButton(discord.ui.Button):
    def __init__(self, selection: EntitySelectionView, offset: int) -> None:
        super().__init__(
            label="<" if offset < 0 else ">",
            row=2,
            custom_id=f"entity_selection_page_{offset}",
        )
        self.selection = selection
        self.offset = offset

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.selection.interaction_check(interaction):
            return
        self.selection.page = max(
            0,
            min(
                self.selection.page + self.offset,
                (len(self.selection.options) - 1) // 25,
            ),
        )
        self.selection._refresh_filtered_select()
        await self.selection.on_selection_changed(interaction)


class EntitySelectionView(EphemeralView):
    """Reusable picker; subclasses render previews and apply changes.

    Native pickers show guild entities, not a filtered application-specific list.
    Explicit options instead show only allowed entities, with 25 per page.
    Disallowed selections are rejected as a whole without changing the preview.
    Callers must revalidate permissions and configuration before committing.
    """

    def __init__(
        self,
        *,
        owner_id: int,
        kind: Literal["role", "channel"],
        allowed_ids: Iterable[int],
        max_selected: int,
        placeholder: str,
        owner_message: str,
        invalid_message: str,
        options: Iterable[discord.SelectOption] | None = None,
        timeout: float = 180,
    ) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.kind = kind
        self.allowed_ids = frozenset(allowed_ids)
        if not self.allowed_ids or not 1 <= max_selected <= 25:
            raise ValueError(
                "A picker needs allowed entities and a limit from 1 to 25."
            )
        self.max_selected = min(max_selected, len(self.allowed_ids))
        self.owner_message = owner_message
        self.invalid_message = invalid_message
        self.selected_ids: set[int] = set()
        self.options = list(options) if options is not None else []
        self.page = 0
        self.page_buttons: list[_PageButton] = []
        self.entity_select: (
            discord.ui.RoleSelect | discord.ui.ChannelSelect | discord.ui.Select
        )
        if options is not None:
            option_ids = [int(option.value) for option in self.options]
            if set(option_ids) != self.allowed_ids or len(option_ids) != len(
                self.allowed_ids
            ):
                raise ValueError("Options must match the allowed entity IDs exactly.")
            self.entity_select = _FilteredSelect(self, placeholder)
            if len(self.options) > 25:
                self.page_buttons = [_PageButton(self, -1), _PageButton(self, 1)]
                for button in self.page_buttons:
                    self.add_item(button)
            self._refresh_filtered_select()
        else:
            self.entity_select = (
                _RoleSelect(self, placeholder)
                if kind == "role"
                else _TextChannelSelect(self, placeholder)
            )
        self.add_item(self.entity_select)

    def _refresh_filtered_select(self) -> None:
        if not isinstance(self.entity_select, discord.ui.Select):
            return
        self.entity_select.options = self.options[self.page * 25 : (self.page + 1) * 25]
        self.entity_select.max_values = min(
            self.max_selected, len(self.entity_select.options)
        )
        for option in self.options:
            option.default = int(option.value) in self.selected_ids
        for button in self.page_buttons:
            button.disabled = (
                self.page == 0
                if button.offset < 0
                else (self.page + 1) * 25 >= len(self.options)
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Allow only the person who opened the picker to use it."""
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(interaction, self.owner_message)
        return False

    async def select_entities(
        self, interaction: discord.Interaction, selected_ids: Iterable[int]
    ) -> None:
        """Replace a valid selection and retain it as picker defaults."""
        if not await self.interaction_check(interaction):
            return
        selected = set(selected_ids)
        if not selected <= self.allowed_ids or len(selected) > self.max_selected:
            await self.send_temporary_response(interaction, self.invalid_message)
            return
        self.selected_ids = selected
        default_type = (
            discord.SelectDefaultValueType.role
            if self.kind == "role"
            else discord.SelectDefaultValueType.channel
        )
        if isinstance(self.entity_select, discord.ui.Select):
            self._refresh_filtered_select()
        else:
            self.entity_select.default_values = [
                discord.SelectDefaultValue(id=entity_id, type=default_type)
                for entity_id in sorted(selected)
            ]
        await self.on_selection_changed(interaction)

    async def on_selection_changed(self, interaction: discord.Interaction) -> None:
        """Render the subclass's preview after a validated selection."""
        raise NotImplementedError
