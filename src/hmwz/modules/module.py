"""Basisklasse fuer Module.

Die Klasse liefert no-op Standardimplementierungen fuer den kompletten
Modul-Lebenszyklus. Konkrete Module koennen nur die benoetigten Methoden
ueberschreiben.
"""

from __future__ import annotations

import discord

from hmwz import events, sqlite_db, client

class Module:
    """Basisklasse fuer Module."""

    def __init__(self, guild: discord.Guild, client : client.Client):
        """Initialisiert ein Modul."""
        self.guild = guild
        self.client = client
        self.database: sqlite_db.Database | None = getattr(client, "_database", None)

    @classmethod
    async def create(cls, guild: discord.Guild, client):
        """Factory-Methode fuer den Modulmanager."""
        return cls(guild, client)
