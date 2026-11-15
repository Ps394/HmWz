"""Phase-start notifications in the corresponding phase thread."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_message
from hmwz.ui.threads import edit_thread
from hmwz.utils.interactions import log_guild

from ..maintenance import existing_thread
from ..models import Phase

if TYPE_CHECKING:
    from ..module import QsModule

_logger = logging.getLogger(__name__)


class PhasePings:
    """Notify the Qs role when a phase starts."""

    def __init__(self, module: QsModule) -> None:
        self.module = module

    async def ping_participants(self, channel_id: int, phase: Phase) -> bool:
        """Notify the Qs role of phase signups, or consume a disabled ping."""
        module = self.module
        guild = module.guild
        configuration = await module.qs.get(guild.id, channel_id)
        if configuration is None or configuration.state != "active":
            _logger.warning(
                "%s Participant ping has no active Qs event.", log_guild(guild)
            )
            return False
        if not configuration.ping_settings.phase_start:
            return True
        if not await module.qs.members(guild.id, channel_id, phase.index):
            return True
        role = guild.get_role(configuration.role_id)
        if role is None:
            _logger.warning(
                "%s Qs participant ping role no longer exists.", log_guild(guild)
            )
            return False
        thread = await existing_thread(module, channel_id, phase)
        if thread is None:
            _logger.warning(
                "%s Missing phase thread for participant notification.",
                log_guild(guild),
            )
            return False
        if not role.mentionable and (
            guild.me is None or not thread.permissions_for(guild.me).mention_everyone
        ):
            _logger.warning(
                "%s Bot cannot mention the configured Qs role in phase thread %s.",
                log_guild(guild),
                thread.id,
            )
            return False
        if thread.archived:
            thread = await edit_thread(thread, archived=False)
        content = t(
            guild,
            "qs.admin.ping_phase_start",
            phase=phase.index,
            role=role.mention,
        )
        return (
            await send_message(
                thread,
                content=content,
                allowed_mentions=discord.AllowedMentions(
                    roles=[role],
                    users=False,
                    everyone=False,
                ),
            )
            is not None
        )
