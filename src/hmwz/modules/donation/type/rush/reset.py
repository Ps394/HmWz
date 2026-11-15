"""Rush cycle reset with separate local date and time inputs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

from hmwz.ui.messages import send_followup
from hmwz.i18n import t
from hmwz.ui.components.date_time_input import DateTimeInput
from .setup import start_datetime_input
from .pricing import validate_rush_target
from hmwz.ui.messages import send_temporary_response as _send_temporary_response
from .. import reset_result_key


if TYPE_CHECKING:
    from ...module import DonationModule


class DonationRushResetModal(discord.ui.Modal):
    """Set the next Rush start using separate local date and time inputs."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        owner_id: int,
        timezone_name: str = "UTC",
    ) -> None:
        super().__init__(
            title=t(module.guild, "donation.type.rush.reset.start_modal_title")[:45]
        )
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.start_input = start_datetime_input(
            module.guild,
            datetime.now(UTC).replace(second=0, microsecond=0),
            timezone_name,
        )
        self.add_item(self.start_input.date_input)
        self.add_item(self.start_input.time_input)
        self.target_input = DateTimeInput(
            module.guild,
            label=t(module.guild, "donation.type.rush.setup.target_label"),
            timezone_name=timezone_name,
            required=False,
        )
        self.add_item(self.target_input.date_input)
        self.add_item(self.target_input.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await _send_temporary_response(
                interaction, t(interaction, "donation.setup.owner_only")
            )
            return
        try:
            rush_start_at = self.start_input.parse()
            if rush_start_at is None:
                raise ValueError("A start is required.")
            target_at = self.target_input.parse()
        except ValueError:
            await _send_temporary_response(
                interaction, t(interaction, "ui.datetime.invalid")
            )
            return
        try:
            if target_at is not None:
                target_at = validate_rush_target(rush_start_at, target_at)
        except ValueError:
            await _send_temporary_response(
                interaction,
                t(interaction, "donation.type.rush.error.invalid_schedule"),
            )
            return
        await interaction.response.defer(ephemeral=True)
        reset_done, messages_updated, export_failed = await self.module.reset_cycle(
            self.channel_id, rush_start_at=rush_start_at, target_at=target_at
        )
        result = await send_followup(
            interaction,
            t(
                interaction,
                reset_result_key(
                    reset_done, messages_updated, export_failed=export_failed
                ),
            ),
            ephemeral=True,
            wait=True,
        )
        await result.delete(delay=5)
