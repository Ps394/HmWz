"""Rush donation quoting, confirmation validation, and persistence."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from decimal import Decimal
from typing import TYPE_CHECKING

import discord

from hmwz.ui.messages import send_initial_response
from hmwz.i18n import t
from hmwz.ui.messages import send_temporary_response

from ...models import DonationType
from .pricing import (
    RUSH_BUTTON_DURATIONS_HOURS,
    RUSH_DURATIONS_HOURS,
    available_rush_durations,
    rush_donation_cost,
    rush_donation_prices,
)
from .views import DonationRushConfirmationView, DonationTimeReductionView

if TYPE_CHECKING:
    from ...module import DonationModule

_logger = logging.getLogger(__name__)


async def start_donation(
    module: DonationModule,
    interaction: discord.Interaction,
    channel_id: int,
    donation_type: DonationType,
    *,
    time_reduction: str | None = None,
    replace_prompt: bool = False,
) -> None:
    """Quote an available Rush duration and open its confirmation prompt."""
    configuration = await module.donations.get_channel(
        guild=module.guild, channel_id=channel_id
    )
    now = datetime.now(timezone.utc)
    if configuration is None or configuration.rush_start_at is None:
        await send_temporary_response(
            interaction, t(interaction, "donation.error.rush_closed")
        )
        return
    summary = await module.donations.get_summary(
        guild=module.guild,
        channel_id=channel_id,
        cycle=configuration.current_cycle,
    )
    if summary is None:
        await send_temporary_response(
            interaction, t(interaction, "donation.error.save")
        )
        return
    rush_prices = rush_donation_prices(
        started_at=configuration.rush_start_at,
        now=now,
        accelerated_hours=summary.time_reduction_hours,
        target_at=configuration.target_at,
    )
    if not rush_prices:
        await send_temporary_response(
            interaction, t(interaction, "donation.error.rush_closed")
        )
        return
    if time_reduction is None:
        await send_initial_response(
            interaction,
            t(interaction, "donation.setup.hours_donation_prompt"),
            view=DonationTimeReductionView(
                module, channel_id, donation_type, rush_prices
            ),
            ephemeral=True,
        )
        return
    if time_reduction not in {f"{hours}h" for hours in rush_prices}:
        await send_temporary_response(
            interaction, t(interaction, "donation.error.choose_time")
        )
        return
    hours = int(time_reduction.removesuffix("h"))
    cost = rush_prices[hours]
    response_content = t(
        interaction,
        "donation.rush.confirm",
        hours=hours,
        cost=format(cost, "f"),
    )
    confirmation_view = DonationRushConfirmationView(
        module,
        channel_id,
        donation_type,
        hours,
        cost,
        configuration.current_cycle,
        configuration.rush_start_at,
        now,
        interaction.user.id,
    )
    await module.show_donation_confirmation(
        interaction, confirmation_view, response_content, replace_prompt=replace_prompt
    )


async def record_donation(
    module: DonationModule,
    interaction: discord.Interaction,
    channel_id: int,
    donation_type: DonationType,
    duration_hours: int,
    amount: Decimal,
    expected_cycle: int,
    expected_start_at: datetime,
    quoted_at: datetime,
) -> tuple[bool, bool]:
    """Save a quoted Rush donation only while its cycle and price remain valid."""
    guild = interaction.guild
    member = interaction.user
    if (
        guild is None
        or guild.id != module.guild.id
        or not isinstance(member, discord.Member)
        or donation_type.kind != "time_reduction"
        or duration_hours not in RUSH_DURATIONS_HOURS
        or amount <= 0
    ):
        return False, False
    async with module._cycle_lock(channel_id):
        configuration = await module.donations.get_channel(
            guild=module.guild, channel_id=channel_id
        )
        current_type = await module.donations.get_type(
            guild=module.guild, channel_id=channel_id
        )
        if (
            configuration is None
            or current_type != donation_type
            or configuration.current_cycle != expected_cycle
            or configuration.rush_start_at != expected_start_at
        ):
            return False, False
        summary = await module.donations.get_summary(
            guild=module.guild,
            channel_id=channel_id,
            cycle=configuration.current_cycle,
        )
        now = datetime.now(timezone.utc)
        if (
            summary is None
            or duration_hours
            not in available_rush_durations(
                started_at=expected_start_at,
                now=quoted_at,
                accelerated_hours=summary.time_reduction_hours,
                target_at=configuration.target_at,
            )
            or duration_hours
            not in available_rush_durations(
                started_at=expected_start_at,
                now=now,
                accelerated_hours=summary.time_reduction_hours,
                target_at=configuration.target_at,
            )
            or amount
            != rush_donation_cost(
                started_at=expected_start_at,
                now=quoted_at,
                duration_hours=duration_hours,
                accelerated_hours=summary.time_reduction_hours,
            )
        ):
            _logger.warning("Rush quote no longer available in channel %s.", channel_id)
            return False, False
        if not await module.donations.add_donation(
            guild=guild,
            channel_id=channel_id,
            member=member,
            donation_type=donation_type,
            amount=amount,
            time_reduction=f"{duration_hours}h",
            cycle=configuration.current_cycle,
            rush_quoted_at=quoted_at,
        ):
            return False, False
    return True, await module.compose_overview(channel_id)


async def refresh_overviews(module: DonationModule) -> None:
    """Refresh Rush controls when their current prices or availability change."""
    now = datetime.now(timezone.utc)
    for channel_id in await module.donations.get_channels(guild=module.guild):
        configuration = await module.donations.get_channel(
            guild=module.guild, channel_id=channel_id
        )
        donation_type = await module.donations.get_type(
            guild=module.guild, channel_id=channel_id
        )
        if (
            configuration is None
            or donation_type is None
            or donation_type.kind != "time_reduction"
        ):
            continue
        summary = await module.donations.get_summary(
            guild=module.guild,
            channel_id=channel_id,
            cycle=configuration.current_cycle,
        )
        if summary is None:
            continue
        rush_prices = (
            rush_donation_prices(
                started_at=configuration.rush_start_at,
                now=now,
                accelerated_hours=summary.time_reduction_hours,
                target_at=configuration.target_at,
            )
            if configuration.rush_start_at is not None
            else {}
        )
        rush_open = configuration.donations_enabled and bool(rush_prices)
        rush_state = (
            rush_open,
            configuration.donations_enabled,
            tuple(rush_prices.get(hours) for hours in RUSH_BUTTON_DURATIONS_HOURS),
        )
        if module._rush_view_states.get(channel_id) != rush_state:
            if not await module.compose_overview(channel_id):
                _logger.error(
                    "%s Failed to refresh Rush overview in channel %s "
                    "after a price or availability change.",
                    module.guild.name,
                    channel_id,
                )
