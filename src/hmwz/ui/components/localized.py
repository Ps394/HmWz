"""Reusable localized Discord components with native callback support."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict, Unpack

import discord

from hmwz.i18n import t


class ButtonOptions(TypedDict, total=False):
    """Native button options other than the translated label."""

    style: discord.ButtonStyle
    disabled: bool
    custom_id: str | None
    url: str | None
    emoji: str | discord.Emoji | discord.PartialEmoji | None
    row: int | None
    sku_id: int | None
    id: int | None


class SelectOptions(TypedDict, total=False):
    """Native select options other than the translated placeholder."""

    custom_id: str
    min_values: int
    max_values: int
    options: list[discord.SelectOption]
    disabled: bool
    required: bool
    row: int | None
    id: int | None


class LocalizedButton(discord.ui.Button):
    """Button whose label is translated using the project runtime catalog."""

    def __init__(
        self,
        context: discord.Guild | discord.Interaction,
        key: str,
        *,
        values: Mapping[str, object] | None = None,
        **kwargs: Unpack[ButtonOptions],
    ) -> None:
        """Initialize a translated button.

        Args:
            context: Locale source.
            key: Runtime label translation key.
            values: Optional template substitutions.
            **kwargs: Native button options, excluding label.
        """
        super().__init__(label=t(context, key, **(values or {})), **kwargs)


class LocalizedSelect(discord.ui.Select):
    """Select whose placeholder is translated using the runtime catalog."""

    def __init__(
        self,
        context: discord.Guild | discord.Interaction,
        key: str,
        *,
        values: Mapping[str, object] | None = None,
        **kwargs: Unpack[SelectOptions],
    ) -> None:
        """Initialize a translated select.

        Args:
            context: Locale source.
            key: Runtime placeholder translation key.
            values: Optional template substitutions.
            **kwargs: Native select options, excluding placeholder.
        """
        super().__init__(placeholder=t(context, key, **(values or {})), **kwargs)


def localize_buttons(
    view: discord.ui.View,
    context: discord.Guild | discord.Interaction,
    keys: Mapping[str, str],
) -> None:
    """Translate decorator-created buttons by their stable custom IDs.

    Args:
        view: View containing native or localized buttons.
        context: Locale source.
        keys: Mapping of button custom IDs to runtime label keys.
    """
    for item in view.children:
        if (
            isinstance(item, discord.ui.Button)
            and item.custom_id is not None
            and item.custom_id in keys
        ):
            item.label = t(context, keys[item.custom_id])
