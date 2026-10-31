"""Regression tests for the separated credit and Rush workflows."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.modules.donation.commands.reset import reset
from hmwz.modules.donation.commands.setup.config.draft import DonationSetupDraft
from hmwz.modules.donation.commands.setup.config.view import DonationSetupView
from hmwz.modules.donation.models import DonationChannel, DonationKind, DonationType
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.repositories import DonationRepository
from hmwz.modules.donation.type.credit.reset import DonationCycleResetView
from hmwz.modules.donation.type.credit.setup import DonationValuesModal
from hmwz.modules.donation.type.credit.views import (
    DonationAmountChoiceView,
    DonationAmountModal,
)
from hmwz.modules.donation.type.rush.reset import DonationRushResetModal
from hmwz.modules.donation.type.rush.service import refresh_overviews
from hmwz.modules.donation.type.rush.pricing import rush_end_at
from hmwz.modules.donation.type.rush.setup import DonationRushStartModal
from hmwz.modules.donation.type.rush.views import (
    DonationRushConfirmationView,
    DonationTimeReductionView,
)


@pytest.fixture
def module() -> Mock:
    module = Mock(spec=DonationModule)
    module.guild = Mock(spec=discord.Guild)
    module.guild.id = 123
    module.guild.name = "Test guild"
    module.guild.locale = "de"
    module.donations = Mock(spec=DonationRepository)
    module.donations.get_channels = AsyncMock(return_value=(456,))
    module.donations.get_channel = AsyncMock(
        return_value=DonationChannel(
            channel_id=456,
            overview_message_id=None,
            ranking_message_id=None,
            title="Donations",
            description="",
            goal_hours=216,
            rush_start_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    module.donations.get_summary = AsyncMock(return_value=Mock(time_reduction_hours=50))
    module.compose_overview = AsyncMock(return_value=True)
    module._rush_view_states = {}
    return module


@pytest.fixture
def interaction(module: Mock) -> Mock:
    interaction = Mock(spec=discord.Interaction)
    interaction.guild = module.guild
    interaction.channel_id = 456
    interaction.user = Mock(spec=discord.Member)
    interaction.user.id = 789
    interaction.client = Mock(
        module_manager=Mock(get_module=AsyncMock(return_value=module))
    )
    interaction.response = Mock(
        send_message=AsyncMock(),
        send_modal=AsyncMock(),
        edit_message=AsyncMock(),
    )
    interaction.original_response = AsyncMock()
    return interaction


def configured_type(kind: DonationKind, *, choices: bool = False) -> DonationType:
    return DonationType(
        name="Donation",
        kind=kind,
        unit="Credits" if kind == "simple" else "crystals",
        input_mode="choice" if choices else "free",
        choices=("10000", "100000") if choices else (),
        time_reductions=("1h", "8h", "24h") if kind == "time_reduction" else (),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("choices", [False, True])
async def test_credit_start_uses_only_credit_input(
    module: Mock, interaction: Mock, choices: bool
) -> None:
    module.donations.get_type = AsyncMock(
        return_value=configured_type("simple", choices=choices)
    )
    await DonationModule.start_donation(module, interaction, 456)
    if choices:
        view = interaction.response.send_message.await_args.kwargs["view"]
        assert isinstance(view, DonationAmountChoiceView)
        assert [button.custom_id for button in view.children] == [
            "donation:amount:456:0",
            "donation:amount:456:1",
        ]
        interaction.response.send_modal.assert_not_awaited()
    else:
        modal = interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, DonationAmountModal)
        interaction.response.send_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("replace_prompt", [False, True])
async def test_rush_start_uses_updated_price_in_rush_confirmation(
    module: Mock, interaction: Mock, replace_prompt: bool
) -> None:
    module.donations.get_type = AsyncMock(
        return_value=configured_type("time_reduction")
    )
    await DonationModule.start_donation(
        module,
        interaction,
        456,
        time_reduction="8h",
        replace_prompt=replace_prompt,
    )
    response = (
        interaction.response.edit_message
        if replace_prompt
        else interaction.response.send_message
    )
    view = response.await_args.kwargs["view"]
    assert isinstance(view, DonationRushConfirmationView)
    assert view.amount == Decimal(223)
    assert view.duration_hours == 8
    assert view.expected_cycle == 1
    interaction.response.send_modal.assert_not_awaited()


@pytest.mark.asyncio
async def test_rush_start_without_duration_offers_only_rush_buttons(
    module: Mock, interaction: Mock
) -> None:
    module.donations.get_type = AsyncMock(
        return_value=configured_type("time_reduction")
    )
    await DonationModule.start_donation(module, interaction, 456)
    view = interaction.response.send_message.await_args.kwargs["view"]
    assert isinstance(view, DonationTimeReductionView)
    assert [button.custom_id for button in view.children] == [
        "donation:time:456:24",
        "donation:time:456:8",
        "donation:time:456:1",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("remaining", "expected"), [(24, [24, 8, 1]), (8, [8, 1]), (1, [1]), (0, [])]
)
async def test_rush_target_caps_accessible_buttons_and_maintenance(
    module: Mock,
    interaction: Mock,
    remaining: int,
    expected: list[int],
) -> None:
    configuration = module.donations.get_channel.return_value
    module.donations.get_channel.return_value = replace(
        configuration,
        target_at=rush_end_at(configuration.rush_start_at, 50 + remaining),
    )
    module.donations.get_type = AsyncMock(
        return_value=configured_type("time_reduction")
    )
    await DonationModule.start_donation(module, interaction, 456)
    view = interaction.response.send_message.await_args.kwargs.get("view")
    if expected:
        assert isinstance(view, DonationTimeReductionView)
        assert [button.custom_id for button in view.children] == [
            f"donation:time:456:{hours}" for hours in expected
        ]
    else:
        assert view is None
    prices = {24: Decimal(723), 8: Decimal(223), 1: Decimal(28)}
    module._rush_view_states[456] = (
        bool(expected),
        True,
        tuple(prices[hours] if hours in expected else None for hours in (24, 8, 1)),
    )
    await refresh_overviews(module)
    module.compose_overview.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["simple", "time_reduction"])
async def test_shared_setup_opens_the_type_specific_modal(
    module: Mock, interaction: Mock, kind: DonationKind
) -> None:
    draft = DonationSetupDraft(
        module=module,
        channel_id=456,
        owner_id=789,
        kind=kind,
        title="Donations",
        description="",
        unit="Credits",
        choices=(),
        time_reductions=(),
        goal_hours=None,
        recent_limit=20,
        show_ranking=True,
        rush_start_at=None,
    )
    setup = DonationSetupView(draft)
    action = "values" if kind == "simple" else "start"
    await setup.handle_action(interaction, action)
    modal = interaction.response.send_modal.await_args.args[0]
    expected_class = DonationValuesModal if kind == "simple" else DonationRushStartModal
    assert isinstance(modal, expected_class)
    assert modal.setup_view is setup
    assert modal.draft is draft


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["simple", "time_reduction"])
async def test_reset_command_routes_to_the_type_specific_dialog(
    module: Mock, interaction: Mock, kind: DonationKind
) -> None:
    module.donations.get_type = AsyncMock(return_value=configured_type(kind))
    await reset.callback(interaction)
    if kind == "simple":
        dialog = interaction.response.send_message.await_args.kwargs["view"]
        assert isinstance(dialog, DonationCycleResetView)
        interaction.response.send_modal.assert_not_awaited()
    else:
        dialog = interaction.response.send_modal.await_args.args[0]
        assert isinstance(dialog, DonationRushResetModal)
        interaction.response.send_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_rush_maintenance_only_refreshes_changed_prices(
    module: Mock, changed: bool
) -> None:
    module.donations.get_type = AsyncMock(
        return_value=configured_type("time_reduction")
    )
    if not changed:
        module._rush_view_states[456] = (
            True,
            True,
            (Decimal(723), Decimal(223), Decimal(28)),
        )
    await refresh_overviews(module)
    if changed:
        module.compose_overview.assert_awaited_once_with(456)
    else:
        module.compose_overview.assert_not_awaited()


@pytest.mark.asyncio
async def test_rush_maintenance_does_not_refresh_credit_channels(module: Mock) -> None:
    module.donations.get_type = AsyncMock(return_value=configured_type("simple"))
    await refresh_overviews(module)
    module.compose_overview.assert_not_awaited()
    module.donations.get_summary.assert_not_awaited()
