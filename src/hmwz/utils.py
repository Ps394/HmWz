"""
Hilfsfunktionen und Typdefinitionen für Discord-Objekte, sowie ein Dekorator für das Protokollieren von Funktionsaufrufen und Ausnahmen.
Diese Funktionen erleichtern den Zugriff auf Discord-Kanäle, Nachrichten, Mitglieder und Rollen, indem sie versuchen, die entsprechenden Objekte zu holen und bei Fehlern die IDs zurückgeben.
Alle Funktionen sind mit einem Log-Dekorator versehen, um die Aufrufe und Ergebnisse zu protokollieren.
"""

from __future__ import annotations

import asyncio
import logging
import typing
from functools import wraps

import discord

from hmwz.exceptions import Forbidden, HTTPException, NotFound, RateLimited

_DELAY: float = 0.1

__all__ = [
    "fetch_channel",
    "fetch_member",
    "fetch_message",
    "fetch_role",
    "log_decorator",
    "log_guild",
]

_logger = logging.getLogger(__name__)


def log_decorator(func: typing.Callable) -> typing.Callable:
    """Ein Dekorator, der die Aufrufe von Funktionen protokolliert, einschließlich Argumente, Rückgabewerte und Ausnahmen.

    :param func: Die Funktion, die dekoriert werden soll.
    :type func: typing.Callable
    :return: Eine dekorierte Funktion, die die Protokollierung übernimmt."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        LOG_CONTEXT = f"{__name__} {func.__name__}"
        _logger.debug(f"{LOG_CONTEXT} - Called with args: {args}, kwargs: {kwargs}")
        try:
            result = await func(*args, **kwargs)
            _logger.debug(f"{LOG_CONTEXT} - Result: {result}")
            return result
        except Exception as e:
            _logger.exception(f"{LOG_CONTEXT} - Exception: {e}")
            raise

    return wrapper


def log_guild(guild: discord.Guild) -> str:
    """Generiert einen Log-Prefix basierend auf dem Namen und der ID eines Guilds.

    :param guild: Das Guild-Objekt, für das der Log-Prefix generiert werden soll.
    :type guild: discord.Guild
    :return: Ein String, der den Namen und die ID des Guilds enthält, gefolgt von einem Bindestrich. Wenn kein Guild-Objekt übergeben wird, ist der Prefix leer.
    :rtype: str
    """
    return f"{guild.name} ({guild.id}) =>"


async def fetch_channel(
    guild: discord.Guild, channel_id: int, attempts: int = 3
) -> discord.TextChannel | None:
    """
    Versucht, einen Discord-Kanal anhand der übergebenen Kanal-ID zu holen.
    Zuerst wird versucht, den Kanal aus dem Cache zu holen. Wenn das fehlschlägt, wird versucht, den Kanal über die API zu holen.
    Wenn beide Versuche fehlschlagen, wird die Kanal-ID zurückgegeben.

    :param guild: Das Guild-Objekt, in dem der Kanal gesucht werden soll.
    :type guild: discord.Guild
    :param channel_id: Die ID des Kanals, der geholt werden soll.
    :type channel_id: int
    :return: Das TextChannel-Objekt, wenn gefunden, sonst die Kanal-ID.
    :rtype: typing.Optional[discord.TextChannel]
    """
    channel = guild.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        _logger.debug(
            f"channel {channel_id} for guild {log_guild(guild)} found in cache: {channel}"
        )
        return channel

    for attempt in range(attempts):
        try:
            fetched_channel = await guild.fetch_channel(channel_id)
            if isinstance(fetched_channel, discord.TextChannel):
                _logger.debug(
                    f"fetched channel {channel_id} for guild {log_guild(guild)}: {fetched_channel}"
                )
                return fetched_channel
            else:
                raise TypeError(
                    f"Channel {channel_id} for guild {log_guild(guild)} is not a TextChannel."
                )
        except RateLimited as e:
            await asyncio.sleep(e.retry_after)
        except (NotFound, HTTPException):
            _logger.warning(
                f"channel {channel_id} for guild {log_guild(guild)} unable to find!"
            )
            return None
        except Forbidden:
            _logger.warning(
                f"channel {channel_id} for guild {log_guild(guild)} permission denied!"
            )
            return None
    await asyncio.sleep(_DELAY)
    return None


async def fetch_message(
    channel: discord.TextChannel, message_id: int, attempts: int = 3
) -> discord.Message | None:
    """Versucht, eine Discord-Nachricht anhand der übergebenen Nachrichten-ID zu holen.

    :param channel: Das TextChannel-Objekt, in dem die Nachricht gesucht werden soll.
    :type channel: discord.TextChannel
    :param message_id: Die ID der Nachricht, die geholt werden soll.
    :type message_id: int
    :return: Das Message-Objekt, wenn gefunden, sonst die Nachrichten-ID.
    :rtype: typing.Optional[discord.Message]
    """

    for attempt in range(attempts):
        try:
            message = await channel.fetch_message(message_id)
            if isinstance(message, discord.Message):
                _logger.debug(
                    f"fetched message {message_id} in channel {channel.id} for guild {log_guild(channel.guild)}: {message}"
                )
                return message
        except RateLimited as e:
            await asyncio.sleep(e.retry_after)
        except (NotFound, HTTPException):
            _logger.warning(
                f"message {message_id} in channel {channel.id} for guild {log_guild(channel.guild)} unable to find!"
            )
            return None
        except Forbidden:
            _logger.warning(
                f"message {message_id} in channel {channel.id} for guild {log_guild(channel.guild)} permission denied!"
            )
            return None
    await asyncio.sleep(_DELAY)
    return None


async def fetch_member(
    guild: discord.Guild, member_id: int, attempts: int = 3
) -> discord.Member | None:
    """
    Versucht, ein Discord-Mitglied anhand der übergebenen Mitglieder-ID zu holen.
    Zuerst wird versucht, das Mitglied aus dem Cache zu holen. Wenn das fehlschlägt, wird versucht, das Mitglied über die API zu holen.

    :param guild: Das Guild-Objekt, in dem das Mitglied gesucht werden soll.
    :type guild: discord.Guild
    :param member_id: Die ID des Mitglieds, das geholt werden soll.
    :type member_id: int
    :return: Das Member-Objekt, wenn gefunden, sonst die Mitglieder-ID.
    :rtype: typing.Optional[discord.Member]
    """
    member = guild.get_member(member_id)
    if isinstance(member, discord.Member):
        _logger.debug(
            f"member {member_id} for guild {log_guild(guild)} found in cache: {member}"
        )
        return member

    for attempt in range(attempts):
        try:
            member = await guild.fetch_member(member_id)
            if isinstance(member, discord.Member):
                _logger.debug(
                    f"fetched member {member_id} for guild {log_guild(guild)}: {member}"
                )
                return member
        except RateLimited as e:
            await asyncio.sleep(e.retry_after)
        except (NotFound, HTTPException):
            _logger.warning(
                f"member {member_id} for guild {log_guild(guild)} unable to find!"
            )
            return None
        except Forbidden:
            _logger.warning(
                f"member {member_id} for guild {log_guild(guild)} permission denied!"
            )
            return None
    await asyncio.sleep(_DELAY)
    return None


async def fetch_role(guild: discord.Guild, role_id: int) -> discord.Role | None:
    """
    Versucht, eine Discord-Rolle anhand der übergebenen Rollen-ID zu holen.
    Zuerst wird versucht, die Rolle aus dem Cache zu holen. Wenn das fehlschlägt, wird versucht, die Rolle über die API zu holen.

    :param guild: Das Guild-Objekt, in dem die Rolle gesucht werden soll.
    :type guild: discord.Guild
    :param role_id: Die ID der Rolle, die geholt werden soll.
    :type role_id: int
    :return: Das Role-Objekt, wenn gefunden, sonst die Rollen-ID.
    :rtype: typing.Optional[discord.Role]
    """
    role = guild.get_role(role_id)
    if isinstance(role, discord.Role):
        _logger.debug(
            f"role {role_id} for guild {log_guild(guild)} found in cache: {role}"
        )
        return role

    try:
        roles = await guild.fetch_roles()
        for fetched_role in roles:
            if fetched_role.id == role_id:
                _logger.debug(
                    f"fetched role {role_id} for guild {log_guild(guild)}: {fetched_role}"
                )
                return fetched_role
    except Exception as e:
        _logger.warning(
            f"failed to fetch role {role_id} for guild {log_guild(guild)}: {e}"
        )
        return None
    await asyncio.sleep(_DELAY)
    return None
