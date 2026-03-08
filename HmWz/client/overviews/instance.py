"""
Modul, das die Definition der Instance-Schnittstelle enthält, die von allen Übersichtsinstanzen implementiert werden muss.
"""
from __future__ import annotations
from typing import Optional, Sequence, Protocol, Type, runtime_checkable
from discord import RawMessageDeleteEvent
import enum

@runtime_checkable
class Instance(Protocol):
    """
    Interface für alle Übersichtsinstanzen, die in diesem Bot verwendet werden.
    """

    async def sync(self, startup: bool = False, sync_data: bool = False, sync_config: bool = False, sync_discord: bool = False) -> bool: 
        """
        Soll die Übersicht synchronisieren, wenn diese eingerichtet ist.

        :param startup: Vollständige Synchronisation beim Startup.
        :param sync_data: Synchronisiert nur Daten (Registrierungen).
        :param sync_config: Synchronisiert nur Konfiguration.
        :param sync_discord: Synchronisiert Discord-Mitglieder mit DB.
        :return: True, wenn die Synchronisierung erfolgreich war, sonst False.
        :rtype: bool
        """
        ...
    async def ensure(self) -> bool: 
        """
        Soll sicherstellen, dass die Übersicht vorhanden ist, wenn diese eingerichtet ist.

        :return: True, wenn die Übersicht erfolgreich sichergestellt wurde, sonst False.
        :rtype: bool
        """
        ...
        
    async def send(self) -> bool: 
        """
        Soll die Übersicht senden, wenn diese eingerichtet ist.
        
        :return: True, wenn die Übersicht erfolgreich gesendet wurde, sonst False.
        :rtype: bool
        """
        ...
    async def update(self) -> bool: 
        """
        Soll die Übersicht aktualisieren, wenn diese eingerichtet ist.

        :return: True, wenn die Übersicht erfolgreich aktualisiert wurde, sonst False.
        :rtype: bool
        """
        ...
    
    async def clean(self)-> bool: 
        """
        Soll den Kanal von nicht Bot-Nachrichten bereinigen, wenn Übersicht eingerichtet ist.

        :return: True, wenn die Übersicht erfolgreich bereinigt wurde, sonst False.
        :rtype: bool
        """
        ...
    async def delete(self) -> bool: 
        """
        Soll die Übersicht löschen, wenn diese eingerichtet ist.

        :return: True, wenn die Übersicht erfolgreich gelöscht wurde, sonst False.
        :rtype: bool
        """
        ...
    async def on_message_delete(self, payload: RawMessageDeleteEvent) -> bool: 
        """
        Soll auf das Löschen einer Nachricht reagieren, wenn die Übersicht eingerichtet ist.

        :param payload: Das Ereignis, das das Löschen der Nachricht beschreibt.
        :type payload: discord.RawMessageDeleteEvent
        :return: True, wenn die Übersicht erfolgreich auf das Löschen reagiert hat, sonst False.
        :rtype: bool
        """
        ...

type Instances = Sequence[Instance]
"""Typalias für eine Sequenz von Übersicht-Instanzen."""

type InstanceType = Type[Instance]
"""Typalias für den Typ einer Übersicht-Instanz."""