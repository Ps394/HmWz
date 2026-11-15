"""Destroyed-base report and withdrawal controls for a single phase."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz.i18n import t
from hmwz.ui.components.localized import LocalizedButton
from hmwz.ui.messages import delete_temporary_message, send_interaction_response
from hmwz.utils.text import escape_discord_text

from ...models import BaseReport
from ..accounts import ACCOUNT_OPTIONS_PER_PAGE, AccountChoice, AccountConfirmation
from ..embeds import report_name

if TYPE_CHECKING:
    from ...module import QsModule

_logger = logging.getLogger(__name__)


def reporting_choices(
    display_name: str,
    accounts: tuple[str, ...],
    *,
    member_id: int,
    reports: tuple[BaseReport, ...],
) -> tuple[AccountChoice, ...]:
    """Offer only identities that have not already reported a base."""
    reported_accounts = {
        report.game_account.casefold()
        for report in reports
        if report.game_account is not None
    }
    main_account_available = not any(
        report.member_id == member_id and report.game_account is None
        for report in reports
    )
    choices: list[AccountChoice] = []
    if main_account_available:
        choices.append(
            AccountChoice(
                key="discord-display-name",
                game_account=None,
                label=display_name,
            )
        )
    choices.extend(
            AccountChoice(key=f"account-{index}", game_account=account, label=account)
            for index, account in enumerate(accounts)
            if account.casefold() not in reported_accounts
    )
    return tuple(choices)


class BaseReportConfirmation(AccountConfirmation):
    """Select an account and confirm a destroyed-base report or withdrawal."""

    owner_denied_key = "qs.event.report_owner"

    def __init__(
        self,
        module: QsModule,
        channel_id: int,
        phase_index: int,
        owner_id: int,
        *,
        choices: tuple[AccountChoice, ...],
        prompt: str,
        withdraw_member_id: int | None = None,
        withdraw_reports: tuple[BaseReport, ...] = (),
        report_member: discord.Member | None = None,
        moderation: bool = False,
    ) -> None:
        if not choices:
            raise ValueError("A base-report confirmation requires at least one choice.")
        if len({choice.key for choice in choices}) != len(choices):
            raise ValueError("Base-report choices must have unique values.")
        default_choice = next(
            (choice for choice in choices if choice.game_account is None), None
        )
        super().__init__(
            module,
            channel_id,
            phase_index,
            owner_id,
            choices,
            prompt,
            selected_account=default_choice.key if default_choice else None,
            show_selection=not (len(choices) == 1 and choices[0].game_account is None),
        )
        self.withdraw_member_id = withdraw_member_id
        self.withdraw_reports = withdraw_reports
        self.report_member, self.moderation = report_member, moderation
        self.confirm.disabled = self.selected_account is None

    def select_account(self, account: str) -> None:
        """Enable confirmation for a currently offered account."""
        super().select_account(account)
        self.confirm.disabled = False

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.success,
        custom_id="qs_base_confirm",
        row=2,
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Recheck permissions and save the selected reporting identity."""
        if not await self.interaction_check(interaction):
            return
        if self.selected_account is None:
            return
        if self.moderation and not await self.module.access.authorize_moderation(
            interaction, self.channel_id
        ):
            return
        if self.withdraw_member_id is None:
            await self.module.bases.report_base(
                interaction,
                self.channel_id,
                self.phase_index,
                game_account=self._selected_choice().game_account,
                member=self.report_member,
            )
        else:
            choice = self._selected_choice()
            report = next(
                item
                for item in self.withdraw_reports
                if item.report_key == choice.report_key
            )
            await self.module.bases.withdraw_base(
                interaction,
                self.channel_id,
                report.phase_index,
                self.withdraw_member_id,
                report.game_account,
            )
        self.stop()
        await delete_temporary_message(self.message or interaction.message)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_base_cancel",
        row=2,
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Close the confirmation without recording a destroyed base."""
        if not await self.interaction_check(interaction):
            return
        await self.dismiss(interaction)


class ReportButton(LocalizedButton):
    """Open a confirmation only for members with this channel's Qs role."""

    def __init__(self, module: QsModule, channel_id: int, phase_index: int) -> None:
        super().__init__(
            module.guild,
            "qs.event.report",
            style=discord.ButtonStyle.success,
            custom_id=f"qs:report:{channel_id}:{phase_index}",
        )
        self.module = module
        self.channel_id = channel_id
        self.phase_index = phase_index

    async def callback(self, interaction: discord.Interaction) -> None:
        """Revalidate the role before presenting the confirmation."""
        if await self.module.access.authorize(interaction, self.channel_id) is None:
            return
        try:
            accounts = await self.module.access.game_accounts_for(interaction.user.id)
            reports = await self.module.qs.reports(
                self.module.guild.id, self.channel_id
            )
        except aiosqlite.Error:
            _logger.exception(
                "Failed to load Qs reporting accounts for member %s.",
                interaction.user.id,
            )
            await send_interaction_response(
                interaction, t(interaction, "qs.event.database_failed")
            )
            return
        choices = reporting_choices(
            interaction.user.display_name,
            accounts,
            member_id=interaction.user.id,
            reports=reports,
        )
        if not choices:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.report_accounts_exhausted")
            )
            return
        view = BaseReportConfirmation(
            self.module,
            self.channel_id,
            self.phase_index,
            interaction.user.id,
            choices=choices,
            prompt=t(
                interaction,
                "qs.event.report_confirmation"
                if any(choice.game_account is not None for choice in choices)
                else "qs.event.report_confirmation_display_name",
                member=escape_discord_text(interaction.user.display_name),
            ),
        )
        view.message = await send_interaction_response(
            interaction, view.prompt, view=view
        )


class WithdrawButton(LocalizedButton):
    """Open a confirmation for the clicking player's own report only."""

    def __init__(self, module: QsModule, channel_id: int, phase_index: int) -> None:
        super().__init__(
            module.guild,
            "qs.event.withdraw",
            style=discord.ButtonStyle.secondary,
            custom_id=f"qs:withdraw:{channel_id}:{phase_index}",
        )
        self.module, self.channel_id, self.phase_index = module, channel_id, phase_index

    async def callback(self, interaction: discord.Interaction) -> None:
        if (
            await self.module.access.authorize_withdrawal(
                interaction, self.channel_id, interaction.user.id
            )
            is None
        ):
            return
        reports = tuple(
            report
            for report in await self.module.qs.reports(
                self.module.guild.id, self.channel_id
            )
            if report.phase_index == self.phase_index
            and report.member_id == interaction.user.id
        )
        if not reports:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.withdraw_missing")
            )
            return
        choices = tuple(
            AccountChoice(
                key=f"report-{index}",
                game_account=report.game_account,
                label=report_name(self.module.guild, report),
                description=t(interaction, "qs.event.phase", index=report.phase_index),
                report_key=report.report_key,
            )
            for index, report in enumerate(reports)
        )
        view = BaseReportConfirmation(
            self.module,
            self.channel_id,
            self.phase_index,
            interaction.user.id,
            choices=choices,
            prompt=t(
                interaction,
                "qs.event.withdraw_confirmation_display_name"
                if len(reports) == 1 and reports[0].game_account is None
                else (
                    "qs.event.withdraw_confirmation_default"
                    if any(report.game_account is None for report in reports)
                    else "qs.event.withdraw_confirmation"
                ),
                member=escape_discord_text(interaction.user.display_name),
            ),
            withdraw_member_id=interaction.user.id,
            withdraw_reports=reports,
        )
        view.message = await send_interaction_response(
            interaction,
            view.content() if len(reports) > 1 else view.prompt,
            view=view,
        )
