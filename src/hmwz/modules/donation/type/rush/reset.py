"""Rush cycle reset with a Discord timestamp start."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from .validation import parse_rush_timestamp
from .setup import start_timestamp_input
from .pricing import validate_rush_target
from hmwz.ui.messages import send_temporary_response as _send_temporary_response
from .. import reset_result_key


if TYPE_CHECKING:
    from ...module import DonationModule


class DonationRushResetModal(discord.ui.Modal):
    """Set the next Rush start using a timezone-independent timestamp."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        owner_id: int,
    ) -> None:
        super().__init__(title=t(module.guild, "donation.reset.start_modal_title")[:45])
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.timestamp_input = start_timestamp_input(module.guild, datetime.now(UTC))
        self.add_item(self.timestamp_input)
        self.target_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(module.guild, "donation.setup.target_timestamp")[:45],
            placeholder=t(module.guild, "donation.setup.start_timestamp_placeholder")[
                :100
            ],
            required=False,
            max_length=64,
        )
        self.add_item(self.target_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await _send_temporary_response(
                interaction, t(interaction, "donation.setup.owner_only")
            )
            return
        try:
            rush_start_at = parse_rush_timestamp(self.timestamp_input.value)
            target_at = (
                parse_rush_timestamp(self.target_input.value)
                if self.target_input.value.strip()
                else None
            )
            if target_at is not None:
                validate_rush_target(rush_start_at, target_at)
        except ValueError:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_rush_schedule")
            )
            return
        await interaction.response.defer(ephemeral=True)
        reset_done, messages_updated, export_failed = await self.module.reset_cycle(
            self.channel_id, rush_start_at=rush_start_at, target_at=target_at
        )
        result = await interaction.followup.send(
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
