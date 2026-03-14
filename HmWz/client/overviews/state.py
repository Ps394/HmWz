from __future__ import annotations
from asyncio import Event
from enum import Enum
from dataclasses import dataclass
from typing import Optional

@dataclass()
class State():
    """
    Repräsentiert den Synchronisierungsstatus einer Overview"""
    on_startup: bool = True
    sync_from_discord: bool = False
    sync_configuration: bool = False
    sync_data: bool = False

    class SyncEvent(Enum):
        """Synchronisierungsereignisse für die Overview"""
        STARTUP = 0x100
        CHANGED_DISCORD = 0x200
        CHANGED_CONFIGURATION = 0x300
        CHANGED_REGISTRATIONS = 0x400
    
    def check(self, event: SyncEvent) -> bool:
        """
        Überprüft, ob ein bestimmtes Synchronisierungsereignis eingetreten ist. 
        Wenn das Ereignis eingetreten ist, wird es zurückgesetzt.
        :param event: Das zu überprüfende Synchronisierungsereignis.
        :type event: SyncEvent
        :return: True, wenn das Ereignis eingetreten ist, sonst False.
        :rtype: bool
        """
        if event == self.SyncEvent.STARTUP and self.on_startup:
            self.reset(self.SyncEvent.STARTUP)
            return True
        elif event == self.SyncEvent.CHANGED_DISCORD and self.sync_from_discord:
            self.reset(self.SyncEvent.CHANGED_DISCORD)
            return True
        elif event == self.SyncEvent.CHANGED_CONFIGURATION and self.sync_configuration:
            self.reset(self.SyncEvent.CHANGED_CONFIGURATION)
            return True
        elif event == self.SyncEvent.CHANGED_REGISTRATIONS and self.sync_data:
            self.reset(self.SyncEvent.CHANGED_REGISTRATIONS)
            return True
        else:
            return False  
    
    def reset(self, event: Optional[SyncEvent] = None):
        """
        Setzt den Status eines bestimmten Synchronisierungsereignisses zurück.
        :param event: Das zu zurücksetzende Synchronisierungsereignis.
        :type event: Optional[SyncEvent]

        """
        if event is None or event == self.SyncEvent.STARTUP:
             self.on_startup = False
             self.sync_from_discord = False
             self.sync_configuration = False
             self.sync_data = False
        elif event == self.SyncEvent.CHANGED_DISCORD:
            self.sync_from_discord = False
        elif event == self.SyncEvent.CHANGED_CONFIGURATION:
            self.sync_configuration = False
        elif event == self.SyncEvent.CHANGED_REGISTRATIONS:
            self.sync_data = False

    def clear(self):
        """
        Setzt alle Synchronisierungsereignisse zurück.
        """
        self.on_startup = False
        self.sync_from_discord = False
        self.sync_configuration = False
        self.sync_data = False
