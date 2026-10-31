"""
Discord event payload types used by the bot.
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
