"""
Shared emoji constants used by bot commands and views.
"""

import re
from typing import Final

import discord

from .uploader import EmojiUploader

SUCCESS: Final[str] = "✅"
ERROR: Final[str] = "❌"
WARNING: Final[str] = "⚠️"
INFO: Final[str] = "ℹ️"
SETUP: Final[str] = "⚙️"
RESET: Final[str] = "♻️"
SAVE: Final[str] = "💾"
DELETE: Final[str] = "🗑️"

# Registration (existing compatibility)
REGISTER: Final[str] = "➕"
REREGISTER: Final[str] = "🔄"
UNREGISTER: Final[str] = "➖"
PERMA_REGISTRATION: Final[str] = "🔒"
NORMAL_REGISTRATION: Final[str] = "🔓"
GAMEPAD: Final[str] = "🎮"


# Navigation / UI hints
NEXT: Final[str] = "➡️"
PREVIOUS: Final[str] = "⬅️"
UP: Final[str] = "⬆️"
DOWN: Final[str] = "⬇️"
HOME: Final[str] = "🏠"
BACK: Final[str] = "↩️"
FORWARD: Final[str] = "↪️"
MENU: Final[str] = "📋"

CREDIT: Final[str] = "🪙"
CRYSTAL: Final[str] = "💎"

_FALLBACKS: Final[dict[str, str]] = {
    "success": SUCCESS,
    "error": ERROR,
    "warning": WARNING,
    "info": INFO,
    "setup": SETUP,
    "reset": RESET,
    "save": SAVE,
    "delete": DELETE,
    "register": REGISTER,
    "reregister": REREGISTER,
    "unregister": UNREGISTER,
    "perma_registration": PERMA_REGISTRATION,
    "normal_registration": NORMAL_REGISTRATION,
    "gamepad": GAMEPAD,
    "next": NEXT,
    "previous": PREVIOUS,
    "up": UP,
    "down": DOWN,
    "home": HOME,
    "back": BACK,
    "forward": FORWARD,
    "menu": MENU,
    "credit": CREDIT,
    "cristall": CRYSTAL,
}
_UNICODE_NAMES: Final[dict[str, str]] = {
    value: name for name, value in _FALLBACKS.items()
}
_UNICODE_PATTERN: Final[re.Pattern[str]] = re.compile(
    "|".join(
        re.escape(value) for value in sorted(_UNICODE_NAMES, key=len, reverse=True)
    )
)


def get(
    name: str,
    context: discord.Client | discord.Interaction | discord.Guild | None = None,
) -> str:
    """Resolve a named application emoji, falling back to the shared Unicode icon.

    Unknown names without an uploaded image raise ``KeyError``.
    ``crystal`` aliases the bundled ``cristall``.
    Guild lookup is isolated here because discord.py exposes no public client
    accessor on a Guild.
    """
    name = name.lower()
    if name == "crystal":
        name = "cristall"
    client: discord.Client | None
    if isinstance(context, discord.Interaction):
        client = context.client
    elif isinstance(context, discord.Guild):
        client = context._state._get_client()
    else:
        client = context
    uploader = getattr(client, "emoji_uploader", None)
    if isinstance(uploader, EmojiUploader) and name in uploader.mentions:
        return uploader.mentions[name]
    return _FALLBACKS[name]


def render(
    text: str,
    context: discord.Client | discord.Interaction | discord.Guild | None = None,
) -> str:
    """Replace shared Unicode icons in message text with available custom emojis.

    Use ``get`` for a component's emoji property; custom mentions do not render
    inside button labels, modal titles, or text-input labels.
    """
    return _UNICODE_PATTERN.sub(
        lambda match: get(_UNICODE_NAMES[match.group()], context), text
    )
