"""Destroyed-base reports and withdrawals for a phase."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz.i18n import t
from hmwz.ui.messages import (
    defer_interaction,
    send_followup,
    send_interaction_message,
)
from hmwz.utils.interactions import log_guild

from ...repositories.bases import (
    BaseLimitReached,
    DuplicateBaseReport,
    InvalidGameAccount,
)

if TYPE_CHECKING:
    from ...module import QsModule

_logger = logging.getLogger(__name__)


class BaseService:
    """Record and retract destroyed bases, one per linked game account."""

    def __init__(self, module: QsModule) -> None:
        self.module = module

    async def report_base(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        phase_index: int,
        *,
        game_account: str | None,
        member: discord.Member | None = None,
    ) -> None:
        """Record one destroyed base per linked game account across all phases."""
        module = self.module
        await defer_interaction(interaction, thinking=True)
        async with module.publisher.lock(channel_id):
            if member is None:
                if await module.access.authorize(interaction, channel_id) is None:
                    return
                reporter = interaction.user
            else:
                if not await module.access.authorize_moderation(
                    interaction, channel_id
                ):
                    return
                if member.guild.id != module.guild.id:
                    await send_interaction_message(
                        interaction, t(interaction, "qs.event.withdraw_denied")
                    )
                    return
                reporter = member
            phase = await module.access.phase(interaction, channel_id, phase_index)
            if phase is None:
                return
            if phase.starts_at > int(time.time()):
                await send_interaction_message(
                    interaction, t(interaction, "qs.event.phase_not_started")
                )
                return
            try:
                await module.qs.report(
                    module.guild.id,
                    channel_id,
                    phase_index,
                    reporter.id,
                    game_account,
                    reporter.display_name,
                    int(time.time()),
                )
            except BaseLimitReached:
                await send_followup(interaction, t(interaction, "qs.event.base_limit"))
                return
            except InvalidGameAccount:
                await send_followup(
                    interaction, t(interaction, "qs.event.report_account_invalid")
                )
                return
            except DuplicateBaseReport:
                _logger.info(
                    "%s Duplicate Qs game-account report rejected.",
                    log_guild(module.guild),
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.duplicate_report")
                )
                return
            except aiosqlite.IntegrityError as error:
                if error.sqlite_errorcode in (
                    sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
                    sqlite3.SQLITE_CONSTRAINT_UNIQUE,
                ):
                    _logger.info(
                        "%s Duplicate Qs base report rejected.", log_guild(module.guild)
                    )
                    await send_followup(
                        interaction, t(interaction, "qs.event.duplicate_report")
                    )
                    return
                _logger.exception(
                    "%s Failed to save Qs base report.", log_guild(module.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to save Qs base report.", log_guild(module.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            notified = await module.notifications.goals(channel_id)
            update = module.publisher.queue_update(channel_id, phase_index, bases=True)
            signup_updates = tuple(
                module.publisher.queue_update(channel_id, signup_phase)
                for signup_phase in await module.qs.signup_phases(
                    module.guild.id, channel_id, reporter.id, game_account
                )
            )
        refreshed = all(
            await asyncio.gather(
                *(asyncio.shield(task) for task in {update, *signup_updates})
            )
        )
        await send_followup(
            interaction,
            t(interaction, "qs.event.reported")
            + ("" if refreshed else "\n" + t(interaction, "qs.event.refresh_failed"))
            + (
                ""
                if notified
                else "\n" + t(interaction, "qs.admin.notification_failed")
            ),
        )

    async def withdraw_base(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        phase_index: int,
        member_id: int,
        game_account: str | None,
    ) -> None:
        """Retract one account report and preserve once-per-phase ping markers."""
        module = self.module
        await defer_interaction(interaction, thinking=True)
        async with module.publisher.lock(channel_id):
            if (
                await module.access.authorize_withdrawal(
                    interaction, channel_id, member_id
                )
                is None
            ):
                return
            try:
                removed = await module.qs.withdraw_report(
                    module.guild.id,
                    channel_id,
                    phase_index,
                    member_id,
                    game_account,
                )
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to withdraw Qs report.", log_guild(module.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            if not removed:
                await send_followup(
                    interaction, t(interaction, "qs.event.withdraw_missing")
                )
                return
            update = module.publisher.queue_update(channel_id, phase_index, bases=True)
            signup_updates = tuple(
                module.publisher.queue_update(channel_id, signup_phase)
                for signup_phase in await module.qs.signup_phases(
                    module.guild.id, channel_id, member_id, game_account
                )
            )
        refreshed = all(
            await asyncio.gather(
                *(asyncio.shield(task) for task in {update, *signup_updates})
            )
        )
        await send_followup(
            interaction,
            t(interaction, "qs.event.withdrawn")
            + ("" if refreshed else "\n" + t(interaction, "qs.event.refresh_failed")),
        )
