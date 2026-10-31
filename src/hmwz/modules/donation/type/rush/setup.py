"""Configuration of Rush donations using Discord timestamps."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_temporary_response
from hmwz.ui.components.timestamp_input import TimestampInput

from ...models import DonationType
from .pricing import RUSH_DURATIONS_HOURS, validate_rush_target

if TYPE_CHECKING:
    from ...commands.setup.config.view import DonationSetupView
    from ...commands.setup.config.draft import DonationSetupDraft


def configured_type(draft: DonationSetupDraft) -> DonationType:
    """Build the fixed-duration crystal donation configuration."""
    return DonationType(
        name=t(draft.module.guild, "donation.setup.rush"),
        kind="time_reduction",
        unit=draft.unit or t(draft.module.guild, "donation.setup.crystals_unit"),
        input_mode="free",
        choices=(),
        time_reductions=tuple(f"{hours}h" for hours in RUSH_DURATIONS_HOURS),
    )


def start_timestamp_input(
    context: discord.Guild, started_at: datetime, timezone_name: str = "UTC"
) -> TimestampInput:
    """Create the shared local date/time picker with absolute timestamp support."""
    return TimestampInput(
        context,
        label=t(context, "donation.setup.edit_start"),
        timezone_name=timezone_name,
        value=started_at,
    )


class DonationRushStartModal(discord.ui.Modal):
    """Set the Rush start from a timezone-independent timestamp."""

    def __init__(self, setup_view: DonationSetupView) -> None:
        draft = setup_view.draft
        super().__init__(title=t(draft.module.guild, "donation.setup.start_title")[:45])
        self.draft = draft
        self.setup_view = setup_view
        self.timestamp_input = start_timestamp_input(
            draft.module.guild,
            draft.rush_start_at or datetime.now(UTC).replace(second=0, microsecond=0),
            draft.timezone_name,
        )
        self.add_item(self.timestamp_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            started_at = self.timestamp_input.parse()
            if started_at is None:
                raise ValueError("A start is required.")
        except ValueError:
            await send_temporary_response(
                interaction, t(interaction, "ui.timestamp.invalid")
            )
            return
        try:
            if self.draft.target_at is not None:
                validate_rush_target(
                    started_at, self.draft.target_at, self.draft.accelerated_hours
                )
        except ValueError:
            await send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_rush_schedule")
            )
            return
        self.draft.rush_start_at = started_at
        await self.setup_view.refresh(interaction)


class DonationRushTargetModal(discord.ui.Modal):
    """Set or clear the earliest permitted Rush end using a Discord timestamp."""

    def __init__(self, setup_view: DonationSetupView) -> None:
        self.setup_view = setup_view
        self.draft = setup_view.draft
        super().__init__(
            title=t(self.draft.module.guild, "donation.setup.target_title")[:45]
        )
        self.target_input = TimestampInput(
            self.draft.module.guild,
            label=t(self.draft.module.guild, "donation.setup.target_timestamp"),
            timezone_name=self.draft.timezone_name,
            value=self.draft.target_at,
            required=False,
        )
        self.add_item(self.target_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            target_at = self.target_input.parse()
        except ValueError:
            await send_temporary_response(
                interaction, t(interaction, "ui.timestamp.invalid")
            )
            return
        try:
            if target_at is not None:
                if self.draft.rush_start_at is None:
                    raise ValueError("A target requires a Rush start.")
                validate_rush_target(
                    self.draft.rush_start_at, target_at, self.draft.accelerated_hours
                )
        except ValueError:
            await send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_target")
            )
            return
        self.draft.target_at = target_at
        await self.setup_view.refresh(interaction)
