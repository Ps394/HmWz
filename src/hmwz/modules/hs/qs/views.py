"""Persistent phase actions and player-owned destroyed-base confirmations."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

from .models import Phase
from .overview import phase_label, phase_period

if TYPE_CHECKING:
    from .module import QsModule


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
            view = BaseReportConfirmation(
                self.module, self.channel_id, self.phase_index, interaction.user.id
            )
            view.message = await send_interaction_response(
                interaction,
                t(
                    interaction,
                    "qs.event.report_confirmation",
                    member=escape_discord_text(interaction.user.display_name),
                ),
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
        view = BaseReportConfirmation(
            self.module,
            self.channel_id,
            self.phase_index,
            interaction.user.id,
            withdraw_member_id=interaction.user.id,
        )
        view.message = await send_interaction_response(
            interaction,
            t(
                interaction,
                "qs.event.withdraw_confirmation",
                member=escape_discord_text(interaction.user.display_name),
            ),
            view=view,
        )


class BaseReportConfirmation(EphemeralView):
    """Confirm the player's own destroyed-base report without text inputs."""

    def __init__(
        self,
        module: QsModule,
        channel_id: int,
        phase_index: int,
        owner_id: int,
        *,
        withdraw_member_id: int | None = None,
        report_member: discord.Member | None = None,
        moderation: bool = False,
    ) -> None:
        super().__init__(timeout=180)
        self.module = module
        self.channel_id = channel_id
        self.phase_index = phase_index
        self.owner_id = owner_id
        self.withdraw_member_id = withdraw_member_id
        self.report_member, self.moderation = report_member, moderation
        localize_buttons(
            self,
            module.guild,
            {
                "qs_base_confirm": "qs.admin.confirm",
                "qs_base_cancel": "qs.admin.cancel",
            },
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
        label="Confirm", style=discord.ButtonStyle.success, custom_id="qs_base_confirm"
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Recheck the Qs role and save the reporting player's display name."""
        if not await self.interaction_check(interaction):
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
                member=self.report_member,
            )
        else:
            await self.module.withdraw_base(
                interaction, self.channel_id, self.phase_index, self.withdraw_member_id
            )
        self.stop()
        await delete_temporary_message(self.message or interaction.message)

    @discord.ui.button(
        label="Cancel", style=discord.ButtonStyle.secondary, custom_id="qs_base_cancel"
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Close the confirmation without recording a destroyed base."""
        if not await self.interaction_check(interaction):
            return
        await self.dismiss(interaction)
