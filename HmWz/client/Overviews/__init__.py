"""
Dieses Modul enthält die Definition des Managers für Übersichten, der für die Verwaltung aller Übersichtsinstanzen in diesem Bot verantwortlich ist.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Type
from discord import RawMessageDeleteEvent, Guild, Client
from .registry import REGISTRY
from .instance import Instance, Instances, InstanceType

from . import registration

__all__ = ["Manager", "Instance", "Instances", "Registration"]

logger = logging.getLogger(__name__)

class Manager:
    """
    Manager für alle Übersichten, die in diesem Bot verwendet werden.
    """
    
    def __init__(self, client: Client):
        """Initialisiert den Manager mit dem Discord-Client."""
        self.client = client
        """Cache für Übersicht-Instanzen pro Gilde. Schlüssel ist die Guild-ID, Wert ist eine Liste von Übersicht-Instanzen."""
        self.instances_cache = {}
        """Cache für Übersicht-Instanzen pro Gilde."""

    async def get_instance(self, guild: Guild, instance_type: InstanceType) -> Instance:
        """
        Gibt die Übersicht-Instanz für die angegebene Gilde und den angegebenen Instanztyp zurück.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :param instance_type: Der Typ der Übersicht-Instanz, die zurückgegeben werden soll.
        :type instance_type: InstanceType
        :return: Die Übersicht-Instanz.
        :rtype: Instance
        :raise: Exception: Wenn keine Übersicht-Instanz des angegebenen Typs gefunden wird.
        """
        instances = await self.get_instances(guild)
        for instance in instances:
            if isinstance(instance, instance_type):
                return instance
        raise Exception(f"Instance of type {instance_type} not found for guild {guild.id}.")
 
    async def get_instances(self, guild: Guild) -> Instances:
        """
        Gibt die Übersicht-Instanzen für die angegebene Gilde zurück. Wenn die Instanzen noch nicht im Cache sind, werden sie erstellt und im Cache gespeichert.
        
        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :return: Die Übersicht-Instanzen.
        :rtype: Instances
        """
        if guild.id not in self.instances_cache:
            instances = []
            for factory in REGISTRY:
                try:
                    instance = await factory.create(guild, self.client)
                    instances.append(instance)
                except Exception as e:
                    logger.exception(f"Failed to create overview instance for guild {guild.id}: {e}")
            self.instances_cache[guild.id] = instances
        return self.instances_cache[guild.id]
        
    async def startup(self):
        """
        Startet den Manager und initialisiert alle Gilden.
        Aufrufen bei On_ready Event des Clients.

        :return: None
        """
        tasks = [self.init_guild(g) for g in self.client.guilds]
        await asyncio.gather(*tasks)
        logger.info("Manager startup complete.")

    async def init_guild(self, guild: Guild):
        """
        Initialisiert die Übersicht-Instanzen für die angegebene Gilde, synchronisiert sie und stellt sie sicher.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :return: None
        :rtype: None
        """
        instances = await self.get_instances(guild)
        for instance in instances:
            try:
                await instance.sync()
                await instance.ensure()
                logger.debug(f"Overview instance {instance.__class__.__name__} for guild {guild.id} synced successfully.")
            except Exception as e:
                logger.exception(f"Failed to sync overview instance for guild {guild.id}: {e}")

    async def sync(self, guild: Guild) -> bool:
        """
        Synchronisiert die Übersicht-Instanzen für die angegebene Gilde.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :return: True, wenn die Synchronisierung erfolgreich war, sonst False.
        :rtype: bool
        """
        instances = await self.get_instances(guild)
        status = True
        for instance in instances:
            try:
                await instance.sync()
            except Exception as e:
                logger.exception(f"Failed to sync overview instance for guild {guild.id}: {e}")
                status = False
        return status

    async def ensure(self, guild: Guild) -> bool:
        """
        Stellt sicher, dass die Übersicht-Instanzen für die angegebene Gilde korrekt sind.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :return: True, wenn die Sicherstellung erfolgreich war, sonst False.
        :rtype: bool
        """
        instances = await self.get_instances(guild)
        status = True
        for instance in instances:
            try:
                await instance.ensure()
            except Exception as e:
                logger.exception(f"Failed to ensure overview instance for guild {guild.id}: {e}")
                status = False
        return status
    
    async def send(self, guild: Guild) -> bool:
        """
        Sendet die Übersicht-Instanzen für die angegebene Gilde.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :return: True, wenn das Senden erfolgreich war, sonst False.
        :rtype: bool
        """
        instances = await self.get_instances(guild)
        status = True
        for instance in instances:
            try:
                await instance.send()
            except Exception as e:
                logger.exception(f"Failed to send overview instance for guild {guild.id}: {e}")
                status = False
        return status
    
    async def update(self, guild: Guild) -> bool:
        """
        Aktualisiert die Übersicht-Instanzen für die angegebene Gilde.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :return: True, wenn die Aktualisierung erfolgreich war, sonst False.
        :rtype: bool
        """
        instances = await self.get_instances(guild)
        status = True
        for instance in instances:
            try:
                await instance.update()
            except Exception as e:
                logger.exception(f"Failed to update overview instance for guild {guild.id}: {e}")
                status = False
        return status
    
    async def clean(self, guild: Guild) -> bool:
        """
        Bereinigt die Übersicht-Instanzen für die angegebene Gilde.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :return: True, wenn die Bereinigung erfolgreich war, sonst False.
        :rtype: bool
        """
        instances = await self.get_instances(guild)
        status = True
        for instance in instances:
            try:
                await instance.clean()
            except Exception as e:
                logger.exception(f"Failed to clean overview instance for guild {guild.id}: {e}")
                status = False
        return status
    
    async def delete(self, guild: Guild) -> bool:
        """
        Löscht die Übersicht-Instanzen für die angegebene Gilde.

        :param guild: Die Discord-Gilde, für die die Übersicht erstellt wird.
        :type guild: discord.Guild
        :return: True, wenn das Löschen erfolgreich war, sonst False.
        :rtype: bool
        """
        instances = await self.get_instances(guild)
        status = True
        for instance in instances:
            try:
                await instance.delete()
            except Exception as e:
                logger.exception(f"Failed to delete overview instance for guild {guild.id}: {e}")
                status = False
        return status
    
    async def on_message_delete(self, payload: RawMessageDeleteEvent) -> bool:
        """
        Reagiert auf das Löschen einer Nachricht, indem es die Übersicht-Instanzen der betroffenen Gilde benachrichtigt.

        :param payload: Das Ereignis, das das Löschen der Nachricht beschreibt.
        :type payload: discord.RawMessageDeleteEvent
        """
        guild = self.client.get_guild(payload.guild_id)
        if not guild:
            return False
        
        instances = await self.get_instances(guild)
        status = True
        for instance in instances:
            try:
                await instance.on_message_delete(payload)
            except Exception as e:
                logger.exception(f"Failed to handle message delete for overview instance in guild {guild.id}: {e}")
                status = False
        return status