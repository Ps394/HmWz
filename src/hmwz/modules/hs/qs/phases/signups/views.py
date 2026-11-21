"""Signup and unregister controls for a single phase."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.ui.components.localized import LocalizedButton
from hmwz.ui.messages import delete_temporary_message

from ...models import Phase
from ..accounts import AccountChoice, AccountConfirmation
from ..embeds import phase_label

if TYPE_CHECKING:
    from ...module import QsModule


class PhaseButton(LocalizedButton):
    """Open account selection for signing up to one phase."""

    def __init__(self, module: QsModule, channel_id: int, phase: Phase) -> None:
        super().__init__(
            module.guild,
            "qs.event.signup_label",
            values={"phase": phase_label(module.guild, phase)},
            style=discord.ButtonStyle.primary,
            custom_id=f"qs:toggle:{channel_id}:{phase.index}",
            row=phase.index - 1,
        )
        self.module = module
        self.channel_id = channel_id
        self.phase_index = phase.index

    async def callback(self, interaction: discord.Interaction) -> None:
        """Delegate signup authorization and account selection to the service."""
        await self.module.signups.signup_button(
            interaction, self.channel_id, self.phase_index
        )


class PhaseUnregisterButton(LocalizedButton):
    """Open account selection for unregistering from one phase."""

    def __init__(self, module: QsModule, channel_id: int, phase: Phase) -> None:
        super().__init__(
            module.guild,
            "qs.event.unregister_label",
            values={"phase": phase_label(module.guild, phase)},
            style=discord.ButtonStyle.secondary,
            custom_id=f"qs:leave:{channel_id}:{phase.index}",
            row=phase.index - 1,
        )
        self.module = module
        self.channel_id = channel_id
        self.phase_index = phase.index

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.signups.unregister_phase_button(
            interaction, self.channel_id, self.phase_index
        )


class SignupConfirmation(AccountConfirmation):
    """Select one account to add or remove from a phase signup."""

    def __init__(
        self,
        module: QsModule,
        channel_id: int,
        phase_index: int,
        owner_id: int,
        choices: tuple[AccountChoice, ...],
        prompt: str,
        *,
        unregister: bool = False,
    ) -> None:
        if not choices:
            raise ValueError("A phase signup confirmation requires an account choice.")
        default_choice = next(
            (choice for choice in choices if choice.game_account is None), choices[0]
        )
        super().__init__(
            module,
            channel_id,
            phase_index,
            owner_id,
            choices,
            prompt,
            selected_account=default_choice.key,
        )
        self.unregister = unregister

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.success,
        custom_id="qs_base_confirm",
        row=2,
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self.interaction_check(interaction):
            return
        account = self._selected_choice().game_account
        if self.unregister:
            await self.module.signups.remove_phase_signup(
                interaction, self.channel_id, self.phase_index, game_account=account
            )
        else:
            await self.module.signups.confirm_phase_signup(
                interaction, self.channel_id, self.phase_index, game_account=account
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
        if not await self.interaction_check(interaction):
            return
        await self.dismiss(interaction)
