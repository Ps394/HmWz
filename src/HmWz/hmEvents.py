"""
Modul für Events, die in HsBot verwendet werden.
"""

from discord import (
    RawBulkMessageDeleteEvent,
    RawMemberRemoveEvent,
    RawMessageDeleteEvent,
    RawMessageUpdateEvent,
    RawReactionActionEvent,
    RawReactionClearEvent,
    RawThreadDeleteEvent,
    RawThreadUpdateEvent,
)

__all__ = [
    "RawBulkMessageDeleteEvent",
    "RawMemberRemoveEvent",
    "RawMessageDeleteEvent",
    "RawMessageUpdateEvent",
    "RawReactionActionEvent",
    "RawReactionClearEvent",
    "RawThreadDeleteEvent",
    "RawThreadUpdateEvent",
]
