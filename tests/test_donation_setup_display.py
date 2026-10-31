"""Donation setup embeds, timestamp input, and ranking defaults."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from hmwz.modules.donation.commands.setup.config.command import setup
from hmwz.modules.donation.commands.setup.config.configuration_message import (
    donation_setup_panel,
)
from hmwz.modules.donation.commands.setup.config.draft import DonationSetupDraft
from hmwz.modules.donation.commands.setup.config.view import (
    DonationSetupKindView,
    DonationSetupKindSelect,
    DonationSetupView,
    DonationSetupButton,
    DonationTimezoneSelect,
)
from hmwz.modules.donation.models import DonationChannel, DonationType
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.repositories import DonationRepository
from hmwz.modules.donation.type.rush.reset import DonationRushResetModal
from hmwz.modules.donation.type.rush.setup import (
    DonationRushStartModal,
    DonationRushTargetModal,
)
from hmwz.modules.donation.type.rush.pricing import rush_end_at
from hmwz.modules.donation.type.rush.validation import parse_rush_timestamp
from hmwz.sqlite_db import Database


@pytest.fixture
def draft() -> DonationSetupDraft:
    return DonationSetupDraft(
        module=cast(
            DonationModule, SimpleNamespace(guild=SimpleNamespace(locale="de"))
        ),
        channel_id=456,
        owner_id=789,
        kind="time_reduction",
        title="Rush",
        description="Support the guild",
        unit="crystals",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
        goal_hours=216,
        recent_limit=20,
        show_ranking=False,
        rush_start_at=datetime(2026, 10, 31, 12, tzinfo=UTC),
        accelerated_hours=50,
    )


@pytest.mark.parametrize(
    "value",
    [
        "1793448000",
        " <t:1793448000> ",
        "<t:1793448000:F>",
        "<t:1793448000:R>",
        "<t:1793448000:t>",
        "<t:1793448000:T>",
        "<t:1793448000:d>",
        "<t:1793448000:D>",
        "<t:1793448000:f>",
        "0",
        "-1",
    ],
)
def test_timestamp_input_accepts_discord_tokens_and_unix_seconds(value: str) -> None:
    timestamp = 0 if value == "0" else -1 if value == "-1" else 1793448000
    assert parse_rush_timestamp(value) == datetime.fromtimestamp(timestamp, UTC)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "tomorrow",
        "2026-10-31",
        "1793448000.5",
        "<t:1793448000:X>",
        "<t:1793448000:F> trailing",
        "99999999999999999999999999",
        "1793448000000",
    ],
)
def test_timestamp_input_rejects_invalid_or_out_of_range_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_rush_timestamp(value)


def test_embed_shows_content_accelerated_end_and_input_timezone(
    draft: DonationSetupDraft,
) -> None:
    embed = donation_setup_panel(
        draft, cast(discord.Interaction, SimpleNamespace(locale="de"))
    )
    fields = {field.name: field.value for field in embed.fields}
    assert embed.color == discord.Color.blurple()
    assert fields["Kanal"] == "<#456>"
    assert fields["Beschreibungstext (optional)"] == draft.description
    assert fields["Startzeit"] == discord.utils.format_dt(draft.rush_start_at, "F")
    assert fields["Endzeit"] == discord.utils.format_dt(
        draft.rush_start_at + timedelta(hours=216 - 50), "F"
    )
    assert fields["All-Time-Spendencharts"] == "deaktiviert"
    assert fields["Zeitzone der Zeiteingabe"].startswith("UTC\n")
    assert not any("Auswahlwerte" in name for name in fields)


def test_credit_embed_omits_rush_fields_and_respects_discord_limits(
    draft: DonationSetupDraft,
) -> None:
    draft.kind = "simple"
    draft.description = "a" * 4000
    draft.choices = ("10000", "100000")
    embed = donation_setup_panel(
        draft, cast(discord.Interaction, SimpleNamespace(locale="de"))
    )
    fields = {field.name: field.value for field in embed.fields}
    assert fields["Auswahlwerte (optional)"] == "10000\n100000"
    assert "Startzeit" not in fields
    assert "Endzeit" not in fields
    assert all(len(field.value) <= 1024 for field in embed.fields)
    assert len(embed) <= 6000


@pytest.mark.asyncio
async def test_target_modal_sets_highlights_clears_and_rejects_invalid_targets(
    draft: DonationSetupDraft,
) -> None:
    view = DonationSetupView(draft)
    view.refresh = AsyncMock()
    interaction = cast(discord.Interaction, SimpleNamespace(locale="de"))
    target = rush_end_at(draft.rush_start_at, 51)
    modal = DonationRushTargetModal(view)
    modal.target_input._value = discord.utils.format_dt(target, "F")
    await modal.on_submit(interaction)
    assert draft.target_at == target
    embed = donation_setup_panel(draft, interaction)
    field = next(f for f in embed.fields if f.name == "ZIELZEIT")
    assert field.inline is False and field.value.startswith("**<t:")
    draft.accelerated_hours = 51
    assert "Ziel erreicht" in next(
        f.value
        for f in donation_setup_panel(draft, interaction).fields
        if f.name == "ZIELZEIT"
    )
    modal.target_input._value = discord.utils.format_dt(
        target + timedelta(minutes=30), "F"
    )
    with patch(
        "hmwz.modules.donation.type.rush.setup.send_temporary_response",
        new_callable=AsyncMock,
    ) as notify:
        await modal.on_submit(interaction)
    notify.assert_awaited_once()
    assert draft.target_at == target
    modal.target_input._value = ""
    await modal.on_submit(interaction)
    assert draft.target_at is None


@pytest.mark.asyncio
async def test_reset_accepts_an_optional_new_target(draft: DonationSetupDraft) -> None:
    module = Mock(spec=DonationModule)
    module.guild = draft.module.guild
    module.reset_cycle = AsyncMock(return_value=(True, True, False))
    modal = DonationRushResetModal(module, 456, 789)
    start = draft.rush_start_at
    target = rush_end_at(start, 24)
    modal.timestamp_input._value = discord.utils.format_dt(start, "F")
    modal.target_input._value = discord.utils.format_dt(target, "F")
    interaction = Mock(spec=discord.Interaction)
    interaction.user.id = 789
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock(
        return_value=SimpleNamespace(delete=AsyncMock())
    )
    await modal.on_submit(interaction)
    module.reset_cycle.assert_awaited_once_with(
        456, rush_start_at=start, target_at=target
    )


@pytest.mark.asyncio
async def test_toggle_refreshes_button_labels_and_clears_old_content(
    draft: DonationSetupDraft,
) -> None:
    view = DonationSetupView(draft)
    interaction = Mock(spec=discord.Interaction)
    interaction.response.edit_message = AsyncMock()
    await view.handle_action(interaction, "ranking")
    button = next(
        item
        for item in view.children
        if isinstance(item, DonationSetupButton) and item.action == "ranking"
    )
    assert button.label == "All-Time-Charts ausblenden"
    response = interaction.response.edit_message.await_args.kwargs
    assert response["content"] is None
    assert isinstance(response["embed"], discord.Embed)
    await view.handle_action(interaction, "ranking")
    button = next(
        item
        for item in view.children
        if isinstance(item, DonationSetupButton) and item.action == "ranking"
    )
    assert button.label == "All-Time-Charts einblenden"


@pytest.mark.asyncio
async def test_setup_start_modal_uses_single_timestamp_input(
    draft: DonationSetupDraft,
) -> None:
    view = DonationSetupView(draft)
    modal = DonationRushStartModal(view)
    assert len(modal.children) == 1
    assert modal.timestamp_input.default == "2026-10-31 12:00"
    modal.timestamp_input._value = modal.timestamp_input.default
    assert modal.timestamp_input.parse() == draft.rush_start_at
    modal.timestamp_input._value = "<t:1793448000:F>"
    view.refresh = AsyncMock()
    interaction = Mock(spec=discord.Interaction)
    await modal.on_submit(interaction)
    assert draft.rush_start_at == datetime.fromtimestamp(1793448000, UTC)
    view.refresh.assert_awaited_once_with(interaction)


@pytest.mark.asyncio
async def test_reset_start_modal_uses_the_same_timestamp_parser(
    draft: DonationSetupDraft,
) -> None:
    module = Mock(spec=DonationModule)
    module.guild = draft.module.guild
    module.reset_cycle = AsyncMock(return_value=(True, True, False))
    modal = DonationRushResetModal(module, 456, 789)
    assert len(modal.children) == 2
    modal.timestamp_input._value = "1793448000"
    interaction = Mock(spec=discord.Interaction)
    interaction.user.id = 789
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock(
        return_value=SimpleNamespace(delete=AsyncMock())
    )
    await modal.on_submit(interaction)
    module.reset_cycle.assert_awaited_once_with(
        456, rush_start_at=datetime.fromtimestamp(1793448000, UTC), target_at=None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("reset", [False, True])
@pytest.mark.parametrize("minutes", ["00", "57"])
async def test_unpadded_target_date_in_reset_and_setup(
    draft: DonationSetupDraft, reset: bool, minutes: str
) -> None:
    draft.rush_start_at = datetime(2026, 10, 31, 10, 57, tzinfo=UTC)
    draft.accelerated_hours = 0
    interaction = Mock(spec=discord.Interaction)
    interaction.user.id = 789
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock(
        return_value=SimpleNamespace(delete=AsyncMock())
    )
    if reset:
        module = Mock(spec=DonationModule)
        module.guild = draft.module.guild
        module.reset_cycle = AsyncMock(return_value=(True, True, False))
        modal = DonationRushResetModal(module, 456, 789)
        modal.timestamp_input._value = "2026-10-31 10:57"
        notify_path = "hmwz.modules.donation.type.rush.reset._send_temporary_response"
    else:
        view = DonationSetupView(draft)
        view.refresh = AsyncMock()
        modal = DonationRushTargetModal(view)
        notify_path = "hmwz.modules.donation.type.rush.setup.send_temporary_response"
    modal.target_input._value = f"2026-11-3 22:{minutes}"
    with patch(notify_path, new_callable=AsyncMock) as notify:
        await modal.on_submit(interaction)
    notify.assert_not_awaited()
    target = datetime(2026, 11, 3, 22, 57, tzinfo=UTC)
    if reset:
        module.reset_cycle.assert_awaited_once_with(
            456, rush_start_at=draft.rush_start_at, target_at=target
        )
    else:
        assert draft.target_at == target
        view.refresh.assert_awaited_once_with(interaction)


@pytest.mark.asyncio
async def test_start_change_rounds_existing_target_on_new_grid(
    draft: DonationSetupDraft,
) -> None:
    draft.accelerated_hours = 0
    draft.target_at = datetime(2026, 11, 3, 22, tzinfo=UTC)
    view = DonationSetupView(draft)
    view.refresh = AsyncMock()
    modal = DonationRushStartModal(view)
    modal.timestamp_input._value = "2026-10-31 10:57"
    await modal.on_submit(Mock(spec=discord.Interaction))
    assert draft.rush_start_at == datetime(2026, 10, 31, 10, 57, tzinfo=UTC)
    assert draft.target_at == datetime(2026, 11, 3, 22, 57, tzinfo=UTC)
    view.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_timestamp_notifies_without_saving(
    draft: DonationSetupDraft,
) -> None:
    view = DonationSetupView(draft)
    modal = DonationRushStartModal(view)
    modal.timestamp_input._value = "not a timestamp"
    view.refresh = AsyncMock()
    original = draft.rush_start_at
    with patch(
        "hmwz.modules.donation.type.rush.setup.send_temporary_response",
        new_callable=AsyncMock,
    ) as notify:
        await modal.on_submit(Mock(spec=discord.Interaction))
    notify.assert_awaited_once()
    view.refresh.assert_not_awaited()
    assert draft.rush_start_at == original


@pytest.mark.asyncio
async def test_timezone_selection_changes_input_zone_not_saved_instants(
    draft: DonationSetupDraft,
) -> None:
    view = DonationSetupView(draft)
    interaction = Mock(spec=discord.Interaction)
    interaction.response.edit_message = AsyncMock()
    start = draft.rush_start_at
    draft.target_at = rush_end_at(start, 51)
    target = draft.target_at
    select = next(
        item for item in view.children if isinstance(item, DonationTimezoneSelect)
    )
    assert len(select.options) <= 25
    assert next(option.value for option in select.options if option.default) == "UTC"
    select._values = ["Europe/Berlin"]
    await select.callback(interaction)
    assert draft.timezone_name == "Europe/Berlin"
    assert draft.rush_start_at == start and draft.target_at == target
    modal = DonationRushStartModal(view)
    assert modal.timestamp_input.default == "2026-10-31 13:00"
    modal.timestamp_input._value = "31.10.2026 14:00"
    await modal.on_submit(interaction)
    assert draft.rush_start_at == datetime(2026, 10, 31, 13, tzinfo=UTC)
    assert draft.target_at == target
    current = next(
        item for item in view.children if isinstance(item, DonationTimezoneSelect)
    )
    assert (
        next(option.value for option in current.options if option.default)
        == "Europe/Berlin"
    )
    fields = interaction.response.edit_message.await_args.kwargs["embed"].fields
    assert next(
        f.value for f in fields if f.name == "Zeitzone der Zeiteingabe"
    ).startswith("Europe/Berlin\n")


@pytest.mark.asyncio
async def test_stored_custom_timezone_is_preserved_in_setup(
    draft: DonationSetupDraft,
) -> None:
    draft.timezone_name = "UTC+1"
    view = DonationSetupView(draft)
    select = next(
        item for item in view.children if isinstance(item, DonationTimezoneSelect)
    )
    assert next(option.value for option in select.options if option.default) == "UTC+1"
    assert DonationRushStartModal(view).timestamp_input.default == "2026-10-31 13:00"


@pytest.mark.asyncio
async def test_timezone_and_parsed_instants_survive_save_and_reopening(
    tmp_path: Path,
) -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="Test", locale="de"))
    repository = DonationRepository(
        Database(folder=str(tmp_path), filename="timezones.db")
    )
    assert await repository.ensure_schema()
    module = cast(DonationModule, SimpleNamespace(guild=guild))
    interaction = cast(discord.Interaction, SimpleNamespace(locale="de"))
    selector = DonationSetupKindSelect(module, 456, 789, None, None)
    draft = selector.create_draft("time_reduction", interaction)
    assert draft.rush_start_at.second == draft.rush_start_at.microsecond == 0
    draft.timezone_name = "Europe/Berlin"
    view = DonationSetupView(draft)
    view.refresh = AsyncMock()
    start_modal = DonationRushStartModal(view)
    start_modal.timestamp_input._value = "31.10.2026 12:00"
    await start_modal.on_submit(interaction)
    target_modal = DonationRushTargetModal(view)
    target_modal.target_input._value = "08.11.2026 12:00"
    await target_modal.on_submit(interaction)
    assert await repository.configure_channel(
        guild=guild,
        channel_id=456,
        title="Rush",
        description="",
        timezone_name=draft.timezone_name,
        rush_start_at=draft.rush_start_at,
        target_at=draft.target_at,
    )
    stored = await repository.get_channel(guild=guild, channel_id=456)
    assert stored is not None
    reopened = DonationSetupKindSelect(module, 456, 789, stored, None).create_draft(
        "time_reduction",
        interaction,
    )
    assert reopened.timezone_name == "Europe/Berlin"
    assert reopened.rush_start_at == datetime(2026, 10, 31, 11, tzinfo=UTC)
    assert reopened.target_at == datetime(2026, 11, 8, 11, tzinfo=UTC)
    reset_modal = DonationRushResetModal(Mock(guild=guild), 456, 789, "Europe/Berlin")
    reset_modal.timestamp_input._value = reset_modal.timestamp_input.default
    suggested = reset_modal.timestamp_input.parse()
    assert suggested is not None and suggested.second == suggested.microsecond == 0


@pytest.mark.asyncio
async def test_reset_command_uses_configured_timezone_and_local_input(
    draft: DonationSetupDraft,
) -> None:
    from hmwz.modules.donation.commands.reset import reset

    module = Mock(spec=DonationModule)
    module.guild = draft.module.guild
    module.donations = Mock(spec=DonationRepository)
    module.donations.get_channel = AsyncMock(
        return_value=SimpleNamespace(timezone_name="Europe/Berlin")
    )
    module.donations.get_type = AsyncMock(
        return_value=SimpleNamespace(kind="time_reduction")
    )
    module.reset_cycle = AsyncMock(return_value=(True, True, False))
    interaction = Mock(spec=discord.Interaction)
    interaction.guild = module.guild
    interaction.channel_id = 456
    interaction.user.id = 789
    interaction.client = SimpleNamespace(
        module_manager=SimpleNamespace(get_module=AsyncMock(return_value=module))
    )
    interaction.response.send_modal = AsyncMock()
    await reset.callback(interaction)
    modal = interaction.response.send_modal.await_args.args[0]
    assert (
        modal.timestamp_input.timezone_name
        == modal.target_input.timezone_name
        == "Europe/Berlin"
    )
    modal.timestamp_input._value = "31.10.2026 12:00"
    modal.target_input._value = "08.11.2026 12:00"
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock(
        return_value=SimpleNamespace(delete=AsyncMock())
    )
    await modal.on_submit(interaction)
    module.reset_cycle.assert_awaited_once_with(
        456,
        rush_start_at=datetime(2026, 10, 31, 11, tzinfo=UTC),
        target_at=datetime(2026, 11, 8, 11, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_new_ranking_defaults_and_existing_settings_survive_sync(
    tmp_path: Path,
) -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="Test", locale="de"))
    repository = DonationRepository(
        Database(folder=str(tmp_path), filename="defaults.db")
    )
    assert await repository.ensure_schema()
    for channel_id, options in [(456, {}), (457, {"show_ranking": True})]:
        assert await repository.configure_channel(
            guild=guild,
            channel_id=channel_id,
            title="Donations",
            description="",
            **options,
        )
    assert await repository.ensure_schema()
    assert not (await repository.get_channel(guild=guild, channel_id=456)).show_ranking
    assert (await repository.get_channel(guild=guild, channel_id=457)).show_ranking
    columns = await repository.database.fetch_all(
        "PRAGMA table_info(Donation_Channels)"
    )
    assert (
        next(row for row in columns if row["name"] == "ShowRanking")["dflt_value"]
        == "0"
    )


def test_draft_defaults_disable_charts_but_preserve_existing_choice(
    draft: DonationSetupDraft,
) -> None:
    selector = DonationSetupKindSelect(draft.module, 456, 789, None, None)
    interaction = cast(discord.Interaction, SimpleNamespace(locale="de"))
    assert not selector.create_draft("simple", interaction).show_ranking
    assert not selector.create_draft("time_reduction", interaction).show_ranking
    selector.channel_configuration = DonationChannel(
        channel_id=456,
        overview_message_id=None,
        ranking_message_id=None,
        title="Existing",
        description="",
        goal_hours=None,
        show_ranking=True,
    )
    assert selector.create_draft("simple", interaction).show_ranking


@pytest.mark.asyncio
async def test_setup_command_sends_embed_with_current_cycle_time_savings(
    draft: DonationSetupDraft,
) -> None:
    channel = Mock(spec=discord.TextChannel)
    channel.id = 456
    module = Mock(spec=DonationModule)
    module.guild = draft.module.guild
    module.sync = AsyncMock(return_value=True)
    module.donations = SimpleNamespace(
        get_channel=AsyncMock(
            return_value=DonationChannel(
                channel_id=456,
                overview_message_id=None,
                ranking_message_id=None,
                title="Rush",
                description="",
                goal_hours=216,
                rush_start_at=draft.rush_start_at,
            )
        ),
        get_type=AsyncMock(
            return_value=DonationType(
                "Rush", "time_reduction", "crystals", "free", (), ("1h", "8h", "24h")
            )
        ),
        get_summary=AsyncMock(return_value=SimpleNamespace(time_reduction_hours=50)),
    )
    interaction = Mock(spec=discord.Interaction)
    interaction.guild = module.guild
    interaction.channel = channel
    interaction.user.id = 789
    interaction.client = SimpleNamespace(
        module_manager=SimpleNamespace(get_module=AsyncMock(return_value=module))
    )
    interaction.response.send_message = AsyncMock()
    await setup.callback(interaction)
    response = interaction.response.send_message.await_args.kwargs
    assert "content" not in response
    assert response["view"].draft.accelerated_hours == 50
    assert isinstance(response["embed"], discord.Embed)


@pytest.mark.asyncio
async def test_new_setup_command_also_uses_an_embed(draft: DonationSetupDraft) -> None:
    channel = Mock(spec=discord.TextChannel)
    channel.id = 456
    channel.mention = "<#456>"
    module = Mock(spec=DonationModule)
    module.guild = draft.module.guild
    module.sync = AsyncMock(return_value=True)
    module.donations = SimpleNamespace(
        get_channel=AsyncMock(return_value=None),
        get_type=AsyncMock(return_value=None),
    )
    interaction = Mock(spec=discord.Interaction)
    interaction.guild = draft.module.guild
    interaction.channel = channel
    interaction.user.id = 789
    interaction.client = SimpleNamespace(
        module_manager=SimpleNamespace(get_module=AsyncMock(return_value=module))
    )
    interaction.response.send_message = AsyncMock()
    await setup.callback(interaction)
    response = interaction.response.send_message.await_args.kwargs
    assert "content" not in response
    assert response["embed"].fields[0].value == "<#456>"
    assert isinstance(response["view"], DonationSetupKindView)


@pytest.mark.asyncio
async def test_export_prompt_clears_setup_embed(draft: DonationSetupDraft) -> None:
    view = DonationSetupView(draft)
    interaction = Mock(spec=discord.Interaction)
    interaction.response.edit_message = AsyncMock()
    await view.handle_action(interaction, "export")
    response = interaction.response.edit_message.await_args.kwargs
    assert response["embed"] is None
    assert isinstance(response["content"], str)


@pytest.mark.asyncio
async def test_legacy_schema_missing_ranking_column_defaults_to_disabled(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="legacy.db")
    assert await database.execute(
        """
        CREATE TABLE Donation_Channels (
            Guild INTEGER NOT NULL, Channel INTEGER NOT NULL, Message INTEGER,
            PRIMARY KEY (Guild, Channel)
        )
        """
    )
    assert await database.execute(
        "INSERT INTO Donation_Channels (Guild, Channel) VALUES (123, 456)"
    )
    repository = DonationRepository(database)
    assert await repository.ensure_schema()
    configuration = await repository.get_channel(
        guild=cast(discord.Guild, SimpleNamespace(id=123)), channel_id=456
    )
    assert configuration is not None
    assert not configuration.show_ranking
