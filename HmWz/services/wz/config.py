from dataclasses import dataclass
import logging
from discord import Guild
from typing import Optional

from ..database import Database
from ..base import Base
from ...types import id

class WzConfig(Base):
    """
    Service für die Verwaltung der Konfigurationen von WZ in der Datenbank. 
    Diese Klasse bietet Methoden zum Abrufen, Hinzufügen/Aktualisieren und Entfernen von WZ-Konfigurationen für Server (Guilds) in der Datenbank.
    """

    def __init__(self, database: Database):
        super().__init__(database)
        self.logger = logging.getLogger(__name__)

    @dataclass(frozen=True)
    class Data:
        guild: Guild
        channel_id: Optional[id]
        score_mod_lvl: bool
        matchmaker: bool

    type Record = Optional[Data]

    @property
    def table(self):
        return  f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            Guild INTEGER PRIMARY KEY,
            ChannelID INTEGER,
            ScoreModLvl BOOLEAN DEFAULT 0,
            Matchmaker BOOLEAN DEFAULT 0,
            FOREIGN KEY (Guild) REFERENCES Servers(Guild)
        ) WITHOUT ROWID"""

    async def get(self, *, guild: Guild) -> Record:
        """
        Ruft die WZ-Konfiguration für einen bestimmten Server (Guild) aus der Datenbank ab.

        :param guild: Das Guild-Objekt, für das die Konfiguration abgerufen werden soll.
        :type guild: Guild
        :return: Ein Record-Objekt mit den Konfigurationsdaten oder None, wenn keine Konfiguration gefunden wurde oder ein Fehler aufgetreten ist.
        :rtype: Optional[WzConfig.Data]
        """
        try:
            query = f"""
            SELECT 
                ChannelID, 
                ScoreModLvl, 
                Matchmaker 
            FROM 
                {self.table_name} 
            WHERE 
                Guild = ?
            """
            row = await self.database.fetch_one(query, (guild.id,))
            
            if not row:
                return None
            
            self.logger.info(f"{self.log_prefix(guild)} WZ config retrieved.")
            return self.Data(
                guild=guild,
                channel_id=row["ChannelID"],
                score_mod_lvl=bool(row["ScoreModLvl"]),
                matchmaker=bool(row["Matchmaker"])
            )
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to get WZ config: {e}")
            return None

    async def upsert(self, *, guild: Guild, channel_id: Optional[id] = None, score_mod_lvl: Optional[bool] = None, matchmaker: Optional[bool] = None) -> bool:
        """
        Fügt eine neue WZ-Konfiguration für einen Server (Guild) hinzu oder aktualisiert eine vorhandene Konfiguration in der Datenbank.

        :param guild: Das Guild-Objekt, für das die Konfiguration hinzugefügt oder aktualisiert werden soll.
        :type guild: Guild
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
                cols.append("ChannelID")
                vals.append(channel_id)
            if score_mod_lvl is not None:
                cols.append("ScoreModLvl")
                vals.append(int(score_mod_lvl))
            if matchmaker is not None:
                cols.append("Matchmaker")
                vals.append(int(matchmaker))

            if not cols:
                return False

            columns = "Guild, " + ", ".join(cols)
            placeholders = ", ".join(["?"] * (1 + len(cols)))
            update_clause = ", ".join([f"{c}=excluded.{c}" for c in cols])
            
            query = f"""
                INSERT INTO {self.table_name} ({columns}) 
                VALUES ({placeholders}) 
                ON CONFLICT(Guild) DO UPDATE SET {update_clause}
            """
            params = [guild.id] + vals
            
            await self.database.execute(query, tuple(params))
            self.logger.info(f"{self.log_prefix(guild)} WZ config upserted.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to upsert WZ config: {e}")
            return False

    async def remove(self, *, guild: Guild) -> bool:
        """
        Entfernt die WZ-Konfiguration für einen Server (Guild) aus der Datenbank.

        :param guild: Das Guild-Objekt, für das die Konfiguration entfernt werden soll.
        :type guild: Guild
        :return: True, wenn die Konfiguration erfolgreich entfernt wurde, andernfalls False.
        :rtype: bool
        """
        try:
            query = f"DELETE FROM {self.table_name} WHERE Guild = ?"
            await self.database.execute(query, (guild.id,))
            self.logger.info(f"{self.log_prefix(guild)} WZ config removed.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to remove WZ config: {e}")
            return False