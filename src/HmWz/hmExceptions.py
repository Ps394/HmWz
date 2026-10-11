"""
Modul für Exceptions, die in HsBot verwendet werden.
"""

from discord import (
    ClientException,
    ConnectionClosed,
    DiscordException,
    DiscordServerError,
    Forbidden,
    HTTPException,
    InteractionResponded,
    LoginFailure,
    NotFound,
    PrivilegedIntentsRequired,
    RateLimited,
)

__all__ = [
    "ClientException",
    "ConnectionClosed",
    "DiscordException",
    "DiscordServerError",
    "Forbidden",
    "HTTPException",
    "InteractionResponded",
    "LoginFailure",
    "NotFound",
    "PrivilegedIntentsRequired",
    "RateLimited",
]
