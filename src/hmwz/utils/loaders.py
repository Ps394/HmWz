from __future__ import annotations

import asyncio
import logging

import discord

from hmwz.exceptions import Forbidden, HTTPException, NotFound, RateLimited
from hmwz.utils.interactions import log_guild

_DELAY = 0.1
_logger = logging.getLogger(__name__)


async def fetch_channel(
    guild: discord.Guild, channel_id: int, attempts: int = 3
) -> discord.TextChannel | None:
    """Fetch a text channel from cache or Discord, returning None if unavailable."""
    channel = guild.get_channel_or_thread(channel_id)
    if isinstance(channel, discord.TextChannel):
        _logger.debug(
            "Channel %s (%s) for guild %s found in cache: %s",
            channel.name,
            channel_id,
            log_guild(guild),
            channel,
        )
        return channel

    for _attempt in range(attempts):
        try:
            fetched_channel = await guild.fetch_channel(channel_id)
            if isinstance(fetched_channel, discord.TextChannel):
                _logger.debug(
                    "Fetched channel %s (%s) for guild %s: %s",
                    fetched_channel.name,
                    channel_id,
                    log_guild(guild),
                    fetched_channel,
                )
                return fetched_channel
            raise TypeError(
                f"Channel {channel_id} for guild {log_guild(guild)} is not a TextChannel."
            )
        except RateLimited as error:
            await asyncio.sleep(error.retry_after)
        except Forbidden:
            _logger.warning(
                "Unknown channel (%s) for guild %s; permission denied!",
                channel_id,
                log_guild(guild),
            )
            return None
        except NotFound:
            _logger.warning(
                "Unknown channel (%s) for guild %s; unable to find it!",
                channel_id,
                log_guild(guild),
            )
            return None
        except HTTPException as error:
            _logger.warning(
                "HTTP exception occurred while fetching channel (%s) for guild %s: %s",
                channel_id,
                log_guild(guild),
                error,
            )

    await asyncio.sleep(_DELAY)
    return None


async def fetch_message(
    channel: discord.TextChannel, message_id: int, attempts: int = 3
) -> discord.Message | None:
    """Fetch a message from Discord, returning None if it is unavailable."""
    for _attempt in range(attempts):
        try:
            message = await channel.fetch_message(message_id)
            if isinstance(message, discord.Message):
                _logger.debug(
                    "Fetched message %s in channel %s (%s) for guild %s: %s",
                    message_id,
                    channel.name,
                    channel.id,
                    log_guild(channel.guild),
                    message,
                )
                return message
        except RateLimited as error:
            await asyncio.sleep(error.retry_after)
        except NotFound:
            _logger.warning(
                "Message %s in channel %s (%s) for guild %s unable to find!",
                message_id,
                channel.name,
                channel.id,
                log_guild(channel.guild),
            )
            return None
        except Forbidden:
            _logger.warning(
                "Message %s in channel %s (%s) for guild %s permission denied!",
                message_id,
                channel.name,
                channel.id,
                log_guild(channel.guild),
            )
            return None
        except HTTPException as error:
            _logger.warning(
                "HTTP exception occurred while fetching message %s in channel %s (%s) for guild %s: %s",
                message_id,
                channel.name,
                channel.id,
                log_guild(channel.guild),
                error,
            )
    await asyncio.sleep(_DELAY)
    return None


async def fetch_member(
    guild: discord.Guild, member_id: int, attempts: int = 3
) -> discord.Member | None:
    """Fetch a guild member from cache or Discord, returning None if unavailable."""
    member = guild.get_member(member_id)
    if isinstance(member, discord.Member):
        _logger.debug(
            "Member %s / %s (%s) for guild %s found in cache: %s",
            member.name,
            member.display_name,
            member_id,
            log_guild(guild),
            member,
        )
        return member

    for _attempt in range(attempts):
        try:
            member = await guild.fetch_member(member_id)
            if isinstance(member, discord.Member):
                _logger.debug(
                    "Fetched member %s / %s (%s) for guild %s: %s",
                    member.name,
                    member.display_name,
                    member_id,
                    log_guild(guild),
                    member,
                )
                return member
        except RateLimited as error:
            await asyncio.sleep(error.retry_after)
        except NotFound:
            _logger.warning(
                "Unknown member (%s) for guild %s; unable to find it!",
                member_id,
                log_guild(guild),
            )
            return None
        except Forbidden:
            _logger.warning(
                "Unknown member (%s) for guild %s; permission denied!",
                member_id,
                log_guild(guild),
            )
            return None
        except HTTPException as error:
            _logger.warning(
                "HTTP exception occurred while fetching member %s for guild %s: %s",
                member_id,
                log_guild(guild),
                error,
            )
            
    await asyncio.sleep(_DELAY)
    return None


async def fetch_role(guild: discord.Guild, role_id: int) -> discord.Role | None:
    """Fetch a guild role from cache or Discord, returning None if unavailable."""
    role = guild.get_role(role_id)
    if isinstance(role, discord.Role):
        _logger.debug(
            "Role %s for guild %s found in cache: %s",
            role_id,
            log_guild(guild),
            role,
        )
        return role

    try:
        roles = await guild.fetch_roles()
        for fetched_role in roles:
            if fetched_role.id == role_id:
                _logger.debug(
                    "Fetched role %s for guild %s: %s",
                    role_id,
                    log_guild(guild),
                    fetched_role,
                )
                return fetched_role
    except Exception as error:
        _logger.warning(
            "Failed to fetch role %s for guild %s: %s",
            role_id,
            log_guild(guild),
            error,
        )
        return None
    await asyncio.sleep(_DELAY)
    return None
