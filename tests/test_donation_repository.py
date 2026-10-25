from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from zoneinfo import ZoneInfo

import discord
import pytest

from hmwz.modules.donation.overview import DonationOverview
from hmwz.modules.donation.repository import (
    DonationRepository,
    DonationSummary,
    DonationType,
)
from hmwz.modules.donation.rush_pricing import (
    RUSH_DONATION_CUTOFF,
    RUSH_PERIOD_DURATION,
    rush_donation_cost,
)
from hmwz.modules.donation.validation import (
    parse_amount,
    parse_choices,
    parse_hours,
)
from hmwz.sqlite_db import Database


@pytest.mark.asyncio
async def test_donation_types_channels_and_entries_are_persisted(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="donations.db")
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))
    member = cast(
        discord.Member,
        SimpleNamespace(id=456, display_name="Donor One"),
    )
    now = datetime.now(timezone.utc)
    rush_start = now - timedelta(hours=68)
    donations = DonationRepository(database)

    assert await donations.ensure_schema()
    assert await donations.configure_channel(
        guild=guild,
        channel_id=789,
        title="Donations",
        description="Support the guild",
        goal_hours=216,
        rush_start_at=rush_start,
        timezone_name="America/New_York",
        show_donations=False,
        export_channel_id=321,
    )
    crystal_type = DonationType(
        name="Rush donation",
        kind="time_reduction",
        unit="crystals",
        input_mode="free",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
    )
    assert await donations.configure_type(
        guild=guild, channel_id=789, donation_type=crystal_type
    )
    assert await donations.configure_channel(
        guild=guild,
        channel_id=987,
        title="Credits",
        description="",
    )
    simple_type = DonationType(
        name="Simple donation",
        kind="simple",
        unit="credits",
        input_mode="free",
        choices=(),
        time_reductions=(),
    )
    assert await donations.configure_type(
        guild=guild, channel_id=987, donation_type=simple_type
    )
    assert await donations.get_channels(guild=guild) == (789, 987)
    assert await donations.get_type(guild=guild, channel_id=987) == simple_type
    assert await donations.set_message(guild=guild, channel_id=789, message_id=12345)
    assert await donations.set_message(
        guild=guild, channel_id=789, message_id=12346, ranking=True
    )
    assert await donations.set_message(
        guild=guild, channel_id=789, message_id=12347, history=True
    )
    channel = await donations.get_channel(guild=guild, channel_id=789)
    assert channel is not None
    assert channel.title == "Donations"
    assert channel.description == "Support the guild"
    assert channel.goal_hours == 216
    assert channel.overview_message_id == 12345
    assert channel.ranking_message_id == 12346
    assert channel.history_message_id == 12347
    assert channel.timezone_name == "America/New_York"
    assert not channel.show_donations
    assert channel.donations_enabled
    assert channel.export_channel_id == 321

    assert await donations.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=crystal_type,
        amount=rush_donation_cost(
            started_at=rush_start,
            now=rush_start + timedelta(hours=60),
            duration_hours=24,
        ),
        time_reduction="24h",
        rush_quoted_at=rush_start + timedelta(hours=60),
    )
    assert not await donations.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=crystal_type,
        amount=Decimal(260),
        time_reduction="8h",
        rush_quoted_at=rush_start + timedelta(hours=68),
    )
    assert await donations.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=crystal_type,
        amount=rush_donation_cost(
            started_at=rush_start,
            now=rush_start + timedelta(hours=68),
            duration_hours=8,
            accelerated_hours=24,
        ),
        time_reduction="8h",
        rush_quoted_at=rush_start + timedelta(hours=68),
    )
    assert await donations.add_donation(
        guild=guild,
        channel_id=987,
        member=member,
        donation_type=simple_type,
        amount=Decimal(250),
        time_reduction=None,
    )
    records = await donations.get_donations(guild=guild, channel_id=789)
    assert len(records) == 2
    exported_records = await donations.get_donations_for_export(
        guild=guild, channel_id=789, cycle=1
    )
    assert exported_records == records
    assert records[0].member_id == 456
    assert records[0].member_name == "Donor One"
    assert records[0].amount == Decimal(445)
    assert records[0].unit == "crystals"
    assert records[0].time_reduction == "8h"
    summary = await donations.get_summary(guild=guild, channel_id=789)
    assert summary == DonationSummary(donation_count=2, time_reduction_hours=32)
    ranking = await donations.get_ranking(guild=guild, channel_id=789, unit="crystals")
    assert len(ranking) == 1
    assert ranking[0].amount == Decimal(1446)
    assert ranking[0].donation_count == 2
    assert ranking[0].time_reduction_hours == 32
    overview = DonationOverview.create_embed(
        guild,
        channel,
        rush_start_at=rush_start,
        timezone_name=channel.timezone_name,
        accelerated_hours=summary.time_reduction_hours,
        donations_enabled=channel.donations_enabled,
    )
    assert overview.title == channel.title
    assert overview.description == channel.description
    assert [field.name for field in overview.fields] == [
        "Startzeit",
        "Dauer",
        "Endzeit",
        "Zeitzone",
        "Spendenstatus",
    ]
    assert overview.fields[0].value == rush_start.astimezone(
        ZoneInfo(channel.timezone_name)
    ).strftime("%d.%m.%Y %H:%M")
    assert "UTC" not in overview.fields[0].value
    assert overview.fields[1].value == "9 Tage (216 Stunden)"
    expected_adjusted_end = (
        rush_start
        + RUSH_PERIOD_DURATION
        - timedelta(hours=summary.time_reduction_hours)
    )
    assert overview.fields[2].value == expected_adjusted_end.astimezone(
        ZoneInfo("America/New_York")
    ).strftime("%d.%m.%Y %H:%M")
    assert overview.fields[3].value == "New York (USA)"
    assert overview.fields[4].value == "aktiviert"
    ranking_embed = DonationOverview.create_ranking_embed(guild, crystal_type, ranking)
    assert "1.446 Kristalle" in ranking_embed.description
    assert "32h eingespart" in ranking_embed.description
    history_embed = DonationOverview.create_history_embed(
        guild,
        crystal_type,
        records,
        summary,
    )
    assert history_embed.title == "2 Spenden | 1d 08:00 beschleunigt"
    assert "Donor One" in history_embed.description
    assert "445 Kristalle" in history_embed.description
    assert not history_embed.fields

    assert await donations.get_donations(guild=guild, channel_id=789) == records
    assert await donations.configure_channel(
        guild=guild,
        channel_id=789,
        title="Donations",
        description="Support the guild",
        goal_hours=216,
        rush_start_at=rush_start,
        donations_enabled=False,
    )
    assert not await donations.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=crystal_type,
        amount=Decimal(28),
        time_reduction="1h",
        rush_quoted_at=datetime.now(timezone.utc),
    )
    assert await donations.reset_cycle(
        guild=guild, channel_id=789, rush_start_at=rush_start
    )
    channel = await donations.get_channel(guild=guild, channel_id=789)
    assert channel is not None and channel.donations_enabled
    for index in range(21):
        assert await database.execute(
            """
            INSERT INTO Donations (
                Guild, Channel, Member, MemberName, TypeName, Amount,
                Unit, TimeReduction, Cycle
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild.id,
                789,
                1000 + index,
                f"Donor {index}",
                crystal_type.name,
                "28",
                "crystals",
                "1h",
                1,
            ),
        )
    assert len(await donations.get_donations(guild=guild, channel_id=789)) == 20
    assert (
        len(await donations.get_donations(guild=guild, channel_id=789, limit=None))
        == 23
    )
    all_records = await donations.get_donations(guild=guild, channel_id=789, limit=None)
    all_summary = await donations.get_summary(guild=guild, channel_id=789)
    assert all_summary is not None
    all_history_embed = DonationOverview.create_history_embed(
        guild,
        crystal_type,
        all_records,
        all_summary,
    )
    assert all_summary.donation_count == 23
    assert all_history_embed.title == "23 Spenden | 2d 05:00 beschleunigt"
    assert "Donor 20" in all_history_embed.description
    assert await donations.get_history_units(guild=guild, channel_id=789) == (
        "crystals",
    )
    assert await donations.delete_channel(guild=guild, channel_id=987)
    assert await donations.get_channels(guild=guild) == (789,)
    assert await donations.get_donations(guild=guild, channel_id=987) == ()
    assert await donations.get_history_units(guild=guild, channel_id=987) == ()
    changed_unit_type = DonationType(
        name="Simple donation",
        kind="simple",
        unit="tokens",
        input_mode="free",
        choices=(),
        time_reductions=(),
    )
    assert await donations.configure_channel(
        guild=guild,
        channel_id=987,
        title="Tokens",
        description="",
    )
    assert await donations.configure_type(
        guild=guild, channel_id=987, donation_type=changed_unit_type
    )
    assert await donations.get_type(guild=guild, channel_id=987) == changed_unit_type
    assert await donations.remove_channel(guild=guild, channel_id=789)
    assert await donations.get_channels(guild=guild) == (987,)
    assert await donations.get_donations(guild=guild, channel_id=789) == ()
    assert await donations.get_history_units(guild=guild, channel_id=789) == ()
    assert (
        await donations.get_ranking(guild=guild, channel_id=789, unit="crystals") == ()
    )
    assert await donations.remove_guild(guild=guild)
    assert await donations.get_channels(guild=guild) == ()


@pytest.mark.asyncio
async def test_donation_schema_migrates_legacy_overview_and_entry_tables(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="legacy-donations.db")
    assert await database.execute(
        """
        CREATE TABLE Donation_Channels (
            Guild INTEGER NOT NULL,
            Channel INTEGER NOT NULL,
            Message INTEGER,
            PRIMARY KEY (Guild, Channel)
        ) WITHOUT ROWID
        """
    )
    assert await database.execute(
        "INSERT INTO Donation_Channels (Guild, Channel, Message) VALUES (?, ?, ?)",
        (123, 789, 987),
    )
    assert await database.execute(
        """
        CREATE TABLE Donations (
            Id INTEGER PRIMARY KEY AUTOINCREMENT,
            Guild INTEGER NOT NULL,
            Channel INTEGER NOT NULL,
            Member INTEGER NOT NULL,
            MemberName TEXT NOT NULL,
            TypeName TEXT NOT NULL,
            Amount TEXT NOT NULL,
            ExtraLabel TEXT,
            ExtraValue TEXT,
            CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    assert await database.execute(
        """
        INSERT INTO Donations (Guild, Channel, Member, MemberName, TypeName, Amount)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (123, 789, 456, "Donor One", "Crystals", "500"),
    )
    repository = DonationRepository(database)

    assert await repository.ensure_schema()
    assert await repository.get_history_units(
        guild=cast(discord.Guild, SimpleNamespace(id=123, name="test guild")),
        channel_id=789,
    ) == ("Crystals",)
    columns = await database.fetch_all('PRAGMA table_info("Donation_Channels")')
    assert "RankingMessage" in {column["name"] for column in columns}
    assert "SummaryMessage" in {column["name"] for column in columns}
    assert {
        "Timezone",
        "ShowDonations",
        "DonationsEnabled",
    }.issubset({column["name"] for column in columns})
    assert "GoalHours" in {column["name"] for column in columns}
    assert {
        "RecentLimit",
        "ShowRanking",
        "RushStartAt",
        "CurrentCycle",
    }.issubset({column["name"] for column in columns})
    donation_columns = await database.fetch_all('PRAGMA table_info("Donations")')
    assert "Cycle" in {column["name"] for column in donation_columns}
    records = await repository.get_donations(
        guild=cast(discord.Guild, SimpleNamespace(id=123, name="test guild")),
        channel_id=789,
    )
    assert len(records) == 1
    assert records[0].unit == "Crystals"
    assert records[0].amount == Decimal(500)
    channel = await repository.get_channel(
        guild=cast(discord.Guild, SimpleNamespace(id=123, name="test guild")),
        channel_id=789,
    )
    assert channel is not None
    assert channel.history_message_id is None
    assert channel.timezone_name == "UTC"
    assert channel.show_donations
    assert channel.donations_enabled


@pytest.mark.asyncio
async def test_reset_starts_new_current_cycle_and_keeps_all_time_ranking(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="donation-cycles.db")
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))
    member = cast(
        discord.Member,
        SimpleNamespace(id=456, display_name="Donor One"),
    )
    repository = DonationRepository(database)
    donation_type = DonationType(
        name="Rush donation",
        kind="time_reduction",
        unit="crystals",
        input_mode="free",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
    )
    start = datetime.now(timezone.utc) - timedelta(hours=1)

    assert await repository.ensure_schema()
    assert await repository.configure_channel(
        guild=guild,
        channel_id=789,
        title="Rush",
        description="",
        recent_limit=7,
        show_ranking=False,
        rush_start_at=start,
    )
    assert await repository.configure_type(
        guild=guild, channel_id=789, donation_type=donation_type
    )
    assert await repository.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=donation_type,
        amount=Decimal(28),
        time_reduction="1h",
        rush_quoted_at=start + timedelta(hours=1),
    )
    assert await repository.reset_cycle(
        guild=guild,
        channel_id=789,
        rush_start_at=start + timedelta(days=10),
    )

    channel = await repository.get_channel(guild=guild, channel_id=789)
    assert channel is not None
    assert channel.current_cycle == 2
    assert channel.recent_limit == 7
    assert not channel.show_ranking
    assert channel.rush_start_at is not None
    assert channel.rush_start_at == start + timedelta(days=10)
    assert channel.rush_start_at + RUSH_PERIOD_DURATION == start + timedelta(days=19)
    assert (
        await repository.get_donations(
            guild=guild, channel_id=789, cycle=channel.current_cycle
        )
        == ()
    )
    assert await repository.get_summary(
        guild=guild, channel_id=789, cycle=channel.current_cycle
    ) == DonationSummary(donation_count=0, time_reduction_hours=0)
    ranking = await repository.get_ranking(guild=guild, channel_id=789, unit="crystals")
    assert len(ranking) == 1
    assert ranking[0].amount == Decimal(28)
    assert ranking[0].time_reduction_hours == 1


@pytest.mark.asyncio
async def test_repository_rejects_rush_donations_after_the_cutoff(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="donation-cutoff.db")
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))
    member = cast(
        discord.Member,
        SimpleNamespace(id=456, display_name="Donor One"),
    )
    repository = DonationRepository(database)
    donation_type = DonationType(
        name="Rush donation",
        kind="time_reduction",
        unit="crystals",
        input_mode="free",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
    )
    start = datetime.now(timezone.utc) - RUSH_DONATION_CUTOFF - timedelta(minutes=1)
    quote_time = start + RUSH_DONATION_CUTOFF

    assert await repository.ensure_schema()
    assert await repository.configure_channel(
        guild=guild,
        channel_id=789,
        title="Rush",
        description="",
        rush_start_at=start,
    )
    assert await repository.configure_type(
        guild=guild, channel_id=789, donation_type=donation_type
    )
    assert not await repository.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=donation_type,
        amount=Decimal(84),
        time_reduction="1h",
        rush_quoted_at=quote_time,
    )
    assert await repository.get_donations(guild=guild, channel_id=789) == ()


@pytest.mark.asyncio
async def test_repository_allows_only_durations_that_fit_before_rush_cutoff(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="donation-last-hours.db")
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))
    member = cast(
        discord.Member,
        SimpleNamespace(id=456, display_name="Donor One"),
    )
    repository = DonationRepository(database)
    donation_type = DonationType(
        name="Rush donation",
        kind="time_reduction",
        unit="crystals",
        input_mode="free",
        choices=(),
        time_reductions=("1h", "8h", "24h"),
    )
    quote_time = datetime.now(timezone.utc)
    start = quote_time - timedelta(hours=190)

    assert await repository.ensure_schema()
    assert await repository.configure_channel(
        guild=guild,
        channel_id=789,
        title="Rush",
        description="",
        rush_start_at=start,
    )
    assert await repository.configure_type(
        guild=guild, channel_id=789, donation_type=donation_type
    )
    assert not await repository.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=donation_type,
        amount=Decimal(667),
        time_reduction="8h",
        rush_quoted_at=quote_time,
    )
    assert await repository.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=donation_type,
        amount=Decimal(84),
        time_reduction="1h",
        rush_quoted_at=quote_time,
    )


def test_donation_input_parsing_rejects_invalid_amounts_and_choices() -> None:
    assert parse_amount("1000.50") == Decimal("1000.50")
    assert parse_choices("100; 500; 1000") == ("100", "500", "1000")
    assert parse_amount("1.00.000") == Decimal("100000")
    assert parse_amount("1,00,000") == Decimal("100000")
    assert DonationOverview._format_amount(Decimal("1234567.50")) == "1.234.567,5"
    assert (
        DonationOverview._format_amount(Decimal("1234567.1234567890123456789012345"))
        == "1.234.567,1234567890123456789012345"
    )
    assert parse_hours("216h") == 216
    assert parse_hours("9") == 9
    for amount in ("0", "-1", "NaN", "1.00.x"):
        with pytest.raises(ValueError):
            parse_amount(amount)
    for choices in ("", "1;;2", "1;1", ";".join(str(i) for i in range(26))):
        with pytest.raises(ValueError):
            parse_choices(choices)
    for hours in ("0", "1d", "-1h", "1.5h"):
        with pytest.raises(ValueError):
            parse_hours(hours)
