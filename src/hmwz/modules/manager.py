"""Create guild-scoped module instances and route Discord events to them."""

from __future__ import annotations

import asyncio
import logging

import discord

from hmwz import events

from .protocols import ModuleProtocol, Modules, ModuleType, ChannelModuleProtocol, MemberModuleProtocol, RoleModuleProtocol, MessageModuleProtocol
from .registry import REGISTRY

_logger = logging.getLogger(__name__)


class Manager:
    """Manage guild-scoped module instances and dispatch Discord events."""

    def __init__(self, client):
        """Create a module manager for a Discord client.

        Args:
            client: Discord client used to create module instances.
        """
        self.client = client
        self._modules_by_guild: dict[int, list[ModuleProtocol]] = {}

    async def get_modules(self, guild: discord.Guild) -> Modules:
        """Return all module instances for a guild.

        Instances are created from the registry and cached on first access.

        Args:
            guild: Guild whose modules should be retrieved.

        Returns:
            The guild's module instances.
        """
        if guild.id not in self._modules_by_guild:
            modules: list[ModuleProtocol] = []
            for factory in REGISTRY:
                try:
                    modules.append(await factory.create(guild, self.client))
                except Exception as e:
                    _logger.exception(
                        f"{guild.name} ({guild.id}) - Failed to create module {getattr(factory, '__name__', factory)}: {e}"
                    )
            self._modules_by_guild[guild.id] = modules
        return self._modules_by_guild[guild.id]

    async def get_module(self, guild: discord.Guild, module_type: ModuleType):
        """Return the module instance matching a requested type.

        Args:
            guild: Guild whose modules should be searched.
            module_type: Module class or protocol used to identify the instance.

        Returns:
            The matching guild-scoped module.

        Raises:
            LookupError: If no module of the requested type is registered.
        """
        modules = await self.get_modules(guild)
        for module in modules:
            if isinstance(module, module_type):
                return module
        raise LookupError(
            f"Module of type {module_type} not found for guild "
            f"{guild.name} ({guild.id})."
        )

    async def startup(self) -> None:
        """Initialize modules for all currently connected guilds."""
        await asyncio.gather(*(self.init_guild(guild) for guild in self.client.guilds))
        _logger.info("Module manager startup complete.")

    async def close(self) -> None:
        """Stop optional background workers owned by guild modules."""
        for guild_modules in self._modules_by_guild.values():
            for module in guild_modules:
                close = getattr(module, "close", None)
                if close is not None:
                    await close()

    async def on_disconnect(self) -> None:
        """Notify optional module workers of gateway disconnection."""
        for guild_modules in self._modules_by_guild.values():
            for module in guild_modules:
                handler = getattr(module, "on_disconnect", None)
                if handler is not None:
                    await handler()

    async def init_guild(self, guild: discord.Guild) -> None:
        """Run startup synchronization and message restoration for a guild.

        Args:
            guild: Guild whose modules should be initialized.
        """
        modules = await self.get_modules(guild)
        for module in modules:
            try:
                await module.sync(startup=True)
                if isinstance(module, MessageModuleProtocol):
                    await module.ensure()
            except Exception as e:
                _logger.exception(
                    f"{guild.name} ({guild.id}) - Failed to initialize module {module.__class__.__name__}: {e}"
                )

    async def sync(self, guild: discord.Guild, startup: bool = False) -> bool:
        """Synchronize each module for a guild and restore managed messages.

        Args:
            guild: Guild whose modules should be synchronized.
            startup: Whether this synchronization is part of startup.

        Returns:
            Whether every module synchronized successfully.
        """
        modules = await self.get_modules(guild)
        status = True
        for module in modules:
            try:
                await module.sync(startup=startup)
                if isinstance(module, MessageModuleProtocol):
                    await module.ensure()
            except Exception as e:
                _logger.exception(
                    f"{guild.name} ({guild.id}) - Failed to sync module {module.__class__.__name__}: {e}"
                )
                status = False
        return status

    async def _dispatch(self, guild: discord.Guild, method_name: str, *args) -> bool:
        """Dispatch an event handler to every module associated with a guild.

        Args:
            guild: Guild whose modules receive the event.
            method_name: Name of the handler to invoke.
            *args: Event arguments passed to each matching handler.

        Returns:
            Whether all invoked handlers completed successfully.
        """
        modules = await self.get_modules(guild)
        status = True
        for module in modules:
            handler = getattr(module, method_name, None)
            if not handler:
                continue
            try:
                await handler(*args)
            except Exception as e:
                _logger.exception(
                    f"{guild.name} ({guild.id}) - Module {module.__class__.__name__} failed in {method_name}: {e}"
                )
                status = False
        return status

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        """Dispatch a guild-join event to the guild's modules."""
        self._modules_by_guild.pop(guild.id, None)
        return await self._dispatch(guild, "on_guild_join", guild)

    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> bool:
        """Dispatch a guild-update event to the guild's modules."""
        return await self._dispatch(after, "on_guild_update", before, after)

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Dispatch a guild-removal event, then discard its module instances."""
        status = await self._dispatch(guild, "on_guild_remove", guild)
        self._modules_by_guild.pop(guild.id, None)
        return status

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> bool:
        """Dispatch a guild-channel creation event to its modules."""
        if not channel.guild:
            return False
        return await self._dispatch(channel.guild, "on_guild_channel_create", channel)

    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> bool:
        """Dispatch a guild-channel update event to its modules."""
        guild = before.guild or after.guild
        if not guild:
            return False
        return await self._dispatch(guild, "on_guild_channel_update", before, after)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Dispatch a guild-channel deletion event to its modules."""
        if not channel.guild:
            return False
        return await self._dispatch(channel.guild, "on_guild_channel_delete", channel)

    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> bool:
        """Dispatch a guild-role update event to its modules."""
        return await self._dispatch(before.guild, "on_guild_role_update", before, after)

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        """Dispatch a guild-role deletion event to its modules."""
        return await self._dispatch(role.guild, "on_guild_role_delete", role)

    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> bool:
        """Dispatch a member update event to its guild's modules."""
        return await self._dispatch(before.guild, "on_member_update", before, after)

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool:
        """Dispatch a raw member-removal event when its guild is cached."""
        guild = self.client.get_guild(payload.guild_id)
        if guild is None:
            return False
        return await self._dispatch(guild, "on_raw_member_remove", payload)

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Dispatch a raw message-deletion event when its guild is cached."""
        guild = self.client.get_guild(payload.guild_id)
        if guild is None:
            return False
        return await self._dispatch(guild, "on_raw_message_delete", payload)

    async def on_raw_thread_delete(self, payload: events.RawThreadDeleteEvent) -> bool:
        """Dispatch raw thread deletions to modules that own persistent threads."""
        guild = self.client.get_guild(payload.guild_id)
        if guild is None:
            return False
        return await self._dispatch(guild, "on_raw_thread_delete", payload)

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Dispatch a raw bulk message-deletion event when its guild is cached."""
        guild = self.client.get_guild(payload.guild_id)
        if guild is None:
            return False
        return await self._dispatch(guild, "on_raw_bulk_message_delete", payload)
