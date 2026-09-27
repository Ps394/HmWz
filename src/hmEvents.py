"""
Modul für Events, die in HsBot verwendet werden.
"""

from discord import (
    RawMessageDeleteEvent,
    RawBulkMessageDeleteEvent,
    RawMessageUpdateEvent,
    RawMemberRemoveEvent,
    RawThreadDeleteEvent,
    RawThreadUpdateEvent,
    RawReactionActionEvent,
    RawReactionClearEvent
)

__all__ = [
    "RawMessageDeleteEvent",
    "RawBulkMessageDeleteEvent",
    "RawMessageUpdateEvent",
    "RawMemberRemoveEvent",
    "RawThreadDeleteEvent",
    "RawThreadUpdateEvent",
    "RawReactionActionEvent",
    "RawReactionClearEvent"
]
