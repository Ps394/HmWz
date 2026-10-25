from types import SimpleNamespace
from datetime import datetime, timezone
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import discord
import pytest

from hmwz.modules.donation.commands import DonationGroup
from hmwz.modules.donation.commands.reset import reset as donation_reset
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.repository import DonationType
from hmwz.modules.donation.views import (
    DonationAmountOptionButton,
    DonationAmountChoiceView,
    DonationOverviewView,
    DonationRecordButton,
    DonationRushConfirmationView,
    DonationTimeReductionButton,
    DonationTimeReductionView,
)
from hmwz.modules.donation.setup_views import (
    DONATION_TIMEZONES,
    DonationSetupButton,
    DonationSetupDraft,
    DonationSetupKindSelect,
    DonationSetupView,
    DonationExportChannelSelect,
    DonationExportChannelView,
    _save_setup,
    DonationTimezoneSelect,
    donation_setup_panel,
)
from hmwz.modules.donation.rush_pricing import (
    RUSH_BUTTON_DURATIONS_HOURS,
    RUSH_DURATIONS_HOURS,
    RUSH_PERIOD_DURATION,
)
from hmwz.modules.donation.repository import DEFAULT_DONATION_CHOICES


def test_donation_setup_is_a_direct_command() -> None:
    donation_group = DonationGroup()
    setup_command = donation_group.get_command("setup")

    assert setup_command is not None
    assert setup_command.name == "setup"
    assert not isinstance(setup_command, discord.app_commands.Group)
    assert (
        setup_command._locale_description.extras["key"] == "donation.setup.description"
    )
    assert donation_group.get_command("remove") is not None
    assert (
        donation_group.get_command("remove")._locale_description.extras["key"]
        == "donation.remove.description"
    )
    assert donation_group.get_command("delete") is None
    assert donation_group.get_command("record") is None
    assert donation_group.get_command("reset") is not None
    assert (
        donation_group.get_command("reset")._locale_description.extras["key"]
        == "donation.reset.description"
    )
    assert (
        donation_group._locale_description.extras["key"] == "donation.group.description"
    )


@pytest.mark.asyncio
async def test_reset_command_resolves_donation_module_at_runtime() -> None:
    guild = SimpleNamespace(id=123, locale="de")
    donation_type = DonationType(
        name="Simple donation",
        kind="simple",
        unit="Credits",
        input_mode="free",
        choices=(),
        time_reductions=(),
    )
    module = SimpleNamespace(
        guild=guild,
        donations=SimpleNamespace(
            get_channel=AsyncMock(return_value=SimpleNamespace()),
            get_type=AsyncMock(return_value=donation_type),
        ),
    )
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            guild=guild,
            channel_id=456,
            client=SimpleNamespace(module_manager=manager),
            user=SimpleNamespace(id=789),
            response=SimpleNamespace(send_message=AsyncMock()),
        ),
    )

    await donation_reset.callback(interaction)

    manager.get_module.assert_awaited_once_with(guild, DonationModule)
    interaction.response.send_message.assert_awaited_once()


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

    assert [
        button.action
        for button in view.children
        if isinstance(button, DonationSetupButton)
    ] == [
        "content",
        "start",
        "ranking",
        "visibility",
        "donations",
        "export",
        "save",
    ]
    timezone_selects = [
        item for item in view.children if isinstance(item, DonationTimezoneSelect)
    ]
    assert len(timezone_selects) == 1
    assert tuple(option.value for option in timezone_selects[0].options) == (
        DONATION_TIMEZONES
    )
    assert timezone_selects[0].placeholder == "Zeitzone auswählen"
    assert timezone_selects[0].options[1].label == "Berlin (Deutschland)"
    assert draft.time_reductions == tuple(f"{hours}h" for hours in RUSH_DURATIONS_HOURS)
    assert RUSH_BUTTON_DURATIONS_HOURS == (24, 8, 1)


