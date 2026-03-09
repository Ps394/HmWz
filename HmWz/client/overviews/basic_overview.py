"""
Modul, das die Basisklasse für alle Übersichten enthält, die in diesem Bot verwendet werden.
Diese Klasse implementiert die Instance-Schnittstelle und bietet grundlegende Funktionen und Eigenschaften, die von allen Übersichten gemeinsam genutzt werden können. 
Sie enthält Methoden zum Verwalten von Synchronisierungs-, Arbeits- und Löschstatus sowie Eigenschaften für den Zugriff auf den Client, die Gilde und die Services.
"""
from __future__ import annotations
import asyncio
from typing import Union, Type, Optional
from discord import Embed, Guild, Client, Color, Asset, utils
from .instance import Instance 
from ...services import Services

type BasicOverviewType = Type[BasicOverview]
"""Typalias für den Typ einer Übersichtsklasse, die eine Instanz von BasicOverview zurückgibt."""

class BasicOverview(Instance):
    """
    Basisklasse für alle Übersichten, die in diesem Bot verwendet werden.
    """

    WAIT_INTERVAL : float = 0.5 
    WAIT_INTERVAL_LONG : float = 2.5

    class BotEmbed(Embed):
        def __init__(self, title: str, description: str, color: Color, client_avatar: Optional[Asset] = None):
            super().__init__(title=title, description=description, color=color)
            self.set_footer(text=f"|", icon_url=client_avatar.url if client_avatar else None)
            self.timestamp = utils.utcnow()

    def __init__(self, guild: Guild, services: Services, client: Client):
        """
        Initialisiert die Übersicht mit der Gilde, den Services und dem Client.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :param services: Die Services, die für die Übersicht benötigt werden.
        :type services: Services
        :param client: Der Discord-Client, der für die Übersicht verwendet wird.
        :type client: discord.Client
        """
        self.guild : Guild = guild
        self.services : Services = services
        self.client : Client = client

        self.IS_SYNCING : bool = False
        self.IS_WORKING : bool = False
        self.IS_DELETING : bool = False

    @classmethod
    async def create(cls, guild: Guild, client: Client) -> Instance:
        """
        Erstellt eine Instanz der Übersicht für die angegebene Gilde und den Client.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :param client: Der Discord-Client, der für die Übersicht verwendet wird.
        :type client: discord.Client
        :return: Eine Instanz der Übersicht.
        :rtype: Instance
        :raise: TypeError: Wenn die Client-Services nicht existiert.
        """
        services = getattr(client, "services", None)

        if services is None:
            raise TypeError(f"Client services not found for guild {guild.id}.") 

        return cls(guild, services, client)
    
    async def sleep(self, seconds: float = WAIT_INTERVAL_LONG) -> Union[None, ValueError]:
        """
        ## sleep(seconds: float)
        verzögert die Ausführung.

        :param seconds: Anzahl der Sekunden, die gewartet werden soll. Standard ist WAIT_INTERVAL_LONG.
        :type seconds: float
        :return: None, wenn die Verzögerung erfolgreich war, oder ValueError, wenn die Sekunden negativ sind.
        :rtype: Union[None, ValueError]
        :raise: ValueError: Wenn seconds negativ ist.
        """
        try:
            if seconds < 0:
                raise ValueError(f"{self.log_context} Seconds must be non-negative.")
            await asyncio.sleep(seconds)
        except ValueError as e:
            raise e

    async def wait_while_syncing(self):
        """
        Wartet, bis die Synchronisierung abgeschlossen ist.
        """
        while self.IS_SYNCING:
            await self.sleep()

    async def wait_while_working(self):
        """
        Wartet, bis die Arbeit abgeschlossen ist.
        """
        while self.IS_WORKING:
            await self.sleep()

    async def wait_while_deleting(self):
        """
        Wartet, bis die Löschung abgeschlossen ist.
        """
        while self.IS_DELETING:
            await self.sleep()

    async def wait_while_busy(self):
        """
        Wartet, bis der Bot beschäftigt ist.
        """
        while self.is_busy:
            await self.sleep()
        
    
    def sync_start(self) -> bool:
        """
        Setzt den Synchronisierungsstatus auf True, um anzuzeigen, dass die Synchronisierung läuft.

        :return: True, wenn die Synchronisierung gestartet wurde, sonst False.
        :rtype: bool
        """
        self.IS_SYNCING = True
        return self.IS_SYNCING
    
    def work_start(self) -> bool:
        """
        Setzt den Arbeitsstatus auf True, um anzuzeigen, dass die Arbeit läuft.

        :return: True, wenn die Arbeit gestartet wurde, sonst False.
        :rtype: bool
        """
        self.IS_WORKING = True
        return self.IS_WORKING  
   
    def delete_start(self) -> bool:
        """
        Setzt den Löschstatus auf True, um anzuzeigen, dass die Löschung läuft.

        :return: True, wenn die Löschung gestartet wurde, sonst False.
        :rtype: bool
        """
        self.IS_DELETING = True
        return self.IS_DELETING

    async def sync_stop(self) -> bool:
        """
        Setzt den Synchronisierungsstatus auf False, um anzuzeigen, dass die Synchronisierung abgeschlossen ist.

        :return: True, wenn die Synchronisierung gestoppt wurde, sonst False.
        :rtype: bool
        """
        await self.sleep(self.WAIT_INTERVAL)
        self.IS_SYNCING = False
        return not self.IS_SYNCING

    async def work_stop(self) -> bool:
        """
        Setzt den Arbeitsstatus auf False, um anzuzeigen, dass die Arbeit abgeschlossen ist.

        :return: True, wenn die Arbeit gestoppt wurde, sonst False.
        :rtype: bool
        """
        await self.sleep(self.WAIT_INTERVAL)
        self.IS_WORKING = False
        return not self.IS_WORKING

    async def delete_stop(self) -> bool:
        """
        Setzt den Löschstatus auf False, um anzuzeigen, dass die Löschung abgeschlossen ist.

        :return: True, wenn die Löschung gestoppt wurde, sonst False.
        :rtype: bool
        """
        await self.sleep(self.WAIT_INTERVAL)
        self.IS_DELETING = False
        return not self.IS_DELETING

    @property
    def is_busy(self) -> bool:
        """
        Gibt zurück, ob der Bot beschäftigt ist.

        :return: True, wenn der Bot beschäftigt ist, sonst False.
        :rtype: bool
        """
        return self.IS_SYNCING or self.IS_WORKING or self.IS_DELETING

    @property
    def client_color(self) -> Color:
        """
        Gibt die Farbe des Clients zurück, basierend auf der höchsten Rolle des Clients in der Gilde.

        :return: Die Farbe des Clients.
        :rtype: discord.Color
        """
        return max(self.guild.get_member(self.client.user.id).roles, key=lambda r: r.position).color

    @property
    def client_name(self) -> str:
        """
        Gibt den Namen des Clients zurück.

        :return: Der Name des Clients.
        :rtype: str
        """
        return self.client.user.name
    
    @property
    def client_avatar(self) -> Asset:
        """
        Gibt das Avatar des Clients zurück.

        :return: Das Avatar des Clients.
        :rtype: discord.Asset
        """
        return self.guild.icon if self.guild.icon else self.client.user.avatar if self.client.user.avatar else None

    @property
    def log_context(self) -> str:
        """
        Gibt Klassennamen, Gildenname und Gilden-ID zurück, um konsistente Log-Meldungen zu ermöglichen.

        :return: Der Log-Kontext.
        :rtype: str
        """
        return f"{self.guild.name}({self.guild.id}) :"