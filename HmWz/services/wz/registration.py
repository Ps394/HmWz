from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Optional
from discord import Guild

from ...types import  Id
from ..database import Database
from ..base import Base

__all__ = [
    "Registration"
]

class WzRegistration(Base):
    """
    Service für die Registrierungskanal und -nachrichten einer Guild im WZ-Modul. 
    Verwaltet die Erstellung, Aktualisierung und Löschung von Registrierungskanälen und -nachrichten sowie die zugehörigen Informationen wie Titel, Beschreibung und Link.
    """
    
    def __init__(self, database: Database):
        super().__init__(database)
        self.logger = logging.getLogger(__name__)

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Channel: str = "Channel"
        Message: str = "Message"
        Title: str = "Title"
        Description: str = "Description"

    @property
    def table(self) -> str:
        """
        Gibt die SQL-Definition für die Tabelle zurück, die die Registrierungskanäle und -nachrichten speichert.
        
        :return: Die SQL-Definition der Tabelle als String.
        :rtype: str
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER PRIMARY KEY,
            {self.TableCols.Channel} INTEGER,
            {self.TableCols.Message} INTEGER,
            {self.TableCols.Title} TEXT,
            {self.TableCols.Description} TEXT,
        FOREIGN KEY ({self.TableCols.Guild}) REFERENCES Servers(Guild)
        )WITHOUT ROWID;
        """    

    @dataclass(frozen=True)
    class Data:
        guild: Guild
        channel: Optional[Id]
        message: Optional[Id]
        title: Optional[str]
        description: Optional[str]

        @property
        def has_channel(self) -> bool:
            return self.channel is not None
        
        @property
        def has_message(self) -> bool:
            return self.message is not None
        
        @property
        def has_title(self) -> bool:
            return self.title is not None and self.title != ""
        
        @property
        def has_description(self) -> bool:
            return self.description is not None and self.description != ""

    type Record = Optional[Data]
    """
    Der Datentyp für die Registrierungskanal- und -nachrichteninformationen einer Guild im WZ-Modul.
    
    :param guild: Das Guild-Objekt, für das die Informationen gelten.
    :type guild: discord.Guild
    :param channel: Das DiscordChannel-Objekt, das den Registrierungskanal repräsentiert. Kann auch die Kanal-ID als int sein, wenn der Kanal nicht gefunden werden konnte.
    :type channel: DiscordChannel
    :param message: Das DiscordMessage-Objekt, das die Registrierungsmeldung repräsentiert. Kann auch die Nachrichten-ID als int sein, wenn die Nachricht nicht gefunden werden konnte.
    :type message: DiscordMessage
    :param title: Der Titel der Registrierungsmeldung. Kann None sein, wenn kein Titel festgelegt ist.
    :type title: Optional[str]
    :param description: Die Beschreibung der Registrierungsmeldung. Kann None sein, wenn keine Beschreibung festgelegt ist.
    :type description: Optional[str]
    :param link: [Deprecated] Ein optionaler Link, der in der Registrierungsmeldung angezeigt werden kann. Kann None sein, wenn kein Link festgelegt ist.
    :type link: Optional[str]
    """

    async def get(self, *, guild: Guild) -> Record:
        """
        Docstring for get
        
        :param self: Description
        :param guild: Description
        :type guild: discord.Guild
        :return: Description
        :rtype: Record | None
        """
        try:
            query = f"""
            SELECT 
                {self.TableCols.Channel}, 
                {self.TableCols.Message}, 
                {self.TableCols.Title}, 
                {self.TableCols.Description}
            FROM 
                {self.table_name} 
            WHERE 
                {self.TableCols.Guild} = ?
            """
            params = (guild.id,)
            record = await self.database.fetch_one(query, params)
            if not record:
                return None

            return self.Data(
                guild=guild,
                channel=record[self.TableCols.Channel] if record[self.TableCols.Channel] is not None else None,
                message=record[self.TableCols.Message] if record[self.TableCols.Message] is not None else None,
                title=record[self.TableCols.Title],
                description=record[self.TableCols.Description]
            )
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to get WZ registration: {e}")
            return None
        
    async def upsert(self, *, guild: Guild, channel_id: Optional[Id] = None, message_id: Optional[Id] = None, title: Optional[str] = None, description: Optional[str] = None) -> bool:
        """
        Upsert-Methode für die Registrierungskanal- und -nachrichteninformationen einer Guild im WZ-Modul. 
        Fügt eine neue Konfiguration hinzu oder aktualisiert eine vorhandene Konfiguration in der Datenbank.

        :param guild: Das Guild-Objekt, für das die Informationen hinzugefügt oder aktualisiert werden sollen.
        :type guild: discord.Guild
        :param channel_id: Die ID des Discord-Kanals, der als Registrierungskanal festgelegt werden soll. Kann None sein, wenn kein Kanal festgelegt werden soll.
        :type channel_id: Optional[int]
        :param message_id: Die ID der Discord-Nachricht, die als Registrierungsmeldung festgelegt werden soll. Kann None sein, wenn keine Nachricht festgelegt werden soll.
        :type message_id: Optional[int]
        :param title: Der Titel der Registrierungsmeldung. Kann None sein, wenn kein Titel festgelegt werden soll.
        :type title: Optional[str]
        :param description: Die Beschreibung der Registrierungsmeldung. Kann None sein, wenn keine Beschreibung festgelegt werden soll.
        :type description: Optional[str]
        :return: Ein boolescher Wert, der angibt, ob die Upsert-Operation erfolgreich war.
        """

        try:
            cols = []
            vals = []
            
            if channel_id is not None:
                cols.append(self.TableCols.Channel)
                vals.append(channel_id)
            if message_id is not None:
                cols.append(self.TableCols.Message)
                vals.append(message_id)
            if title is not None:
                cols.append(self.TableCols.Title)
                vals.append(title[:255]) 
            if description is not None:
                cols.append(self.TableCols.Description)
                vals.append(description[:4095])

            if not cols:
                return False

            query = f"""
            INSERT INTO {self.table_name} ({self.TableCols.Guild}, {', '.join(cols)}) 
            VALUES (?, {', '.join(['?'] * len(cols))})
            ON CONFLICT({self.TableCols.Guild}) DO UPDATE SET 
            {', '.join([f"{col} = excluded.{col}" for col in cols])}
            """
            await self.database.execute(query, (guild.id, *vals))
            self.logger.info(f"{self.log_prefix(guild)} Upserted WZ registration with channel {channel_id}, message {message_id}, title {title} and description.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to upsert WZ registration: {e}")
            return False
        
    async def setup_channel(self, *, guild: Guild, channel: Id)->bool:
        """
        Richtet den Registrierungskanal für die angegebene Guild ein oder aktualisiert ihn, wenn bereits ein Kanal existiert.

        :param guild: Das Guild-Objekt, für das der Registrierungskanal eingerichtet werden soll.
        :type guild: discord.Guild
        :param channel: Die ID des Discord-Kanals, der als Registrierungskanal festgelegt werden soll.
        :type channel: int
        """
        try:
            query = f"""
            INSERT INTO {self.table_name} (Guild, Channel) VALUES (?, ?)
            ON CONFLICT(Guild) DO UPDATE SET Channel = excluded.Channel
            """
            await self.database.execute(query, (guild.id, channel))
            self.logger.info(f"{self.log_prefix(guild)} Set up WZ registration channel {channel}.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to setup WZ registration channel: {e}")
            return False
    
    async def setup_message(self, *, guild: Guild, title: Optional[str] = None, description: Optional[str] = None)->bool:
        """
        Richtet die Registrierungsmeldung für die angegebene Guild ein oder aktualisiert sie, wenn bereits eine Meldung existiert. 
        Es können optional ein Titel und eine Beschreibung für die Meldung festgelegt werden.

        :param guild: Das Guild-Objekt, für das die Registrierungsmeldung eingerichtet werden soll.
        :type guild: discord.Guild
        :param title: Der Titel der Registrierungsmeldung. Kann None sein, wenn kein Titel festgelegt werden soll.
        :type title: Optional[str]
        :param description: Die Beschreibung der Registrierungsmeldung. Kann None sein, wenn keine Beschreibung festgelegt werden soll.
        :type description: Optional[str]
        """
        try:
            updates = []
            params = []

            if title is not None:
                updates.append("Title = ?")
                params.append(title[:255]) 
            if description is not None:
                updates.append("Description = ?")
                params.append(description[:4095])

            if not updates:
                self.logger.warning(f"{self.log_prefix(guild)} No title or description provided for WZ registration message setup.")
                return False

            query = f"UPDATE {self.table_name} SET {', '.join(updates)} WHERE Guild = ?"
            params.append(guild.id)

            await self.database.execute(query, tuple(params))
            self.logger.info(f"{self.log_prefix(guild)} Set up WZ registration message with title and description.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to setup WZ registration message: {e}")
            return False

    async def setup_title(self, *, guild: Guild, title: Optional[str] = "")->bool:
        """
        Richtet den Titel der Registrierungsmeldung für die angegebene Guild ein oder aktualisiert ihn, wenn bereits eine Meldung existiert.

        :param guild: Das Guild-Objekt, für das der Registrierungstitel eingerichtet werden soll.
        :type guild: discord.Guild
        :param title: Der Titel der Registrierungsmeldung. Kann None sein, wenn kein Titel festgelegt werden soll.
        :type title: Optional[str]
        """
        try:
            query = f"""
            INSERT INTO {self.table_name} (Guild, Title) VALUES (?, ?)
            ON CONFLICT(Guild) DO UPDATE SET Title = excluded.Title
            """
            await self.database.execute(query, (guild.id, title[:255]))
            self.logger.info(f"{self.log_prefix(guild)} Set up WZ registration title {title}.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to setup WZ registration title: {e}")
            return False
        
    async def setup_description(self, *, guild: Guild, description: Optional[str] = "")->bool:
        """
        Richtet die Beschreibung der Registrierungsmeldung für die angegebene Guild ein oder aktualisiert sie, wenn bereits eine Meldung existiert.

        :param guild: Das Guild-Objekt, für das die WZ-Registrierungsbeschreibung eingerichtet werden soll.
        :type guild: discord.Guild
        :param description: Die Beschreibung der Registrierungsmeldung. Kann None sein, wenn keine Beschreibung festgelegt werden soll.
        :type description: Optional[str]
        """
        try:
            query = f"""
            INSERT INTO {self.table_name} (Guild, Description) VALUES (?, ?)
            ON CONFLICT(Guild) DO UPDATE SET Description = excluded.Description
            """
            await self.database.execute(query, (guild.id, description[:4095]))
            self.logger.info(f"{self.log_prefix(guild)} Set up WZ registration description.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to setup WZ registration description: {e}")
            return False

    async def setup_registration(self, *, guild: Guild, message: Optional[Id], title: Optional[str] = None, description: Optional[str] = None) -> bool:
        """
        Richtet die Registrierungsmeldung für die angegebene Guild ein oder aktualisiert sie, wenn bereits eine Meldung existiert.
        Es können optional ein Titel und eine Beschreibung für die Meldung festgelegt werden.

        :param guild: Das Guild-Objekt, für das die Registrierungsmeldung eingerichtet werden soll.
        :type guild: discord.Guild
        :param message: Die ID der Discord-Nachricht, die als Registrierungsmeldung festgelegt werden soll. Kann None sein, wenn keine Nachricht festgelegt werden soll.
        :type message: Optional[int]
        :param title: Der Titel der Registrierungsmeldung. Kann None sein, wenn kein Titel festgelegt werden soll.
        :type title: Optional[str]
        :param description: Die Beschreibung der Registrierungsmeldung. Kann None sein, wenn keine Beschreibung festgelegt werden soll.
        :type description: Optional[str]
        :return: Ein boolescher Wert, der angibt, ob die Einrichtung oder Aktualisierung der Registrierungsmeldung erfolgreich war.
        :rtype: bool
        """
        try:
            state = await self.upsert(guild=guild, message_id=message, title=title, description=description)
            self.logger.info(f"{self.log_prefix(guild)} Set up WZ registration for message {message}.")
            return state
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to setup WZ registration: {e}")
            return False
  
    async def remove(self, *, guild: Guild) -> bool:
        """
        Entfernt die Registrierungskanal- und -nachrichteninformationen für die angegebene Guild aus der Datenbank.
        :param guild: Das Guild-Objekt, für das die Registrierungskanal- und -nachrichteninformationen entfernt werden sollen.
        :type guild: discord.Guild
        :return: Ein boolescher Wert, der angibt, ob die Entfernung erfolgreich war.
        :rtype: bool
        """
        try:
            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params = (guild.id,)
            await self.database.execute(query, params)
            self.logger.debug(f"{self.log_prefix(guild)} Removed WZ registration.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to remove WZ registration: {e}")
            return False