"""Phase signup flows; every mutation is merged into one channel update."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz.i18n import t
from hmwz.ui.messages import (
    defer_interaction,
    send_followup,
    send_interaction_response,
)
from hmwz.utils.interactions import log_guild
from hmwz.utils.text import escape_discord_text

from ..accounts import AccountChoice
from .views import SignupConfirmation

if TYPE_CHECKING:
    from ...module import QsModule

_logger = logging.getLogger(__name__)


class SignupService:
    """Join, leave and clean up phase signups."""

    def __init__(self, module: QsModule) -> None:
        self.module = module

    def _refresh_hint(self, interaction: discord.Interaction, refreshed: bool) -> str:
        return "" if refreshed else "\n" + t(interaction, "qs.event.refresh_failed")

    async def _queue_account_updates(
        self,
        channel_id: int,
        phase_index: int,
        member_id: int,
        game_account: str | None,
    ) -> tuple[asyncio.Task[bool], ...]:
        module = self.module
        affected = set(
            await module.qs.signup_phases(
                module.guild.id, channel_id, member_id, game_account
            )
        )
        affected.add(phase_index)
        return tuple(
            module.publisher.queue_update(channel_id, index)
            for index in sorted(affected)
        )

    async def toggle_phase(
        self, interaction: discord.Interaction, channel_id: int, phase_index: int
    ) -> None:
        """Toggle one phase without affecting the member's other phase signups."""
        module = self.module
        await defer_interaction(interaction, thinking=True)
        async with module.publisher.lock(channel_id):
            if await module.access.authorize(interaction, channel_id) is None:
                return
            if await module.access.phase(interaction, channel_id, phase_index) is None:
                return
            try:
                joined = await module.qs.toggle(
                    module.guild.id, channel_id, phase_index, interaction.user.id
                )
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to save Qs signup.", log_guild(module.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            updates = await self._queue_account_updates(
                channel_id, phase_index, interaction.user.id, None
            )
        refreshed = all(
            await asyncio.gather(*(asyncio.shield(task) for task in set(updates)))
        )
        await send_followup(
            interaction,
            t(interaction, "qs.event.joined" if joined else "qs.event.left")
            + self._refresh_hint(interaction, refreshed),
        )

    async def signup_button(
        self, interaction: discord.Interaction, channel_id: int, phase_index: int
    ) -> None:
        """Open account selection for a new or additional phase signup."""
        module = self.module
        async with module.publisher.lock(channel_id):
            if await module.access.authorize(interaction, channel_id) is None:
                return
            try:
                if (
                    await module.access.phase(interaction, channel_id, phase_index)
                    is None
                ):
                    return
                accounts = await module.access.game_accounts_for(interaction.user.id)
                signups = await module.qs.member_signups(
                    module.guild.id, channel_id, phase_index
                )
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to prepare Qs signup.", log_guild(module.guild)
                )
                await send_interaction_response(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
        registered_accounts = {
            signup.game_account.casefold() if signup.game_account is not None else None
            for signup in signups
            if signup.member_id == interaction.user.id
        }
        available_accounts = tuple(
            account
            for account in accounts
            if account.casefold() not in registered_accounts
        )
        main_account_available = None not in registered_accounts
        if not main_account_available and not available_accounts:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.signup_all_registered")
            )
            return
        if not accounts:
            await self.confirm_phase_signup(
                interaction, channel_id, phase_index, game_account=None
            )
            return
        choices: list[AccountChoice] = []
        if main_account_available:
            choices.append(
                AccountChoice(
                    key="main-account",
                    game_account=None,
                    label=interaction.user.display_name,
                )
            )
        choices.extend(
            AccountChoice(key=f"account-{index}", game_account=account, label=account)
            for index, account in enumerate(available_accounts)
        )
        view = SignupConfirmation(
            module,
            channel_id,
            phase_index,
            interaction.user.id,
            tuple(choices),
            t(
                interaction,
                "qs.event.signup_confirmation",
                member=escape_discord_text(interaction.user.display_name),
            ),
        )
        view.message = await send_interaction_response(
            interaction, view.content(), view=view
        )

    async def unregister_phase_button(
        self, interaction: discord.Interaction, channel_id: int, phase_index: int
    ) -> None:
        """Open a selector containing this member's signups for one phase."""
        module = self.module
        async with module.publisher.lock(channel_id):
            if await module.access.authorize(interaction, channel_id) is None:
                return
            try:
                if (
                    await module.access.phase(interaction, channel_id, phase_index)
                    is None
                ):
                    return
                signups = tuple(
                    signup
                    for signup in await module.qs.member_signups(
                        module.guild.id, channel_id, phase_index
                    )
                    if signup.member_id == interaction.user.id
                )
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to load phase signups.", log_guild(module.guild)
                )
                await send_interaction_response(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
        if not signups:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.signup_missing")
            )
            return
        selectable_signups = sorted(
            signups,
            key=lambda signup: (
                signup.game_account is not None,
                signup.game_account.casefold() if signup.game_account else "",
            ),
        )
        choices = tuple(
            AccountChoice(
                key=f"signup-{index}",
                game_account=signup.game_account,
                label=(
                    interaction.user.display_name
                    if signup.game_account is None
                    else signup.game_account
                ),
            )
            for index, signup in enumerate(selectable_signups)
        )
        view = SignupConfirmation(
            module,
            channel_id,
            phase_index,
            interaction.user.id,
            choices,
            t(
                interaction,
                "qs.event.unregister_confirmation",
                member=escape_discord_text(interaction.user.display_name),
            ),
            unregister=True,
        )
        view.message = await send_interaction_response(
            interaction, view.content(), view=view
        )

    async def confirm_phase_signup(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        phase_index: int,
        *,
        game_account: str | None,
    ) -> None:
        """Save the selected account for a phase signup."""
        module = self.module
        await defer_interaction(interaction, thinking=True)
        async with module.publisher.lock(channel_id):
            if await module.access.authorize(interaction, channel_id) is None:
                return
            if await module.access.phase(interaction, channel_id, phase_index) is None:
                return
            if game_account is not None:
                try:
                    accounts = await module.access.game_accounts_for(
                        interaction.user.id
                    )
                    if game_account.casefold() not in {
                        account.casefold() for account in accounts
                    }:
                        await send_followup(
                            interaction,
                            t(interaction, "qs.event.signup_account_invalid"),
                        )
                        return
                except aiosqlite.Error:
                    _logger.exception(
                        "%s Failed to validate Qs signup account.",
                        log_guild(module.guild),
                    )
                    await send_followup(
                        interaction, t(interaction, "qs.event.database_failed")
                    )
                    return
            try:
                signups = await module.qs.member_signups(
                    module.guild.id, channel_id, phase_index
                )
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to check the phase signup.", log_guild(module.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            if any(
                signup.member_id == interaction.user.id
                and (
                    signup.game_account.casefold()
                    if signup.game_account is not None
                    else None
                )
                == (game_account.casefold() if game_account is not None else None)
                for signup in signups
            ):
                await send_followup(
                    interaction,
                    t(interaction, "qs.event.signup_account_already_registered"),
                )
                return
            try:
                if not await module.qs.join(
                    module.guild.id,
                    channel_id,
                    phase_index,
                    interaction.user.id,
                    game_account,
                ):
                    raise aiosqlite.Error("Failed to save Qs signup.")
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to save Qs signup.", log_guild(module.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            updates = await self._queue_account_updates(
                channel_id, phase_index, interaction.user.id, game_account
            )
        refreshed = all(
            await asyncio.gather(*(asyncio.shield(task) for task in set(updates)))
        )
        await send_followup(
            interaction,
            t(interaction, "qs.event.joined")
            + self._refresh_hint(interaction, refreshed),
        )

    async def remove_phase_signup(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        phase_index: int,
        *,
        game_account: str | None,
    ) -> None:
        """Remove only the selected account's signup from a phase."""
        module = self.module
        await defer_interaction(interaction, thinking=True)
        async with module.publisher.lock(channel_id):
            if await module.access.authorize(interaction, channel_id) is None:
                return
            if await module.access.phase(interaction, channel_id, phase_index) is None:
                return
            try:
                signups = await module.qs.member_signups(
                    module.guild.id, channel_id, phase_index
                )
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to check the phase signup.", log_guild(module.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            if not any(
                signup.member_id == interaction.user.id
                and (
                    signup.game_account.casefold()
                    if signup.game_account is not None
                    else None
                )
                == (game_account.casefold() if game_account is not None else None)
                for signup in signups
            ):
                await send_followup(
                    interaction, t(interaction, "qs.event.signup_missing")
                )
                return
            try:
                if not await module.qs.remove_signup(
                    module.guild.id,
                    channel_id,
                    phase_index,
                    interaction.user.id,
                    game_account,
                ):
                    raise aiosqlite.Error("Failed to remove Qs signup.")
            except aiosqlite.Error:
                _logger.exception(
                    "%s Failed to remove Qs signup.", log_guild(module.guild)
                )
                await send_followup(
                    interaction, t(interaction, "qs.event.database_failed")
                )
                return
            updates = await self._queue_account_updates(
                channel_id, phase_index, interaction.user.id, game_account
            )
        refreshed = all(
            await asyncio.gather(*(asyncio.shield(task) for task in set(updates)))
        )
        await send_followup(
            interaction,
            t(interaction, "qs.event.signup_removed")
            + self._refresh_hint(interaction, refreshed),
        )

    async def remove_member(self, channel_id: int, member_id: int) -> bool:
        """Remove signups and enqueue only phase lists that contained the member."""
        module = self.module
        async with module.publisher.lock(channel_id):
            affected = [
                phase.index
                for phase in await module.qs.phases(module.guild.id, channel_id)
                if member_id
                in await module.qs.members(module.guild.id, channel_id, phase.index)
            ]
            if not await module.qs.remove_member(
                module.guild.id, member_id, channel_id
            ):
                return False
            updates = [
                module.publisher.queue_update(channel_id, index) for index in affected
            ]
        return all(await asyncio.gather(*(asyncio.shield(task) for task in updates)))
