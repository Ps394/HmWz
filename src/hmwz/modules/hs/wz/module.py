"""Independent guild-scoped WZ channel and role management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from hmwz import sqlite_db
from hmwz.modules.module import Module
from hmwz.modules.registry import register
from hmwz.utils.interactions import log_guild

from .repositories import ChannelRepository, RoleRepository

if TYPE_CHECKING:
    from hmwz.client import Client

_logger = logging.getLogger(__name__)


@register
class WzModule(Module):
    """Manage WZ cleanup channels and roles independently of registrations."""

    module_key = "wz"

    def __init__(self, guild: discord.Guild, client: Client) -> None:
        super().__init__(guild, client)
        if not isinstance(self.database, sqlite_db.Database):
            raise RuntimeError("WZ module requires a database.")
        self._database = self.database
        self.channels = ChannelRepository(self.database)
        self.roles = RoleRepository(self.database)
        self._schema_ready = False

    async def sync(self, startup: bool = False) -> bool:
        """Create and migrate only the module's own tables."""
        if self._schema_ready:
            return True
        for repository in (self.channels, self.roles):
            if not await self._database.execute(repository.table):
                _logger.error(
                    "%s Failed to create WZ table %s.",
                    log_guild(self.guild),
                    repository.table_name,
                )
                return False
            if not await repository.migrate_schema():
                return False
        self._schema_ready = True
        _logger.info("%s WZ module schema ready.", log_guild(self.guild))
        return True

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        """Initialize WZ settings when joining this guild."""
        return guild.id == self.guild.id and await self.sync(startup=True)

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Remove only this module's settings when leaving the guild."""
        if guild.id != self.guild.id:
            return False
        channels_removed = await self.channels.remove(guild=guild)
        roles_removed = await self.roles.remove(guild=guild)
        return channels_removed and roles_removed

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Remove a deleted channel from WZ settings."""
        if channel.guild.id != self.guild.id:
            return False
        return await self.channels.remove(guild=self.guild, channel_id=channel.id)

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        """Remove a deleted role from WZ settings."""
        if role.guild.id != self.guild.id:
            return False
        return await self.roles.remove(guild=self.guild, role=role.id)
