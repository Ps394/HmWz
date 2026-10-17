from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class WzConfigurationRepository(sqlite_db.Base):
    """
    Repository für die Verwaltung der WZ-Konfiguration in der Datenbank.
    """

    table_name = "Configuration"

    def __init__(self, database: sqlite_db.Database):
        super().__init__(database)

    @dataclass(frozen=True)
    class _Data:
        guild: int
        channel_id: int | None
        score_mod_lvl: bool
        matchmaker: bool

    type Record = _Data | None

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Channel: str = "ChannelID"
        ScoreModLvl: str = "ScoreModLvl"
        Matchmaker: str = "Matchmaker"

    @property
    def table(self):
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER PRIMARY KEY,
            {self.TableCols.Channel} INTEGER,
            {self.TableCols.ScoreModLvl} BOOLEAN DEFAULT 0,
            {self.TableCols.Matchmaker} BOOLEAN DEFAULT 0,
            FOREIGN KEY ({self.TableCols.Guild}) REFERENCES Servers(Guild)
        ) WITHOUT ROWID"""

    async def get(self, *, guild: discord.Guild) -> Record:
        """
        Ruft die WZ-Konfiguration für einen bestimmten Server (Guild) aus der Datenbank ab.

        :param guild: Das Guild-Objekt, für das die Konfiguration abgerufen werden soll.
        :type guild: discord.Guild
        :return: Ein Record-Objekt mit den Konfigurationsdaten oder None, wenn keine Konfiguration gefunden wurde oder ein Fehler aufgetreten ist.
        :rtype: Optional[WzConfig.Data]
        """

        try:
            query = f"""
            SELECT 
                {self.TableCols.Channel}, 
                {self.TableCols.ScoreModLvl}, 
                {self.TableCols.Matchmaker} 
            FROM 
                {self.table_name} 
            WHERE 
                {self.TableCols.Guild} = ?
            """
            row = await self.database.fetch_one(query, (guild.id,))

            if not row:
                return None

            _logger.info(f"{self.log_prefix(guild)} WZ config retrieved.")
            return self._Data(
                guild=guild.id,
                channel_id=row[self.TableCols.Channel],
                score_mod_lvl=bool(row[self.TableCols.ScoreModLvl]),
                matchmaker=bool(row[self.TableCols.Matchmaker]),
            )
        except Exception as e:
            _logger.exception(f"{self.log_prefix(guild)} Failed to get WZ config: {e}")
            return None

    async def upsert(
        self,
        *,
        guild: discord.Guild,
        channel_id: int | None = None,
        score_mod_lvl: bool | None = None,
        matchmaker: bool | None = None,
    ) -> bool:
        """
        Fügt eine neue WZ-Konfiguration für einen Server (Guild) hinzu oder aktualisiert eine vorhandene Konfiguration in der Datenbank.

        :param guild: Das Guild-Objekt, für das die Konfiguration hinzugefügt oder aktualisiert werden soll.
        :type guild: discord.Guild
        :param channel_id: Die ID des Channels, der für WZ verwendet wird. Standardmäßig None.
        :type channel_id: Optional[int]
        :param score_mod_lvl: Gibt an, ob die Score-Mod-Level-Funktion aktiviert ist. Standardmäßig None.
        :type score_mod_lvl: Optional[bool]
        :param matchmaker: Gibt an, ob die Matchmaker-Funktion aktiviert ist. Standardmäßig None.
        :type matchmaker: Optional[bool]
        :return: True, wenn die Konfiguration erfolgreich hinzugefügt oder aktualisiert wurde, andernfalls False.
        :rtype: bool
        """
        try:
            cols = []
            vals = []

            if channel_id is not None:
                cols.append(self.TableCols.Channel)
                vals.append(channel_id)
            if score_mod_lvl is not None:
                cols.append(self.TableCols.ScoreModLvl)
                vals.append(int(score_mod_lvl))
            if matchmaker is not None:
                cols.append(self.TableCols.Matchmaker)
                vals.append(int(matchmaker))

            if not cols:
                return False

            columns = f"{self.TableCols.Guild}, " + ", ".join(cols)
            placeholders = ", ".join(["?"] * (1 + len(cols)))
            update_clause = ", ".join([f"{c}=excluded.{c}" for c in cols])

            query = f"""
                INSERT INTO {self.table_name} ({columns}) 
                VALUES ({placeholders}) 
                ON CONFLICT({self.TableCols.Guild}) DO UPDATE SET {update_clause}
            """
            params = [guild.id] + vals

            if not await self.database.execute(query, tuple(params)):
                return False
            _logger.info(f"{self.log_prefix(guild)} WZ config upserted.")
            return True
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to upsert WZ config: {e}"
            )
            return False

    async def remove(self, *, guild: discord.Guild) -> bool:
        """
        Entfernt die WZ-Konfiguration für einen Server (Guild) aus der Datenbank.

        :param guild: Das Guild-Objekt, für das die Konfiguration entfernt werden soll.
        :type guild: discord.Guild
        :return: True, wenn die Konfiguration erfolgreich entfernt wurde, andernfalls False.
        :rtype: bool
        """
        try:
            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            executed = await self.database.execute(query, (guild.id,))
            if executed:
                _logger.info(f"{self.log_prefix(guild)} WZ config removed.")
            return executed
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to remove WZ config: {e}"
            )
            return False
