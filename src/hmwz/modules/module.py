"""Base implementation for guild-scoped modules.

The class provides no-op defaults for the module lifecycle. Concrete modules
can override only the handlers they need.
"""

from __future__ import annotations

import discord

from hmwz import events, sqlite_db, client

class Module:
    """Base class for guild-scoped modules."""

    def __init__(self, guild: discord.Guild, client : client.Client):
        """Initialize a module for a guild and Discord client.

        Args:
            guild: Guild managed by this module instance.
            client: Discord client that owns the module manager.
        """
        self.guild = guild
        self.client = client
        self.database: sqlite_db.Database | None = getattr(client, "_database", None)

    @classmethod
    async def create(cls, guild: discord.Guild, client):
        """Create a module instance for the manager.

        Args:
            guild: Guild managed by the new module instance.
            client: Discord client that owns the module manager.

        Returns:
            The initialized module instance.
        """
        return cls(guild, client)
