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
class ModuleProtocol(Protocol):
    """Formale Vertragsdefinition fuer ein Modul.

    Jedes Modul muss pro Guild instanzierbar sein und die bekannten
    Discord-Ereignisse asynchron verarbeiten koennen.
    """

    guild: discord.Guild

    @classmethod
    async def create(cls, guild: discord.Guild, client) -> ModuleProtocol: ...

    async def sync(self, startup: bool = False) -> bool: ...

@runtime_checkable
class GuildModuleProtocol(Protocol):
    """Formale Vertragsdefinition fuer ein Modul, das Gilden verwaltet."""
    async def on_guild_join(self, guild: discord.Guild) -> bool: ...

    async def on_guild_remove(self, guild: discord.Guild) -> bool: ...

@runtime_checkable
class MessageModuleProtocol(Protocol):
    """Formale Vertragsdefinition fuer ein Modul, das Nachrichten verwaltet."""

    async def ensure(self) -> bool: ...

    async def on_message_create(self, message: discord.Message) -> bool: ...

    async def on_message_update(self, before: discord.Message, after: discord.Message) -> bool: ...

    async def on_message_delete(self, message: discord.Message) -> bool: ...

    async def on_raw_message_delete(self, payload: events.RawMessageDeleteEvent) -> bool: ...

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool: ...

@runtime_checkable
class RoleModuleProtocol(Protocol):
    """Formale Vertragsdefinition fuer ein Modul, das Rollen verwaltet."""

    async def on_guild_role_create(self, role: discord.Role) -> bool: ...

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> bool: ...

    async def on_guild_role_delete(self, role: discord.Role) -> bool: ...

@runtime_checkable
class ChannelModuleProtocol(Protocol):
    """Formale Vertragsdefinition fuer ein Modul, das Channels verwaltet."""

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> bool: ...

    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> bool: ...

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool: ...

@runtime_checkable
class MemberModuleProtocol(Protocol):
    """Formale Vertragsdefinition fuer ein Modul, das Mitglieder verwaltet."""

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> bool: ...

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool: ...


type ModuleType = type[ModuleProtocol]
"""Typalias fuer eine Modulklasse."""
type Modules = Sequence[ModuleProtocol]
"""Typalias fuer eine Sequenz von Modulinstanzen."""
