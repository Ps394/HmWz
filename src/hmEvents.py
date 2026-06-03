"""
Modul für Events, die in HsBot verwendet werden.
"""

from discord import (
    RawMessageDeleteEvent,
    RawMessageUpdateEvent,
    RawMemberRemoveEvent,
    RawThreadDeleteEvent,
    RawThreadUpdateEvent,
    RawReactionActionEvent,
    RawReactionClearEvent
)

__all__ = [
    "RawMessageDeleteEvent",
    "RawMessageUpdateEvent",
    "RawMemberRemoveEvent",
    "RawThreadDeleteEvent",
    "RawThreadUpdateEvent",
    "RawReactionActionEvent",
    "RawReactionClearEvent"
]