def test_rush_setup_panel_shows_nine_day_stop_time() -> None:
    start = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    draft = DonationSetupDraft(
        module=cast(
            DonationModule, SimpleNamespace(guild=SimpleNamespace(locale="de"))
        ),
        channel_id=456,
        owner_id=789,
        kind="time_reduction",
        title="Rush",
        description="",
        unit="crystals",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
        goal_hours=216,
        recent_limit=20,
        show_ranking=True,
        rush_start_at=start,
    )
    interaction = cast(discord.Interaction, SimpleNamespace(locale="de"))

    panel = donation_setup_panel(draft, interaction)
    expected_stop = start + RUSH_PERIOD_DURATION

    assert expected_stop.strftime("%d.%m.%Y %H:%M UTC (+0000)") in panel
    assert start.strftime("%d.%m.%Y %H:%M UTC (+0000)") in panel
    assert "9 Tage (216 Stunden)" in panel
    assert "Rush-Ende" in panel
    assert "Zeitzone: UTC" in panel
    assert "Spenden annehmen: aktiviert" in panel
    assert "Spendenanzeige: aktiviert" in panel


@pytest.mark.asyncio
async def test_setup_can_toggle_donation_visibility_and_acceptance() -> None:
    draft = DonationSetupDraft(
        module=cast(
            DonationModule, SimpleNamespace(guild=SimpleNamespace(locale="de"))
        ),
        channel_id=456,
        owner_id=789,
        kind="simple",
        title="Overview",
        description="",
        unit="Credits",
        choices=(),
        time_reductions=(),
        goal_hours=None,
        recent_limit=20,
        show_ranking=True,
        rush_start_at=None,
    )
    view = DonationSetupView(draft)
    interaction = Mock(spec=discord.Interaction)
    interaction.response.edit_message = AsyncMock()

    for action in ("visibility", "donations", "ranking"):
        button = next(
            item
            for item in view.children
            if isinstance(item, DonationSetupButton) and item.action == action
        )
        await button.callback(interaction)

    assert not draft.show_donations
    assert not draft.donations_enabled
    assert not draft.show_ranking
    assert interaction.response.edit_message.await_count == 3


@pytest.mark.asyncio
async def test_setup_saves_json_export_channel_and_optional_charts() -> None:
    configure_donation = AsyncMock(return_value=True)
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=SimpleNamespace(locale="de"),
            donations=SimpleNamespace(get_history_units=AsyncMock(return_value=())),
            configure_donation=configure_donation,
        ),
    )
    draft = DonationSetupDraft(
        module=module,
        channel_id=456,
        owner_id=789,
        kind="simple",
        title="Overview",
        description="",
        unit="Credits",
        choices=(),
        time_reductions=(),
        goal_hours=None,
        recent_limit=20,
        show_ranking=False,
        rush_start_at=None,
        export_channel_id=987,
    )
    interaction = cast(discord.Interaction, SimpleNamespace(locale="de"))

    assert await _save_setup(draft, interaction)

    configure_donation.assert_awaited_once()
    assert configure_donation.await_args.kwargs["export_channel_id"] == 987
    assert configure_donation.await_args.kwargs["show_ranking"] is False


@pytest.mark.asyncio
async def test_setup_can_select_a_json_export_channel() -> None:
    export_channel = Mock(spec=discord.TextChannel)
    export_channel.id = 987
    export_channel.mention = "<#987>"
    export_channel.permissions_for.return_value = SimpleNamespace(
        send_messages=True,
        attach_files=True,
    )
    selected_channel = Mock(spec=discord.app_commands.AppCommandChannel)
    selected_channel.id = export_channel.id
    guild = SimpleNamespace(
        locale="de",
        get_channel=Mock(return_value=export_channel),
        me=Mock(spec=discord.Member),
    )
    draft = DonationSetupDraft(
        module=cast(DonationModule, SimpleNamespace(guild=guild)),
        channel_id=456,
        owner_id=789,
        kind="simple",
        title="Overview",
        description="",
        unit="Credits",
        choices=(),
        time_reductions=(),
        goal_hours=None,
        recent_limit=20,
        show_ranking=True,
        rush_start_at=None,
    )
    setup_view = DonationSetupView(draft)
    export_view = DonationExportChannelView(setup_view)
    select = next(
        item
        for item in export_view.children
        if isinstance(item, DonationExportChannelSelect)
    )
    interaction = SimpleNamespace(
        locale="de",
        response=SimpleNamespace(edit_message=AsyncMock()),
    )

    with patch.object(
        DonationExportChannelSelect,
        "values",
        new_callable=PropertyMock,
        return_value=[selected_channel],
    ):
        await select.callback(interaction)

    assert draft.export_channel_id == export_channel.id
    export_channel.permissions_for.assert_called_once_with(guild.me)
    interaction.response.edit_message.assert_awaited_once()
    assert (
        interaction.response.edit_message.await_args.kwargs["content"]
        .splitlines()[-1]
        .endswith("<#987>")
    )
    assert interaction.response.edit_message.await_args.kwargs["view"] is setup_view


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
    view = DonationOverviewView(
        module,
        456,
        donation_type,
        rush_prices={24: Decimal(667), 8: Decimal(223), 1: Decimal(28)},
    )

    assert all(
        isinstance(button, DonationTimeReductionButton) for button in view.children
    )
    assert [button.time_reduction for button in view.children] == [
        "24h",
        "8h",
        "1h",
    ]
    assert [button.label for button in view.children] == [
        "24h - 667 Kristalle",
        "8h - 223 Kristalle",
        "1h - 28 Kristalle",
    ]

    limited_view = DonationOverviewView(
        module,
        456,
        donation_type,
        rush_prices={8: Decimal(223), 1: Decimal(28)},
    )
    assert [button.time_reduction for button in limited_view.children] == ["8h", "1h"]

    interaction = Mock(spec=discord.Interaction)
    await view.children[0].callback(interaction)

    start_donation.assert_awaited_once_with(interaction, 456, time_reduction="24h")


