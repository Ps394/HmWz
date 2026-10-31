"""Protocols describing module lifecycles and supported Discord events.

The protocols define the asynchronous hooks called by the guild-scoped
module manager.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import discord

from hmwz import events

@runtime_checkable
class ModuleProtocol(Protocol):
    """Contract for a guild-scoped module.

    Implementations can be created for a guild and synchronized by the manager.
    """

    guild: discord.Guild

    @classmethod
    async def create(cls, guild: discord.Guild, client) -> ModuleProtocol:
        """Create a module instance for a guild."""
        ...

    async def sync(self, startup: bool = False) -> bool:
        """Synchronize the module's persisted state."""
        ...

@runtime_checkable
class GuildModuleProtocol(Protocol):
    """Contract for modules that handle guild lifecycle events."""
    async def on_guild_join(self, guild: discord.Guild) -> bool:
        """Handle the bot joining a guild."""
        ...

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Handle the bot leaving a guild."""
        ...

@runtime_checkable
class MessageModuleProtocol(Protocol):
    """Contract for modules that manage Discord messages."""

    async def ensure(self) -> bool:
        """Restore or create managed messages."""
        ...

    async def on_message_create(self, message: discord.Message) -> bool:
        """Handle a newly created message."""
        ...

    async def on_message_update(self, before: discord.Message, after: discord.Message) -> bool:
        """Handle a message update."""
        ...

    async def on_message_delete(self, message: discord.Message) -> bool:
        """Handle a cached message deletion."""
        ...

    async def on_raw_message_delete(self, payload: events.RawMessageDeleteEvent) -> bool:
        """Handle a message deletion regardless of cache state."""
        ...

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Handle a bulk message deletion regardless of cache state."""
        ...

@runtime_checkable
class RoleModuleProtocol(Protocol):
    """Contract for modules that handle guild role events."""

    async def on_guild_role_create(self, role: discord.Role) -> bool:
        """Handle creation of a guild role."""
        ...

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> bool:
        """Handle an update to a guild role."""
        ...

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        """Handle deletion of a guild role."""
        ...

@runtime_checkable
class ChannelModuleProtocol(Protocol):
    """Contract for modules that handle guild channel events."""

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> bool:
        """Handle creation of a guild channel."""
        ...

    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> bool:
        """Handle an update to a guild channel."""
        ...

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Handle deletion of a guild channel."""
        ...

@runtime_checkable
class MemberModuleProtocol(Protocol):
    """Contract for modules that handle guild member events."""

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> bool:
        """Handle an update to a guild member."""
        ...

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool:
        """Handle a member removal regardless of cache state."""
        ...


type ModuleType = type[ModuleProtocol]
"""Type alias for a module class."""
type Modules = Sequence[ModuleProtocol]
"""Type alias for a sequence of module instances."""
