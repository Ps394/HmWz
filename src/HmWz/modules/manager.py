from __future__ import annotations

import asyncio
import logging

import discord

from hmwz import events

from .instance import Module, Modules, ModuleType
from .registry import REGISTRY

_logger = logging.getLogger(__name__)


class Manager:
    """Verwaltet Module pro Guild und verteilt Events guild-spezifisch."""

    def __init__(self, client):
        """Erstellt einen Modulmanager fuer einen Discord-Client."""
        self.client = client
        self._modules_by_guild: dict[int, list[Module]] = {}

    async def get_modules(self, guild: discord.Guild) -> Modules:
        """Liefert alle Modulinstanzen fuer eine Guild.

        Falls noch keine Instanzen existieren, werden sie aus der Registry
        erzeugt und zwischengespeichert.
        """
        if guild.id not in self._modules_by_guild:
            modules: list[Module] = []
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
        """Liefert genau eine Modulinstanz eines bestimmten Typs."""
        modules = await self.get_modules(guild)
        for module in modules:
            if isinstance(module, module_type):
                return module
        raise LookupError(
            f"Module of type {module_type} not found for guild {guild.id}."
        )

    async def startup(self) -> None:
        """Initialisiert alle Module fuer alle verbundenen Guilds."""
        await asyncio.gather(*(self.init_guild(guild) for guild in self.client.guilds))
        _logger.info("Module manager startup complete.")

    async def init_guild(self, guild: discord.Guild) -> None:
        """Fuehrt Erst-Sync und Ensure fuer alle Module einer Guild aus."""
        modules = await self.get_modules(guild)
        for module in modules:
            try:
                await module.sync(startup=True)
                await module.ensure()
            except Exception as e:
                _logger.exception(
                    f"{guild.name} ({guild.id}) - Failed to initialize module {module.__class__.__name__}: {e}"
                )

    async def sync(self, guild: discord.Guild, startup: bool = False) -> bool:
        """Synchronisiert alle Module einer Guild und fuehrt anschliessend ensure aus."""
        modules = await self.get_modules(guild)
        status = True
        for module in modules:
            try:
                await module.sync(startup=startup)
                await module.ensure()
            except Exception as e:
                _logger.exception(
                    f"{guild.name} ({guild.id}) - Failed to sync module {module.__class__.__name__}: {e}"
                )
                status = False
        return status

    async def _dispatch(self, guild: discord.Guild, method_name: str, *args) -> bool:
        """Ruft einen benannten Event-Handler auf allen Guild-Modulen auf."""
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
        """Verarbeitet Guild-Join Ereignisse fuer alle Module."""
        self._modules_by_guild.pop(guild.id, None)
        return await self._dispatch(guild, "on_guild_join", guild)

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Verarbeitet Guild-Remove Ereignisse fuer alle Module."""
        status = await self._dispatch(guild, "on_guild_remove", guild)
        self._modules_by_guild.pop(guild.id, None)
        return status

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> bool:
        """Leitet Kanal-Erstellungsevents an Guild-Module weiter."""
        if not channel.guild:
            return False
        return await self._dispatch(channel.guild, "on_guild_channel_create", channel)

    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> bool:
        """Leitet Kanal-Updateevents an Guild-Module weiter."""
        guild = before.guild or after.guild
        if not guild:
            return False
        return await self._dispatch(guild, "on_guild_channel_update", before, after)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Leitet Kanal-Loeschevents an Guild-Module weiter."""
        if not channel.guild:
            return False
        return await self._dispatch(channel.guild, "on_guild_channel_delete", channel)

    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> bool:
        """Leitet Rollen-Updateevents an Guild-Module weiter."""
        return await self._dispatch(before.guild, "on_guild_role_update", before, after)

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        """Leitet Rollen-Loeschevents an Guild-Module weiter."""
        return await self._dispatch(role.guild, "on_guild_role_delete", role)

    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> bool:
        """Leitet Member-Updateevents an Guild-Module weiter."""
        return await self._dispatch(before.guild, "on_member_update", before, after)

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool:
        """Leitet Raw-Member-Removeevents an die passende Guild weiter."""
        guild = self.client.get_guild(payload.guild_id)
        if guild is None:
            return False
        return await self._dispatch(guild, "on_raw_member_remove", payload)

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Leitet Raw-Message-Deleteevents an die passende Guild weiter."""
        guild = self.client.get_guild(payload.guild_id)
        if guild is None:
            return False
        return await self._dispatch(guild, "on_raw_message_delete", payload)

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Leitet Raw-Bulk-Message-Deleteevents an die passende Guild weiter."""
        guild = self.client.get_guild(payload.guild_id)
        if guild is None:
            return False
        return await self._dispatch(guild, "on_raw_bulk_message_delete", payload)
