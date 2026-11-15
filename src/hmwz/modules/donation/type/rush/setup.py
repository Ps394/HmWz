"""Configuration of Rush donations using separate local date and time inputs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_temporary_response
from hmwz.ui.components.date_time_input import DateTimeInput

from ...models import DonationType
from .pricing import RUSH_DURATIONS_HOURS, validate_rush_target

if TYPE_CHECKING:
    from ...commands.setup.config.view import DonationSetupView
    from ...commands.setup.config.draft import DonationSetupDraft


def configured_type(draft: DonationSetupDraft) -> DonationType:
    """Build the fixed-duration crystal donation configuration."""
    return DonationType(
        name=t(draft.module.guild, "donation.type.rush.name"),
        kind="time_reduction",
        unit=draft.unit or t(draft.module.guild, "donation.type.rush.unit"),
        input_mode="free",
        choices=(),
        time_reductions=tuple(f"{hours}h" for hours in RUSH_DURATIONS_HOURS),
    )


def start_datetime_input(
    context: discord.Guild, started_at: datetime, timezone_name: str = "UTC"
) -> DateTimeInput:
    """Create the shared separate local date and time picker for the Rush start."""
    return DateTimeInput(
        context,
        label=t(context, "donation.type.rush.setup.start_label"),
        timezone_name=timezone_name,
        value=started_at,
    )


class DonationRushStartModal(discord.ui.Modal):
    """Set the Rush start from separate local date and time inputs."""

    def __init__(self, setup_view: DonationSetupView) -> None:
        draft = setup_view.draft
        super().__init__(
            title=t(draft.module.guild, "donation.type.rush.setup.start_title")[:45]
        )
        self.draft = draft
        self.setup_view = setup_view
        self.start_input = start_datetime_input(
            draft.module.guild,
            draft.rush_start_at or datetime.now(UTC).replace(second=0, microsecond=0),
            draft.timezone_name,
        )
        self.add_item(self.start_input.date_input)
        self.add_item(self.start_input.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            started_at = self.start_input.parse()
            if started_at is None:
                raise ValueError("A start is required.")
        except ValueError:
            await send_temporary_response(
                interaction, t(interaction, "ui.datetime.invalid")
            )
            return
        try:
            if self.draft.target_at is not None:
                self.draft.target_at = validate_rush_target(
                    started_at, self.draft.target_at, self.draft.accelerated_hours
                )
        except ValueError:
            await send_temporary_response(
                interaction,
                t(interaction, "donation.type.rush.error.invalid_schedule"),
            )
            return
        self.draft.rush_start_at = started_at
        await self.setup_view.refresh(interaction)


class DonationRushTargetModal(discord.ui.Modal):
    """Set or clear the earliest permitted Rush end using separate date and time."""

    def __init__(self, setup_view: DonationSetupView) -> None:
        self.setup_view = setup_view
        self.draft = setup_view.draft
        super().__init__(
            title=t(self.draft.module.guild, "donation.type.rush.setup.target_title")[
                :45
            ]
        )
        self.target_input = DateTimeInput(
            self.draft.module.guild,
            label=t(self.draft.module.guild, "donation.type.rush.setup.target_label"),
            timezone_name=self.draft.timezone_name,
            value=self.draft.target_at,
            required=False,
        )
        self.add_item(self.target_input.date_input)
        self.add_item(self.target_input.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            target_at = self.target_input.parse()
        except ValueError:
            await send_temporary_response(
                interaction, t(interaction, "ui.datetime.invalid")
            )
            return
        try:
            if target_at is not None:
                if self.draft.rush_start_at is None:
                    raise ValueError("A target requires a Rush start.")
                target_at = validate_rush_target(
                    self.draft.rush_start_at, target_at, self.draft.accelerated_hours
                )
        except ValueError:
            await send_temporary_response(
                interaction,
                t(interaction, "donation.type.rush.error.invalid_target"),
            )
            return
        self.draft.target_at = target_at
        await self.setup_view.refresh(interaction)
