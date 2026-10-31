"""Confirmation, replacement, and credit presentation regressions."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from hmwz.client import Client
from hmwz.modules.donation.models import DonationChannel, DonationSummary, DonationType
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.overview import DonationOverview
from hmwz.modules.donation.repositories import DonationRepository
from hmwz.modules.donation.type.credit import service as credit_service
from hmwz.modules.donation.type.credit.views import (
    DonationAmountModal,
    DonationAmountOptionButton,
    DonationCreditConfirmationView,
)
from hmwz.modules.donation.type.rush.pricing import validate_rush_target
from hmwz.modules.donation.type.rush.views import DonationRushConfirmationView
from hmwz.sqlite_db import Database


@pytest.fixture
def module(tmp_path: Path) -> DonationModule:
    guild = Mock(spec=discord.Guild, id=123, locale="de")
    client = Mock(spec=Client)
    client._database = Database(folder=str(tmp_path), filename="confirm.db")
    module = DonationModule(guild, client)
    module.donations.get_channel = AsyncMock(
        return_value=DonationChannel(
            channel_id=456,
            overview_message_id=None,
            ranking_message_id=None,
            title="Credits",
            description="",
            goal_hours=None,
        )
    )
    module.record_donation = AsyncMock(return_value=(True, True))
    module.record_rush_donation = AsyncMock(return_value=(True, True))
    return module


@pytest.fixture
def interaction(module: DonationModule) -> Mock:
    interaction = Mock(spec=discord.Interaction)
    interaction.guild = module.guild
    interaction.user = Mock(spec=discord.Member, id=789)
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    interaction.original_response = AsyncMock(
        return_value=Mock(spec=discord.Message, delete=AsyncMock())
    )
    interaction.followup.send = AsyncMock(
        return_value=Mock(spec=discord.Message, delete=AsyncMock())
    )
    return interaction


@pytest.fixture
def credit_type() -> DonationType:
    return DonationType("Credits", "simple", "Credits", "free", (), ())


@pytest.mark.asyncio
@pytest.mark.parametrize("modal", [False, True])
async def test_credit_requires_confirmation(
    module: DonationModule, interaction: Mock, credit_type: DonationType, modal: bool
) -> None:
    if modal:
        view = DonationAmountModal(module, 456, credit_type)
        view.amount_input._value = "100000"
        await view.on_submit(interaction)
    else:
        button = DonationAmountOptionButton(
            module, 456, credit_type, Decimal(100000), 0
        )
        await button.callback(interaction)
    module.record_donation.assert_not_awaited()
    confirmation = module._pending_donations[789]
    assert isinstance(confirmation, DonationCreditConfirmationView)
    assert "100.000 Credits" in interaction.response.send_message.await_args.args[0]
    await confirmation.children[0].callback(interaction)
    module.record_donation.assert_awaited_once_with(
        interaction,
        456,
        credit_type,
        Decimal(100000),
        time_reduction=None,
        expected_cycle=1,
    )
    assert not module._pending_donations
    interaction.delete_original_response.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("rush_first", [False, True])
async def test_new_confirmation_invalidates_previous_even_across_channels(
    module: DonationModule,
    interaction: Mock,
    credit_type: DonationType,
    rush_first: bool,
) -> None:
    if rush_first:
        first = DonationRushConfirmationView(
            module,
            1234,
            DonationType(
                "Rush", "time_reduction", "crystals", "choice", (), ("1h", "8h", "24h")
            ),
            8,
            Decimal(223),
            1,
            datetime.now(UTC),
            datetime.now(UTC),
            789,
        )
    else:
        first = DonationCreditConfirmationView(
            module, 1234, credit_type, Decimal(10), 1, 789
        )
    second = DonationCreditConfirmationView(
        module, 456, credit_type, Decimal(20), 1, 789
    )
    await module.show_donation_confirmation(interaction, first, "first")
    old_message = first.message
    await module.show_donation_confirmation(interaction, second, "second")
    assert first.is_finished()
    old_message.delete.assert_awaited_once()
    assert module._pending_donations[789] is second
    with patch(
        "hmwz.modules.donation.confirmation.send_temporary_response",
        new_callable=AsyncMock,
    ) as response:
        await first.children[0].callback(interaction)
        response.assert_awaited_once()
    module.record_donation.assert_not_awaited()
    module.record_rush_donation.assert_not_awaited()


@pytest.mark.asyncio
async def test_parallel_confirmations_leave_only_latest_active(
    module: DonationModule, interaction: Mock, credit_type: DonationType
) -> None:
    first = DonationCreditConfirmationView(module, 456, credit_type, Decimal(1), 1, 789)
    second = DonationCreditConfirmationView(
        module, 456, credit_type, Decimal(2), 1, 789
    )
    await asyncio.gather(
        module.show_donation_confirmation(interaction, first, "first"),
        module.show_donation_confirmation(interaction, second, "second"),
    )
    assert first.is_finished()
    assert module._pending_donations[789] is second
    with patch(
        "hmwz.modules.donation.confirmation.send_temporary_response",
        new_callable=AsyncMock,
    ):
        await asyncio.gather(
            second.children[0].callback(interaction),
            second.children[0].callback(interaction),
        )
    module.record_donation.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel", "timeout", "restart"])
async def test_unconfirmed_donation_is_not_saved(
    module: DonationModule, interaction: Mock, credit_type: DonationType, action: str
) -> None:
    view = DonationCreditConfirmationView(module, 456, credit_type, Decimal(1), 1, 789)
    await module.show_donation_confirmation(interaction, view, "confirm")
    if action == "cancel":
        await view.children[1].callback(interaction)
    elif action == "timeout":
        await view.on_timeout()
    else:
        await module.clear_donation_confirmation(789)
    assert not module._pending_donations
    module.record_donation.assert_not_awaited()


@pytest.mark.asyncio
async def test_other_user_cannot_confirm(
    module: DonationModule, interaction: Mock, credit_type: DonationType
) -> None:
    view = DonationCreditConfirmationView(module, 456, credit_type, Decimal(1), 1, 789)
    await module.show_donation_confirmation(interaction, view, "confirm")
    interaction.user.id = 987
    with patch(
        "hmwz.modules.donation.confirmation.send_temporary_response",
        new_callable=AsyncMock,
    ):
        await view.children[0].callback(interaction)
    assert module._pending_donations[789] is view
    module.record_donation.assert_not_awaited()


def test_credit_overviews_do_not_show_times(
    module: DonationModule, credit_type: DonationType
) -> None:
    channel = DonationChannel(
        channel_id=456,
        overview_message_id=None,
        ranking_message_id=None,
        title="Credits",
        description="",
        goal_hours=None,
    )
    overview = DonationOverview.create_embed(module.guild, channel, rush_start_at=None)
    ranking = DonationOverview.create_ranking_embed(module.guild, credit_type, ())
    history = DonationOverview.create_history_embed(
        module.guild, credit_type, (), DonationSummary(2, 0)
    )
    assert history.title == "2 Spenden"
    assert all(embed.timestamp is None for embed in (overview, ranking, history))


@pytest.mark.parametrize("hours", [1, 24, 191, 192])
def test_requested_october_target_range_accepts_whole_hours(hours: int) -> None:
    start = datetime(2026, 10, 31, 10, tzinfo=UTC)
    validate_rush_target(start, start + timedelta(hours=hours))


@pytest.mark.parametrize("hours", [0, 192.5, 193, 216])
def test_requested_october_target_range_rejects_invalid_times(hours: float) -> None:
    start = datetime(2026, 10, 31, 10, tzinfo=UTC)
    with pytest.raises(ValueError):
        validate_rush_target(start, start + timedelta(hours=hours))


@pytest.mark.asyncio
@pytest.mark.parametrize("reset", [False, True])
async def test_credit_confirmation_uses_original_cycle_and_honors_stop(
    module: DonationModule, interaction: Mock, credit_type: DonationType, reset: bool
) -> None:
    module.donations = DonationRepository(module.database)
    assert await module.donations.ensure_schema()
    assert await module.donations.configure_channel(
        guild=module.guild, channel_id=456, title="Credits", description=""
    )
    assert await module.donations.configure_type(
        guild=module.guild, channel_id=456, donation_type=credit_type
    )
    if reset:
        assert await module.donations.reset_cycle(
            guild=module.guild, channel_id=456, rush_start_at=None
        )
    else:
        assert await module.donations.configure_channel(
            guild=module.guild,
            channel_id=456,
            title="Credits",
            description="",
            donations_enabled=False,
        )
    assert await credit_service.record_donation(
        module,
        interaction,
        456,
        credit_type,
        Decimal(100),
        time_reduction=None,
        expected_cycle=1,
    ) == (False, False)
    summary = await module.donations.get_summary(
        guild=module.guild, channel_id=456, cycle=2 if reset else 1
    )
    assert summary is not None and summary.donation_count == 0
