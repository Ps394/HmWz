"""Basisklasse fuer Module.

Die Klasse liefert no-op Standardimplementierungen fuer den kompletten
Modul-Lebenszyklus. Konkrete Module koennen nur die benoetigten Methoden
ueberschreiben.
"""

from __future__ import annotations

import discord

from hmwz import events, sqlite_db


class BasicModule:
    """Basisklasse fuer guild-spezifische Module."""

    def __init__(self, guild: discord.Guild, client):
        """Initialisiert ein Modul fuer genau eine Guild."""
        self.guild = guild
        self.client = client
        self.database: sqlite_db.Database | None = getattr(client, "_database", None)

    @classmethod
    async def create(cls, guild: discord.Guild, client):
        """Factory-Methode fuer den Modulmanager."""
        return cls(guild, client)

    async def sync(self, startup: bool = False) -> bool:
        """Synchronisiert Modulzustand mit externen Quellen."""
        return True

    async def ensure(self) -> bool:
        """Stellt benoetigte Ressourcen des Moduls sicher."""
        return True

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        """Reagiert auf Guild-Join des Bots."""
        return True

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Reagiert auf Guild-Remove des Bots."""
        return True

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> bool:
        """Reagiert auf erstellte Kanaele."""
        return True

    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> bool:
        """Reagiert auf Kanal-Aenderungen."""
        return True

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Reagiert auf geloeschte Kanaele."""
        return True

    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> bool:
        """Reagiert auf Rollen-Aenderungen."""
        return True

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        """Reagiert auf geloeschte Rollen."""
        return True

    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> bool:
        """Reagiert auf Member-Updates."""
        return True

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool:
        """Reagiert auf Raw-Member-Remove Events."""
        return True

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Reagiert auf Raw-Message-Delete Events."""
        return True

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Reagiert auf Raw-Bulk-Message-Delete Events (z. B. durch channel.purge)."""
        return True
