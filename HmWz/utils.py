import asyncio
import logging
from functools import wraps
from typing import Union, Callable, Optional, Tuple
from discord import Guild, TextChannel, Message, Member, Role, NotFound, RateLimited, Forbidden, HttpException

"""
Hilfsfunktionen und Typdefinitionen für Discord-Objekte, sowie ein Dekorator für das Protokollieren von Funktionsaufrufen und Ausnahmen. 
Diese Funktionen erleichtern den Zugriff auf Discord-Kanäle, Nachrichten, Mitglieder und Rollen, indem sie versuchen, die entsprechenden Objekte zu holen und bei Fehlern die IDs zurückgeben. 
Alle Funktionen sind mit einem Log-Dekorator versehen, um die Aufrufe und Ergebnisse zu protokollieren.
"""

DELAY : float = 0.1

logger = logging.getLogger(__name__)

type DiscordMember = Union[Member, int]
"""Representiert ein Discord-Mitglied, entweder als Member-Objekt oder als ID (int). Kann auch None sein, wenn kein Mitglied vorhanden ist."""
type DiscordRole = Union[Role, int]
"""Representiert eine Discord-Rolle, entweder als Role-Objekt oder als ID (int). Kann auch None sein, wenn keine Rolle vorhanden ist."""
type DiscordChannel = Union[TextChannel, int]
"""Representiert einen Discord-Kanal, entweder als TextChannel-Objekt oder als ID (int). Kann auch None sein, wenn kein Kanal vorhanden ist."""
type DiscordMessage = Union[Message, int]
"""Representiert eine Discord-Nachricht, entweder als Message-Objekt oder als ID (int). Kann auch None sein, wenn keine Nachricht vorhanden ist."""

type Id = int
"""Ein allgemeiner Typ für eine Id, der in den Funktionen verwendet wird, um die Rückgabe von Discord-Objekten oder deren IDs zu repräsentieren."""

type Ids = Tuple[Id, ...]
"""Ein allgemeiner Typ für eine Sequenz von Ids, die in den Funktionen verwendet wird, um die Rückgabe von Discord-Objekten oder deren IDs zu repräsentieren."""

