"""
Modul für Exceptions, die in HsBot verwendet werden.
"""

from discord import (
    RateLimited, 
    NotFound, 
    Forbidden, 
    HTTPException, 
    DiscordException, 
    ClientException, 
    LoginFailure, 
    ConnectionClosed, 
    PrivilegedIntentsRequired, 
    DiscordServerError,
    InteractionResponded
)

__all__ = [
    "RateLimited",
    "NotFound",
    "Forbidden",
    "HTTPException",
    "DiscordException",
    "ClientException",
    "LoginFailure",
    "ConnectionClosed",
    "PrivilegedIntentsRequired",
    "DiscordServerError",
    "InteractionResponded"
]