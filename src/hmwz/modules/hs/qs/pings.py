"""Event-wide Qs role pings, such as start, end and goal notifications."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_message
from hmwz.utils.interactions import log_guild

if TYPE_CHECKING:
    from .module import QsModule

_logger = logging.getLogger(__name__)


class QsPings:
    """Mention the configured Qs role in the overview channel."""

    def __init__(self, module: QsModule) -> None:
        self.module = module

    async def ping(
        self, channel_id: int, *, event: str = "manual", phase_index: int | None = None
    ) -> bool:
        """Ping the configured role, or consume a disabled automatic notification."""
        guild = self.module.guild
        configuration = await self.module.qs.get(guild.id, channel_id)
        channel = guild.get_channel(channel_id)
        if (
            configuration is None
            or configuration.state != "active"
            or not isinstance(channel, discord.TextChannel)
        ):
            _logger.warning(
                "%s Qs ping has no configured text channel.", log_guild(guild)
            )
            return False
        if not {
            "start": configuration.ping_settings.start,
            "end": configuration.ping_settings.end,
            "goal": configuration.ping_settings.goal,
        }.get(event, True):
            return True
        role = guild.get_role(configuration.role_id)
        if role is None:
            _logger.warning("%s Qs ping role no longer exists.", log_guild(guild))
            return False
        if not role.mentionable and (
            guild.me is None or not channel.permissions_for(guild.me).mention_everyone
        ):
            _logger.warning(
                "%s Bot cannot mention the configured Qs role.", log_guild(guild)
            )
            return False
        return (
            await send_message(
                channel,
                content=t(
                    guild,
                    "qs.event.ping" if event == "manual" else f"qs.admin.ping_{event}",
                    role=role.mention,
                    phase=phase_index,
                ),
                allowed_mentions=discord.AllowedMentions(
                    roles=[role], users=False, everyone=False
                ),
            )
            is not None
        )
