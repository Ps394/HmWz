from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Optional
from discord import Guild, TextChannel, Message

from ...types import fetch_channel, fetch_message, DiscordChannel, DiscordMessage, Id
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

    @property
    def table(self) -> str:
        """
        Gibt die SQL-Definition für die Tabelle zurück, die die Registrierungskanäle und -nachrichten speichert.
        
        :return: Die SQL-Definition der Tabelle als String.
        :rtype: str
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            Guild INTEGER PRIMARY KEY,
            Channel INTEGER,
            Message INTEGER,
            Title TEXT,
            Description TEXT,
            Link TEXT,
        FOREIGN KEY (Guild) REFERENCES Servers(Guild)
        )WITHOUT ROWID;
        """    

    @dataclass(frozen=True)
    class Data:
        guild: Guild
        channel: Id
        message: Optional[Id]
        title: Optional[str]
        description: Optional[str]
        link: Optional[str]

        @property
        def is_valid(self) -> bool:
            return isinstance(self.channel, TextChannel) and isinstance(self.message, Message)
        
        @property
        def is_configured(self) -> bool:
            return isinstance(self.channel, TextChannel)
        
        @property
        def has_message(self) -> bool:
            return isinstance(self.message, Message)
        
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
                Channel, 
                Message, 
                Title, 
                Description, 
                Link 
            FROM 
                {self.table_name} 
            WHERE 
                Guild = ?
            """
            params = (guild.id,)
            record = await self.database.fetch_one(query, params)
            
            if not record:
                return None

            channel = await fetch_channel(guild=guild, channel_id=record["Channel"])

            if isinstance(channel, TextChannel):
                message = await fetch_message(channel=channel, message_id=record["Message"])
            else:
                message = channel

            return self.Data(
                guild=guild,
                channel=channel,
                message=message,
                title=record["Title"],
                description=record["Description"],
                link=record["Link"]
            )
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to get WZ registration: {e}")
            return None
        
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
            self.logger.debug(f"{self.log_prefix(guild)} Set up WZ registration channel {channel}.")
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
            self.logger.debug(f"{self.log_prefix(guild)} Set up WZ registration message with title and description.")
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
            self.logger.debug(f"{self.log_prefix(guild)} Set up WZ registration title {title}.")
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
            self.logger.debug(f"{self.log_prefix(guild)} Set up WZ registration description.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to setup WZ registration description: {e}")
            return False

    async def setup_registration(self, *, guild: Guild, message: Optional[Id], title: Optional[str] = None, description: Optional[str] = None, link: Optional[str] = None) -> bool:
        """
        Richtet die Registrierungsmeldung für die angegebene Guild ein oder aktualisiert sie, wenn bereits eine Meldung existiert.
        Es können optional ein Titel, eine Beschreibung und ein Link für die Meldung festgelegt werden.

        :param guild: Das Guild-Objekt, für das die Registrierungsmeldung eingerichtet werden soll.
        :type guild: discord.Guild
        :param message: Die ID der Discord-Nachricht, die als Registrierungsmeldung festgelegt werden soll. Kann None sein, wenn keine Nachricht festgelegt werden soll.
        :type message: Optional[int]
        :param title: Der Titel der Registrierungsmeldung. Kann None sein, wenn kein Titel festgelegt werden soll.
        :type title: Optional[str]
        :param description: Die Beschreibung der Registrierungsmeldung. Kann None sein, wenn keine Beschreibung festgelegt werden soll.
        :type description: Optional[str]
        :param link: Der Link der Registrierungsmeldung. Kann None sein, wenn kein Link festgelegt werden soll.
        :type link: Optional[str]
        """
        try:
            updates = ["Message = ?"]
            params = [message]

            if title:
                updates.append("Title = ?")
                params.append(title[:255]) 
            if description:
                updates.append("Description = ?")
                params.append(description[:4095])
            if link:
                updates.append("Link = ?")
                params.append(link)

            query = f"UPDATE {self.table_name} SET {', '.join(updates)} WHERE Guild = ?"
            params.append(guild.id)

            await self.database.execute(query, tuple(params))
            self.logger.debug(f"{self.log_prefix(guild)} Set up WZ registration for message {message}.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to setup WZ registration: {e}")
            return False
  
    async def remove(self, *, guild: Guild) -> bool:
        """
        Entfernt die Registrierungskanal- und -nachrichteninformationen für die angegebene Guild aus der Datenbank.
        :param guild: Das Guild-Objekt, für das die Registrierungskanal- und -nachrichteninformationen entfernt werden sollen.
        :type guild: discord.Guild
        :return: Ein boolescher Wert, der angibt, ob die Entfernung erfolgreich war
        :rtype: bool
        """
        try:
            query = f"DELETE FROM {self.table_name} WHERE Guild = ?"
            params = (guild.id,)
            await self.database.execute(query, params)
            self.logger.debug(f"{self.log_prefix(guild)} Removed WZ registration.")
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to remove WZ registration: {e}")
            return False