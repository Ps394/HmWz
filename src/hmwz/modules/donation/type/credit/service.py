"""Credit donation entry and persistence workflow."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_temporary_response

from ...models import DonationType
from .views import DonationAmountChoiceView, DonationAmountModal

if TYPE_CHECKING:
    from ...module import DonationModule


async def start_donation(
    module: DonationModule,
    interaction: discord.Interaction,
    channel_id: int,
    donation_type: DonationType,
    *,
    time_reduction: str | None = None,
) -> None:
    """Open fixed credit choices or a free amount input."""
    if time_reduction is not None:
        await send_temporary_response(
            interaction, t(interaction, "donation.error.invalid_type")
        )
        return
    if donation_type.input_mode == "choice" and donation_type.choices:
        await interaction.response.send_message(
            t(interaction, "donation.setup.amount_donation_prompt"),
            view=DonationAmountChoiceView(module, channel_id, donation_type),
            ephemeral=True,
        )
        return
    await interaction.response.send_modal(
        DonationAmountModal(module, channel_id, donation_type)
    )


async def record_donation(
    module: DonationModule,
    interaction: discord.Interaction,
    channel_id: int,
    donation_type: DonationType,
    amount: Decimal,
    *,
    time_reduction: str | None,
    expected_cycle: int | None = None,
) -> tuple[bool, bool]:
    """Validate a credit donation, save it, and refresh shared public messages."""
    guild = interaction.guild
    member = interaction.user
    if (
        guild is None
        or guild.id != module.guild.id
        or not isinstance(member, discord.Member)
        or amount <= 0
        or (donation_type.kind != "simple" or time_reduction is not None)
        or (
            donation_type.input_mode == "choice"
            and amount not in {Decimal(choice) for choice in donation_type.choices}
        )
    ):
        return False, False

    async with module._cycle_lock(channel_id):
        current_type = await module.donations.get_type(
            guild=module.guild, channel_id=channel_id
        )
        configuration = await module.donations.get_channel(
            guild=module.guild, channel_id=channel_id
        )
        if (
            current_type != donation_type
            or configuration is None
            or not configuration.donations_enabled
            or (
                expected_cycle is not None
                and configuration.current_cycle != expected_cycle
            )
        ):
            return False, False
        if not await module.donations.add_donation(
            guild=guild,
            channel_id=channel_id,
            member=member,
            donation_type=donation_type,
            amount=amount,
            time_reduction=time_reduction,
            cycle=configuration.current_cycle,
        ):
            return False, False
    return True, await module.compose_overview(channel_id)
