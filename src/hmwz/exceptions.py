"""
Discord exception types exposed for consistent bot error handling.
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
