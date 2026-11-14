"""Persistent phase actions and player-owned destroyed-base confirmations."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_interaction_response
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.messages import delete_temporary_message
from hmwz.ui.components.localized import (
    LocalizedButton,
    localize_buttons,
)
from hmwz.utils.text import escape_discord_text

from .models import BaseReport, Phase
from .overview import phase_label, phase_period, report_name

if TYPE_CHECKING:
    from .module import QsModule

_logger = logging.getLogger(__name__)
_ACCOUNT_OPTIONS_PER_PAGE = 25


@dataclass(frozen=True, slots=True)
class AccountChoice:
    """One selectable reporting identity and its persisted account value."""

    key: str
    game_account: str | None
    label: str
    description: str | None = None
    report_key: str | None = None


def reporting_choices(
    interaction: discord.Interaction, display_name: str, accounts: tuple[str, ...]
) -> tuple[AccountChoice, ...]:
    """Offer the Discord display name first, followed by linked alternatives."""
    return (
        AccountChoice(
            key="discord-display-name",
            game_account=None,
            label=display_name,
            description=t(interaction, "qs.event.discord_display_name"),
        ),
        *(
            AccountChoice(key=f"account-{index}", game_account=account, label=account)
            for index, account in enumerate(accounts)
        ),
    )


class PhaseButton(LocalizedButton):
    """Toggle a member's signup for one phase."""

    def __init__(
        self, module: QsModule, channel_id: int, phase: Phase, timezone: str
    ) -> None:
        super().__init__(
            module.guild,
            "qs.event.signup_label",
            values={
                "phase": phase_label(module.guild, phase),
                "period": phase_period(phase, timezone),
            },
            style=discord.ButtonStyle.primary,
            custom_id=f"qs:toggle:{channel_id}:{phase.index}",
        )
        self.module = module
        self.channel_id = channel_id
        self.phase_index = phase.index

    async def callback(self, interaction: discord.Interaction) -> None:
        """Delegate signup authorization and persistence to the module."""
        await self.module.toggle_phase(interaction, self.channel_id, self.phase_index)


class OverviewView(discord.ui.View):
    """Persistent time-range signup buttons on the main overview."""

    def __init__(
        self,
        module: QsModule,
        channel_id: int,
        phases: tuple[Phase, ...],
        timezone: str,
    ) -> None:
        super().__init__(timeout=None)
        for phase in phases:
            self.add_item(PhaseButton(module, channel_id, phase, timezone))


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
        if await self.module.authorize(interaction, self.channel_id) is not None:
            try:
                accounts = await self.module.game_accounts_for(interaction.user.id)
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
                interaction, interaction.user.display_name, accounts
            )
            view = BaseReportConfirmation(
                self.module,
                self.channel_id,
                self.phase_index,
                interaction.user.id,
                choices=choices,
                prompt=t(
                    interaction,
                    "qs.event.report_confirmation"
                    if accounts
                    else "qs.event.report_confirmation_display_name",
                    member=escape_discord_text(interaction.user.display_name),
                ),
            )
            view.message = await send_interaction_response(
                interaction,
                view.prompt,
                view=view,
            )


class PhaseView(discord.ui.View):
    """Persistent destroyed-base action without thread signup controls."""

    def __init__(self, module: QsModule, channel_id: int, phase: Phase) -> None:
        super().__init__(timeout=None)
        self.add_item(ReportButton(module, channel_id, phase.index))
        self.add_item(WithdrawButton(module, channel_id, phase.index))


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
            await self.module.authorize_withdrawal(
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


class AccountSelect(discord.ui.Select):
    """Choose one linked game account or one existing report."""

    def __init__(
        self,
        owner: BaseReportConfirmation,
        options: list[discord.SelectOption],
        placeholder: str,
    ) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            custom_id="qs:base:account",
            row=0,
        )
        self.owner = owner

    async def callback(self, interaction: discord.Interaction) -> None:
        self.owner.select_account(self.values[0])
        await interaction.response.edit_message(
            content=self.owner.content(), view=self.owner
        )


