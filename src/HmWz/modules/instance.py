"""Schnittstellen fuer Module.

Das Protocol beschreibt den erwarteten Lebenszyklus eines Moduls sowie
die Event-Handler, die guild-spezifisch vom Modulmanager aufgerufen
werden.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import discord

from hmwz import events


@runtime_checkable
class Module(Protocol):
    """Formale Vertragsdefinition fuer ein Modul.

    Jedes Modul muss pro Guild instanzierbar sein und die bekannten
    Discord-Ereignisse asynchron verarbeiten koennen.
    """

    guild: discord.Guild

    @classmethod
    async def create(cls, guild: discord.Guild, client) -> Module: ...

    async def sync(self, startup: bool = False) -> bool: ...

    async def ensure(self) -> bool: ...

    async def on_guild_join(self, guild: discord.Guild) -> bool: ...

    async def on_guild_remove(self, guild: discord.Guild) -> bool: ...

    async def on_guild_channel_create(
        self, channel: discord.abc.GuildChannel
    ) -> bool: ...

    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> bool: ...

    async def on_guild_channel_delete(
        self, channel: discord.abc.GuildChannel
    ) -> bool: ...

    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> bool: ...

    async def on_guild_role_delete(self, role: discord.Role) -> bool: ...

    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> bool: ...

    async def on_raw_member_remove(
        self, payload: events.RawMemberRemoveEvent
    ) -> bool: ...

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool: ...

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool: ...


type ModuleType = type[Module]
"""Typalias fuer eine Modulklasse."""
type Modules = Sequence[Module]
"""Typalias fuer eine Sequenz von Modulinstanzen."""