@pytest.mark.asyncio
async def test_rush_duration_selection_replaces_the_selection_prompt() -> None:
    start_donation = AsyncMock()
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=SimpleNamespace(locale="de"), start_donation=start_donation
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
    view = DonationTimeReductionView(
        module,
        456,
        donation_type,
        {24: Decimal(667), 8: Decimal(223), 1: Decimal(28)},
    )
    interaction = Mock(spec=discord.Interaction)

    await view.children[0].callback(interaction)

    start_donation.assert_awaited_once_with(
        interaction,
        456,
        time_reduction="24h",
        replace_prompt=True,
    )


@pytest.mark.asyncio
async def test_confirmed_rush_donation_deletes_confirmation_message() -> None:
    record_rush_donation = AsyncMock(return_value=(True, True))
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=SimpleNamespace(locale="de"),
            record_rush_donation=record_rush_donation,
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
    view = DonationRushConfirmationView(
        module,
        456,
        donation_type,
        8,
        Decimal(223),
        1,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        789,
    )
    interaction = Mock(spec=discord.Interaction)
    interaction.response.defer = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    result_message = SimpleNamespace(delete=AsyncMock())
    interaction.followup.send = AsyncMock(return_value=result_message)
    confirm_button = next(
        button
        for button in view.children
        if button.custom_id == "donation_rush_confirm"
    )

    await confirm_button.callback(interaction)

    interaction.delete_original_response.assert_awaited_once()
    interaction.followup.send.assert_awaited_once_with(
        "Spende gespeichert; öffentliche Spendenmeldungen wurden aktualisiert.",
        ephemeral=True,
        wait=True,
    )
    result_message.delete.assert_awaited_once_with(delay=5)


@pytest.mark.asyncio
async def test_cancelled_rush_donation_deletes_confirmation_message() -> None:
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
    view = DonationRushConfirmationView(
        module,
        456,
        donation_type,
        8,
        Decimal(223),
        1,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        789,
    )
    interaction = Mock(spec=discord.Interaction)
    interaction.response.defer = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    cancel_button = next(
        button for button in view.children if button.custom_id == "donation_rush_cancel"
    )

    await cancel_button.callback(interaction)

    interaction.response.defer.assert_awaited_once()
    interaction.delete_original_response.assert_awaited_once()


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
async def test_disabled_donations_hide_simple_donation_button() -> None:
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

    view = DonationOverviewView(module, 456, donation_type, donations_enabled=False)

    assert view.children == []


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


@pytest.mark.asyncio
async def test_fixed_amount_selection_dismisses_its_prompt() -> None:
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
        choices=("100",),
        time_reductions=(),
    )
    view = DonationAmountChoiceView(module, 456, donation_type)
    interaction = Mock(spec=discord.Interaction)
    interaction.response.defer = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    result_message = SimpleNamespace(delete=AsyncMock())
    interaction.followup.send = AsyncMock(return_value=result_message)

    await view.children[0].callback(interaction)

    interaction.delete_original_response.assert_awaited_once()
    result_message.delete.assert_awaited_once_with(delay=5)
