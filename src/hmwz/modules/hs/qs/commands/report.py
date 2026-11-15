"""Moderator command for reporting a destroyed base for a player."""

from __future__ import annotations

import logging

import aiosqlite
import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import t
from hmwz.ui.messages import send_interaction_response
from hmwz.utils.text import escape_discord_text

from ..phases.accounts import AccountChoice
from ..phases.bases.views import BaseReportConfirmation, reporting_choices
from ..phases.embeds import report_name
from .common import get_module

_logger = logging.getLogger(__name__)


async def report_dialog(
    interaction: discord.Interaction,
    player: discord.Member,
    phase: int | None,
) -> None:
    """Open the report or withdrawal selector for a moderated player."""
    module = await get_module(interaction)
    if module is None or interaction.channel_id is None:
        return
    if not await module.access.authorize_moderation(interaction, interaction.channel_id):
        return
    reports = await module.qs.reports(module.guild.id, interaction.channel_id)
    choices: tuple[AccountChoice, ...]
    if phase is None:
        player_reports = tuple(
            item for item in reports if item.member_id == player.id
        )
        if not player_reports:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.withdraw_missing")
            )
            return
        phase_index = player_reports[0].phase_index
        choices = tuple(
            AccountChoice(
                key=f"report-{index}",
                game_account=report.game_account,
                label=report_name(module.guild, report),
                description=t(
                    interaction, "qs.event.phase", index=report.phase_index
                ),
                report_key=report.report_key,
            )
            for index, report in enumerate(player_reports)
        )
    else:
        phase_index = phase
        if not any(
            item.index == phase
            for item in await module.qs.phases(
                module.guild.id, interaction.channel_id
            )
        ):
            await send_interaction_response(
                interaction, t(interaction, "qs.event.not_configured")
            )
            return
        try:
            accounts = await module.access.game_accounts_for(player.id)
        except aiosqlite.Error:
            _logger.exception(
                "Failed to load Qs reporting accounts for member %s.", player.id
            )
            await send_interaction_response(
                interaction, t(interaction, "qs.event.database_failed")
            )
            return
        choices = reporting_choices(
            player.display_name,
            accounts,
            member_id=player.id,
            reports=reports,
        )
        if not choices:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.report_accounts_exhausted")
            )
            return
        player_reports = ()
    view = BaseReportConfirmation(
        module,
        interaction.channel_id,
        phase_index,
        interaction.user.id,
        choices=choices,
        prompt=t(
            interaction,
            (
                "qs.event.withdraw_confirmation_display_name"
                if len(player_reports) == 1
                and player_reports[0].game_account is None
                else (
                    "qs.event.withdraw_confirmation_default"
                    if any(report.game_account is None for report in player_reports)
                    else "qs.event.withdraw_confirmation"
                )
            )
            if phase is None
            else "qs.event.moderator_report_confirmation",
            member=escape_discord_text(player.display_name),
            phase=phase_index,
        ),
        withdraw_member_id=player.id if phase is None else None,
        withdraw_reports=player_reports,
        report_member=player if phase is not None else None,
        moderation=True,
    )
    view.message = await send_interaction_response(
        interaction,
        view.content()
        if phase is None and len(player_reports) > 1
        else view.prompt,
        view=view,
    )


@app_commands.command(
    name="report",
    description=app_commands.locale_str(
        "Add a base report for a player", key="qs.admin.report"
    ),
)
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
async def report(
    interaction: discord.Interaction,
    player: discord.Member,
    phase: app_commands.Range[int, 1, 5],
) -> None:
    """Confirm a moderator-created player report in the configured main channel."""
    await report_dialog(interaction, player, phase)