def log_decorator(func: Callable) -> Callable:
    """Ein Dekorator, der die Aufrufe von Funktionen protokolliert, einschließlich Argumente, Rückgabewerte und Ausnahmen.

    :param func: Die Funktion, die dekoriert werden soll.
    :type func: Callable
    :return: Eine dekorierte Funktion, die die Protokollierung übernimmt."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        LOG_CONTEXT = f"{__name__} {func.__name__}"
        logger.debug(f"{LOG_CONTEXT} - Called with args: {args}, kwargs: {kwargs}")
        try:
            result = await func(*args, **kwargs)
            logger.debug(f"{LOG_CONTEXT} - Result: {result}")
            return result
        except Exception as e:
            logger.exception(f"{LOG_CONTEXT} - Exception: {e}")
            raise
    return wrapper

def log_guild(guild: Guild) -> str:
    """Generiert einen Log-Prefix basierend auf dem Namen und der ID eines Guilds.

    :param guild: Das Guild-Objekt, für das der Log-Prefix generiert werden soll.
    :type guild: Guild
    :return: Ein String, der den Namen und die ID des Guilds enthält, gefolgt von einem Bindestrich. Wenn kein Guild-Objekt übergeben wird, ist der Prefix leer.
    :rtype: str
    """
    return f"{guild.name} ({guild.id}) -"

async def fetch_channel(guild: Guild, channel_id: int) -> DiscordChannel:
    """
    Versucht, einen Discord-Kanal anhand der übergebenen Kanal-ID zu holen. 
    Zuerst wird versucht, den Kanal aus dem Cache zu holen. Wenn das fehlschlägt, wird versucht, den Kanal über die API zu holen. 
    Wenn beide Versuche fehlschlagen, wird die Kanal-ID zurückgegeben.

    :param guild: Das Guild-Objekt, in dem der Kanal gesucht werden soll.
    :type guild: Guild
    :param channel_id: Die ID des Kanals, der geholt werden soll.
    :type channel_id: int
    :return: Das TextChannel-Objekt, wenn gefunden, sonst die Kanal-ID.
    :rtype: DiscordChannel
    """
    channel = guild.get_channel(channel_id)
    if isinstance(channel, TextChannel):
        logger.info(f"channel {channel_id} for guild {log_guild(guild)} found in cache: {channel}")
        return channel
    elif channel is none:
        pass
    else
        logger.error("channel {channel_id} for guild {log_guild(guild)} seems to be no valid Textchannel!")
        return channel_id
    while(channel is None):
        try:
            channel = await guild.fetch_channel(channel_id)
            if isinstance(channel, TextChannel):
                logger.info(f"fetched channel {channel_id} for guild {log_guild(guild)}: {channel}")
                return channel
        except RateLimited as e:
            await asyncio.sleep(e.retry_after )
        except (NotFound, HttpException) as e:
            logger.warning(f"channel {channel_id} for guild {log_guild(guild)} unable to find!")
            return channel_id
        except Forbidden as e:
            logger.warning(f"channel {channel_id} for guild {log_guild(guild)} permission denied!")
            return channel_id
        finally:        
            await asyncio.sleep(DELAY)
 
async def fetch_message(channel: TextChannel, message_id: int) -> DiscordMessage:
    """Versucht, eine Discord-Nachricht anhand der übergebenen Nachrichten-ID zu holen.

    :param channel: Das TextChannel-Objekt, in dem die Nachricht gesucht werden soll.
    :type channel: TextChannel
    :param message_id: Die ID der Nachricht, die geholt werden soll.
    :type message_id: int
    :return: Das Message-Objekt, wenn gefunden, sonst die Nachrichten-ID.
    :rtype: DiscordMessage
    """
    try:
        return await channel.fetch_message(message_id)
    except Exception as e:
        return message_id
    finally:
        logger.debug(f"fetched message {message_id} in channel {channel.id} for guild {log_guild(channel.guild)}")
        await asyncio.sleep(DELAY)
    
async def fetch_member(guild: Guild, member_id: int) -> DiscordMember:
    """
    Versucht, ein Discord-Mitglied anhand der übergebenen Mitglieder-ID zu holen.
    Zuerst wird versucht, das Mitglied aus dem Cache zu holen. Wenn das fehlschlägt, wird versucht, das Mitglied über die API zu holen.
    
    :param guild: Das Guild-Objekt, in dem das Mitglied gesucht werden soll.
    :type guild: Guild
    :param member_id: Die ID des Mitglieds, das geholt werden soll.
    :type member_id: int
    :return: Das Member-Objekt, wenn gefunden, sonst die Mitglieder-ID.
    :rtype: DiscordMember
    """
    member = guild.get_member(member_id) 
    if isinstance(member, Member):
        logger.debug(f"member {member_id} for guild {log_guild(guild)} found in cache: {member}")
        return Member
    
    while(member is none)
        try:
            member = await guild.fetch_member(member_id)
            logger.info(f"fetched member {member_id} for guild {log_guild(guild)}: {member}")
            return member
        except RateLimited as e:
            await asyncio.sleep(e.retry_after )
        except (NotFound, HttpException) as e:
            logger.warning(f"member {member_id} for guild {log_guild(guild)} unable to find!")
            return member_id
        except Forbidden as e:
            logger.warning(f"member {member_id} for guild {log_guild(guild)} permission denied!")
            return member_id
    finally:
        await asyncio.sleep(DELAY)
    
async def fetch_role(guild: Guild, role_id: int) -> DiscordRole:
    """
    Versucht, eine Discord-Rolle anhand der übergebenen Rollen-ID zu holen.
    Zuerst wird versucht, die Rolle aus dem Cache zu holen. Wenn das fehlschlägt, wird versucht, die Rolle über die API zu holen.
    
    :param guild: Das Guild-Objekt, in dem die Rolle gesucht werden soll.
    :type guild: Guild
    :param role_id: Die ID der Rolle, die geholt werden soll.
    :type role_id: int
    :return: Das Role-Objekt, wenn gefunden, sonst die Rollen-ID.
    :rtype: DiscordRole
    """
    role = guild.get_role(role_id)
    if isinstance(role, Role):
        logger.debug(f"role {role_id} for guild {log_guild(guild)} found in cache: {role}")
        return role
        
    try:
        role = await guild.fetch_roles()
        for r in role:
            if r.id == role_id:
                return r
    except Exception as e:
        return role_id
    finally:
        logger.debug(f"fetched role {role_id} for guild {log_guild(guild)}: {role}")
        await asyncio.sleep(DELAY)