class AccountPageButton(LocalizedButton):
    """Navigate the account options when they exceed Discord's per-menu limit."""

    def __init__(self, owner: BaseReportConfirmation, *, next_page: bool) -> None:
        self.owner = owner
        self.next_page = next_page
        super().__init__(
            owner.module.guild,
            "qs.event.next_page" if next_page else "qs.event.previous_page",
            style=discord.ButtonStyle.secondary,
            custom_id=f"qs:base:page:{'next' if next_page else 'previous'}",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        page_count = math.ceil(len(self.owner.choices) / _ACCOUNT_OPTIONS_PER_PAGE)
        candidate = self.owner.page + (1 if self.next_page else -1)
        if not 0 <= candidate < page_count:
            return
        self.owner.page = candidate
        self.owner.update_page_buttons()
        self.owner.update_options()
        await interaction.response.edit_message(
            content=self.owner.content(), view=self.owner
        )


class BaseReportConfirmation(EphemeralView):
    """Select an account and confirm a destroyed-base report or withdrawal."""

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
        super().__init__(timeout=180)
        self.module = module
        self.channel_id = channel_id
        self.phase_index = phase_index
        self.owner_id = owner_id
        self.withdraw_member_id = withdraw_member_id
        self.withdraw_reports = withdraw_reports
        self.report_member, self.moderation = report_member, moderation
        self.choices = choices
        self.prompt = prompt
        self.page = 0
        self.selected_account: str | None = None
        if not choices:
            raise ValueError("A base-report confirmation requires at least one choice.")
        if len({choice.key for choice in choices}) != len(choices):
            raise ValueError("Base-report choices must have unique values.")
        use_display_name = len(choices) == 1 and choices[0].game_account is None
        default_choice = next(
            (
                index
                for index, choice in enumerate(choices)
                if choice.game_account is None
            ),
            None,
        )
        if default_choice is not None:
            self.selected_account = choices[default_choice].key
            self.page = default_choice // _ACCOUNT_OPTIONS_PER_PAGE
        self.selection = AccountSelect(
            self,
            self._page_options(),
            t(module.guild, "qs.event.choose_account"),
        )
        if not use_display_name:
            self.add_item(self.selection)
        self.previous_button: AccountPageButton | None = None
        self.next_button: AccountPageButton | None = None
        if len(choices) > _ACCOUNT_OPTIONS_PER_PAGE:
            self.previous_button = AccountPageButton(self, next_page=False)
            self.next_button = AccountPageButton(self, next_page=True)
            self.add_item(self.previous_button)
            self.add_item(self.next_button)
            self.update_page_buttons()
        localize_buttons(
            self,
            module.guild,
            {
                "qs_base_confirm": "qs.admin.confirm",
                "qs_base_cancel": "qs.admin.cancel",
            },
        )
        self.confirm.disabled = self.selected_account is None

    def _page_options(self) -> list[discord.SelectOption]:
        start = self.page * _ACCOUNT_OPTIONS_PER_PAGE
        page = self.choices[start : start + _ACCOUNT_OPTIONS_PER_PAGE]
        return [
            discord.SelectOption(
                label=choice.label[:100] or choice.key[:100],
                value=choice.key,
                description=choice.description[:100] if choice.description else None,
                default=choice.key == self.selected_account,
            )
            for choice in page
        ]

    def update_options(self) -> None:
        self.selection.options = self._page_options()

    def select_account(self, account: str) -> None:
        """Enable confirmation for a currently offered account."""
        if account not in {choice.key for choice in self.choices}:
            raise ValueError("The selected account is not an available choice.")
        self.selected_account = account
        self.confirm.disabled = False
        self.update_options()

    def update_page_buttons(self) -> None:
        page_count = math.ceil(len(self.choices) / _ACCOUNT_OPTIONS_PER_PAGE)
        if self.previous_button is not None:
            self.previous_button.disabled = self.page == 0
        if self.next_button is not None:
            self.next_button.disabled = self.page >= page_count - 1

    def content(self) -> str:
        if self.selected_account is None:
            return self.prompt
        choice = self._selected_choice()
        return (
            self.prompt
            + "\n\n"
            + t(
                self.module.guild,
                "qs.event.selected_account",
                account=escape_discord_text(choice.label),
            )
        )

    def _selected_choice(self) -> AccountChoice:
        if self.selected_account is None:
            raise ValueError("No reporting identity has been selected.")
        return next(
            choice for choice in self.choices if choice.key == self.selected_account
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the reporting player can confirm or cancel."""
        if interaction.user.id == self.owner_id:
            return True
        await send_interaction_response(
            interaction, t(interaction, "qs.event.report_owner")
        )
        return False

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
        if self.moderation and not await self.module.authorize_moderation(
            interaction, self.channel_id
        ):
            return
        if self.withdraw_member_id is None:
            await self.module.report_base(
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
            await self.module.withdraw_base(
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
