from types import SimpleNamespace
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.modules.donation.commands import DonationGroup
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.repository import DonationType
from hmwz.modules.donation.views import (
    DonationAmountOptionButton,
    DonationOverviewView,
    DonationRecordButton,
    DonationTimeReductionButton,
)
from hmwz.modules.donation.setup_views import (
    DonationSetupDraft,
    DonationSetupKindSelect,
    DonationSetupView,
)
from hmwz.modules.donation.rush_pricing import RUSH_DURATIONS_HOURS
from hmwz.modules.donation.repository import DEFAULT_DONATION_CHOICES


def test_donation_setup_is_a_direct_command() -> None:
    donation_group = DonationGroup()
    setup_command = donation_group.get_command("setup")

    assert setup_command is not None
    assert setup_command.name == "setup"
    assert not isinstance(setup_command, discord.app_commands.Group)
    assert donation_group.get_command("remove") is not None
    assert donation_group.get_command("delete") is not None
    assert donation_group.get_command("reset") is not None


@pytest.mark.asyncio
async def test_rush_setup_menu_splits_configuration_into_sections() -> None:
    draft = DonationSetupDraft(
        module=cast(
            DonationModule, SimpleNamespace(guild=SimpleNamespace(locale="de"))
        ),
        channel_id=456,
        owner_id=789,
        kind="time_reduction",
        title="Overview",
        description="",
        unit="crystals",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
        goal_hours=216,
        recent_limit=20,
        show_ranking=True,
        rush_start_at=None,
    )

    view = DonationSetupView(draft)

    assert [button.action for button in view.children] == [
        "content",
        "start",
        "recent",
        "ranking",
        "save",
    ]
    assert draft.time_reductions == tuple(f"{hours}h" for hours in RUSH_DURATIONS_HOURS)


@pytest.mark.asyncio
async def test_time_reduction_overview_buttons_select_reduction_before_donation() -> (
    None
):
    start_donation = AsyncMock()
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=SimpleNamespace(locale="de"),
            start_donation=start_donation,
        ),
    )
    donation_type = DonationType(
        name="Rush donation",
        kind="time_reduction",
        unit="crystals",
        input_mode="free",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
    )
    view = DonationOverviewView(module, 456, donation_type)

    assert all(
        isinstance(button, DonationTimeReductionButton) for button in view.children
    )
    assert [button.time_reduction for button in view.children] == [
        "1h",
        "8h",
        "24h",
    ]

    interaction = Mock(spec=discord.Interaction)
    await view.children[2].callback(interaction)

    start_donation.assert_awaited_once_with(interaction, 456, time_reduction="24h")


@pytest.mark.asyncio
async def test_closed_rush_overview_hides_donation_buttons() -> None:
    module = cast(
        DonationModule,
        SimpleNamespace(guild=SimpleNamespace(locale="de")),
    )
    donation_type = DonationType(
        name="Rush donation",
        kind="time_reduction",
        unit="crystals",
        input_mode="free",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
    )

    view = DonationOverviewView(
        module,
        456,
        donation_type,
        rush_open=False,
    )

    assert view.children == []


@pytest.mark.asyncio
async def test_simple_donation_overview_keeps_record_button() -> None:
    module = cast(
        DonationModule,
        SimpleNamespace(guild=SimpleNamespace(locale="de")),
    )
    donation_type = DonationType(
        name="Simple donation",
        kind="simple",
        unit="credits",
        input_mode="free",
        choices=(),
        time_reductions=(),
    )

    view = DonationOverviewView(module, 456, donation_type)

    assert len(view.children) == 1
    assert isinstance(view.children[0], DonationRecordButton)


@pytest.mark.asyncio
async def test_simple_donation_overview_shows_fixed_amount_buttons() -> None:
    module = cast(
        DonationModule,
        SimpleNamespace(guild=SimpleNamespace(locale="de")),
    )
    donation_type = DonationType(
        name="Simple donation",
        kind="simple",
        unit="Credits",
        input_mode="choice",
        choices=DEFAULT_DONATION_CHOICES,
        time_reductions=(),
    )

    view = DonationOverviewView(module, 456, donation_type)

    assert all(isinstance(button, discord.ui.Button) for button in view.children)
    assert [button.label for button in view.children] == [
        "10.000 Credits",
        "100.000 Credits",
        "1.000.000 Credits",
        "8.000.000 Credits",
    ]
    assert [button.custom_id for button in view.children] == [
        "donation:amount:456:0",
        "donation:amount:456:1",
        "donation:amount:456:2",
        "donation:amount:456:3",
    ]


def test_new_simple_setup_defaults_to_four_credit_choices() -> None:
    module = cast(
        DonationModule,
        SimpleNamespace(guild=SimpleNamespace(locale="de")),
    )
    select = DonationSetupKindSelect(
        module,
        456,
        789,
        channel_configuration=None,
        donation_type=None,
    )
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(locale="de"),
    )

    draft = select.create_draft("simple", interaction)

    assert draft.unit == "Credits"
    assert draft.choices == DEFAULT_DONATION_CHOICES


@pytest.mark.asyncio
async def test_credit_amount_button_records_its_fixed_value() -> None:
    record_donation = AsyncMock(return_value=(True, True))
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=SimpleNamespace(locale="de"),
            record_donation=record_donation,
        ),
    )
    donation_type = DonationType(
        name="Simple donation",
        kind="simple",
        unit="Credits",
        input_mode="choice",
        choices=DEFAULT_DONATION_CHOICES,
        time_reductions=(),
    )
    button = DonationAmountOptionButton(
        module,
        456,
        donation_type,
        Decimal("100000"),
        1,
    )
    interaction = Mock(spec=discord.Interaction)
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    await button.callback(interaction)

    record_donation.assert_awaited_once_with(
        interaction,
        456,
        donation_type,
        Decimal("100000"),
        time_reduction=None,
    )
    interaction.followup.send.assert_awaited_once()
