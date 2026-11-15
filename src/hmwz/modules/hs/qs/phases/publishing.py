"""Phase threads and the messages published inside them."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import discord

from hmwz.ui.threads import create_thread, edit_thread
from hmwz.utils.loaders import fetch_thread

from ..models import BaseReport, MemberSignup, Phase
from .embeds import participants_embed, phase_embed, phase_title
from .views import PhaseView

if TYPE_CHECKING:
    from ..module import QsModule


async def ensure_thread(
    module: QsModule, channel: discord.TextChannel, phase: Phase, timezone: str
) -> discord.Thread:
    """Reuse the saved phase thread, renaming or unarchiving it, or create one."""
    title = phase_title(module.guild, phase, timezone)
    if phase.thread_id is not None:
        candidate = await fetch_thread(module.guild, phase.thread_id)
        if isinstance(candidate, discord.Thread) and candidate.parent_id == channel.id:
            if candidate.archived or candidate.name != title:
                candidate = await edit_thread(candidate, name=title, archived=False)
            return candidate
    thread = await create_thread(
        channel,
        name=title,
        type=discord.ChannelType.public_thread,
        auto_archive_duration=10080,
    )
    if not await module.qs.save_thread(
        module.guild.id, channel.id, phase.index, thread.id, None
    ):
        raise RuntimeError("Failed to save Qs thread.")
    return thread


async def publish_phase(
    module: QsModule,
    channel: discord.TextChannel,
    phase: Phase,
    timezone: str,
    *,
    reports: tuple[BaseReport, ...],
    signups: Mapping[int, tuple[MemberSignup, ...]],
    signup_changed: bool,
    bases_changed: bool,
) -> bool:
    """Patch the phase thread's report and participant messages as needed."""
    guild_id = module.guild.id
    thread = await ensure_thread(module, channel, phase, timezone)
    recreated = phase.thread_id != thread.id
    if bases_changed or recreated:
        message = await module.publisher.message(
            thread,
            phase.message_id,
            embeds=[phase_embed(module.guild, phase, reports)],
            view=PhaseView(module, channel.id, phase),
        )
        if not await module.qs.save_thread(
            guild_id, channel.id, phase.index, thread.id, message.id
        ):
            return False
    if signup_changed or recreated:
        participants = await module.publisher.message(
            thread,
            phase.members_message_id if phase.thread_id == thread.id else None,
            embeds=[participants_embed(module.guild, phase, signups[phase.index])],
        )
        if not await module.qs.save_members_message(
            guild_id, channel.id, phase.index, participants.id
        ):
            return False
    return True
