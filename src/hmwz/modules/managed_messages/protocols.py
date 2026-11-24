"""Callback contracts used by the managed-messages infrastructure."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

import discord

ManagedViewFactory = Callable[[str], discord.ui.View | None]
ManagedMessageRefreshHandler = Callable[[str], Awaitable[bool]]
ManagedBatchRefreshHandler = Callable[[frozenset[str]], Awaitable[bool]]
ManagedChannelDeleteHandler = Callable[[int, Iterable[str]], Awaitable[bool]]
ManagedThreadDeleteHandler = Callable[[int, Iterable[str]], Awaitable[bool]]
