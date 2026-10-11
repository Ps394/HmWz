from __future__ import annotations

import logging
from dataclasses import dataclass

import discord
import sqlLiteDB


class Server(sqlLiteDB.Base):
    """
    Service für die Verwaltung von Servern (Guilds) in der Datenbank.
    Diese Klasse bietet Methoden zum Hinzufügen, Entfernen und Zählen von Servern in der Datenbank."""

    def __init__(self, database: sqlLiteDB.Database):
        super().__init__(database)
        self.logger = logging.getLogger(__name__)

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Name: str = "Name"

    @property
    def table(self) -> str:
        """
        Gibt die SQL-Abfrage zurück, um die Tabelle für die Server zu erstellen. Die Tabelle enthält die Spalten "Guild" (INTEGER PRIMARY KEY) und "Name" (TEXT).

        :return: SQL-Abfrage zum Erstellen der Tabelle.
        :rtype: str
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER PRIMARY KEY,
            {self.TableCols.Name} TEXT
        ) WITHOUT ROWID
        """

    async def add(self, *, guild: discord.Guild) -> bool:
        """
        Fügt einen Server (Guild) zur Datenbank hinzu oder aktualisiert den Namen, wenn der Server bereits existiert.

        :param guild: Das Guild-Objekt, das hinzugefügt oder aktualisiert werden soll.
        :type guild: discord.Guild
        :return: True, wenn der Server erfolgreich hinzugefügt oder aktualisiert wurde, False bei einem Fehler.
        :rtype: bool
        """
        try:
            query = f"""
                INSERT INTO {self.table_name} ({self.TableCols.Guild}, {self.TableCols.Name}) 
                VALUES (?, ?) 
                ON CONFLICT({self.TableCols.Guild}) DO UPDATE SET {self.TableCols.Name} = excluded.{self.TableCols.Name}
            """
            await self.database.execute(query, (guild.id, guild.name))
            self.logger.info(f"{self.log_prefix(guild)} Added/Updated server.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to add/update server: {e}")
            return False

    async def remove(self, *, guild: discord.Guild) -> bool:
        """
        Entfernt einen Server (Guild) aus der Datenbank.

        :param guild: Das Guild-Objekt, das entfernt werden soll.
        :type guild: discord.Guild
        :return: True, wenn der Server erfolgreich entfernt wurde, False bei einem Fehler.
        :rtype: bool
        """
        try:
            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            await self.database.execute(query, (guild.id,))
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to remove server: {e}")
            return False
