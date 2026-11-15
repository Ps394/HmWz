"""Account selection shared by phase signup and destroyed-base confirmations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.components.localized import LocalizedButton, localize_buttons
from hmwz.ui.messages import send_interaction_response
from hmwz.utils.text import escape_discord_text

if TYPE_CHECKING:
    from ..module import QsModule

ACCOUNT_OPTIONS_PER_PAGE = 25


@dataclass(frozen=True, slots=True)
class AccountChoice:
    """One selectable identity and its persisted account value."""

    key: str
    game_account: str | None
    label: str
    description: str | None = None
    report_key: str | None = None


class AccountSelect(discord.ui.Select):
    """Choose one linked game account or one existing report."""

    def __init__(
        self,
        owner: AccountConfirmation,
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

    def __init__(self, owner: AccountConfirmation, *, next_page: bool) -> None:
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
        page_count = math.ceil(len(self.owner.choices) / ACCOUNT_OPTIONS_PER_PAGE)
        candidate = self.owner.page + (1 if self.next_page else -1)
        if not 0 <= candidate < page_count:
            return
        self.owner.page = candidate
        self.owner.update_page_buttons()
        self.owner.update_options()
        await interaction.response.edit_message(
            content=self.owner.content(), view=self.owner
        )


class AccountConfirmation(EphemeralView):
    """Paged account selection owned by the member who opened it."""

    owner_denied_key = "qs.event.signup_owner"

    def __init__(
        self,
        module: QsModule,
        channel_id: int,
        phase_index: int,
        owner_id: int,
        choices: tuple[AccountChoice, ...],
        prompt: str,
        *,
        selected_account: str | None,
        show_selection: bool = True,
    ) -> None:
        super().__init__(timeout=180)
        self.module = module
        self.channel_id = channel_id
        self.phase_index = phase_index
        self.owner_id = owner_id
        self.choices = choices
        self.prompt = prompt
        self.selected_account = selected_account
        self.page = (
            next(
                index
                for index, choice in enumerate(choices)
                if choice.key == selected_account
            )
            // ACCOUNT_OPTIONS_PER_PAGE
            if selected_account is not None
            else 0
        )
        self.selection = AccountSelect(
            self, self._page_options(), t(module.guild, "qs.event.choose_account")
        )
        if show_selection:
            self.add_item(self.selection)
        self.previous_button: AccountPageButton | None = None
        self.next_button: AccountPageButton | None = None
        if len(choices) > ACCOUNT_OPTIONS_PER_PAGE:
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

    def _page_options(self) -> list[discord.SelectOption]:
        start = self.page * ACCOUNT_OPTIONS_PER_PAGE
        return [
            discord.SelectOption(
                label=choice.label[:100] or choice.key[:100],
                value=choice.key,
                description=choice.description[:100] if choice.description else None,
                default=choice.key == self.selected_account,
            )
            for choice in self.choices[start : start + ACCOUNT_OPTIONS_PER_PAGE]
        ]

    def update_options(self) -> None:
        self.selection.options = self._page_options()

    def select_account(self, account: str) -> None:
        """Select one of the currently offered accounts."""
        if account not in {choice.key for choice in self.choices}:
            raise ValueError("The selected account is not an available choice.")
        self.selected_account = account
        self.update_options()

    def update_page_buttons(self) -> None:
        page_count = math.ceil(len(self.choices) / ACCOUNT_OPTIONS_PER_PAGE)
        if self.previous_button is not None:
            self.previous_button.disabled = self.page == 0
        if self.next_button is not None:
            self.next_button.disabled = self.page >= page_count - 1

    def _selected_choice(self) -> AccountChoice:
        if self.selected_account is None:
            raise ValueError("No account has been selected.")
        return next(
            choice for choice in self.choices if choice.key == self.selected_account
        )

    def content(self) -> str:
        if self.selected_account is None:
            return self.prompt
        return (
            self.prompt
            + "\n\n"
            + t(
                self.module.guild,
                "qs.event.selected_account",
                account=escape_discord_text(self._selected_choice().label),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the member who opened the confirmation can use it."""
        if interaction.user.id == self.owner_id:
            return True
        await send_interaction_response(
            interaction, t(interaction, self.owner_denied_key)
        )
        return False
