"""Attainable target times, persisted caps, and highlighted Rush end times."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.modules.donation.overview import DonationOverview
from hmwz.modules.donation.repositories import DonationRepository
from hmwz.modules.donation.models import DonationType
from hmwz.modules.donation.snapshot import DonationSnapshotBuilder
from hmwz.modules.donation.type.rush.pricing import (
    available_rush_durations,
    rush_donation_prices,
    rush_end_at,
    validate_rush_target,
)
from hmwz.sqlite_db import Database


@pytest.mark.parametrize(
    ("remaining", "expected"),
    [
        (25, (24, 8, 1)),
        (24, (24, 8, 1)),
        (9, (8, 1)),
        (8, (8, 1)),
        (7, (1,)),
        (1, (1,)),
        (0, ()),
    ],
)
def test_target_filters_every_price_and_duration(
    remaining: int, expected: tuple[int, ...]
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    target = rush_end_at(start, 50 + remaining)
    kwargs = dict(started_at=start, now=start, accelerated_hours=50, target_at=target)
    assert available_rush_durations(**kwargs) == expected
    assert tuple(rush_donation_prices(**kwargs)) == expected


def test_target_preserves_start_and_24_hour_cutoff() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    target = rush_end_at(start, 24)
    assert (
        available_rush_durations(
            started_at=start,
            now=start - timedelta(seconds=1),
            accelerated_hours=0,
            target_at=target,
        )
        == ()
    )
    assert available_rush_durations(
        started_at=start,
        now=start + timedelta(hours=191),
        accelerated_hours=0,
        target_at=target,
    ) == (1,)
    assert (
        available_rush_durations(
            started_at=start,
            now=start + timedelta(hours=192),
            accelerated_hours=0,
            target_at=target,
        )
        == ()
    )


@pytest.mark.parametrize("hours", [0, 217, 49, 50.5])
def test_invalid_targets_are_rejected(hours: float) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        validate_rush_target(start, rush_end_at(start) - timedelta(hours=hours), 50)


def test_targets_accept_equality_and_other_utc_offsets_but_reject_naive_times() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    target = rush_end_at(start, 50)
    validate_rush_target(start, target, 50)
    validate_rush_target(start, target.astimezone(timezone(timedelta(hours=2))), 50)
    with pytest.raises(ValueError):
        validate_rush_target(start, target.replace(tzinfo=None))


@pytest.mark.asyncio
async def test_persisted_target_moves_end_exactly_and_caps_stale_and_parallel_donations(
    tmp_path: Path,
) -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="Test", locale="de"))
    member = cast(discord.Member, SimpleNamespace(id=456, display_name="Donor"))
    database = Database(folder=str(tmp_path), filename="targets.db")
    repo = DonationRepository(database)
    assert await repo.ensure_schema()
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    target = rush_end_at(start, 33)
    donation_type = DonationType(
        "Rush", "time_reduction", "crystals", "choice", (), ("1h", "8h", "24h")
    )
    assert await repo.configure_channel(
        guild=guild,
        channel_id=789,
        title="Rush",
        description="",
        rush_start_at=start,
        target_at=target,
    )
    assert await repo.configure_type(
        guild=guild, channel_id=789, donation_type=donation_type
    )
    restored = await DonationRepository(database).get_channel(
        guild=guild, channel_id=789
    )
    assert restored is not None and restored.target_at == target

    async def donate(hours: int) -> bool:
        return await repo.add_donation(
            guild=guild,
            channel_id=789,
            member=member,
            donation_type=donation_type,
            amount={24: Decimal(667), 8: Decimal(223), 1: Decimal(28)}[hours],
            time_reduction=f"{hours}h",
            rush_quoted_at=now,
        )

    for hours, total in [(24, 24), (8, 32)]:
        assert await donate(hours)
        summary = await repo.get_summary(guild=guild, channel_id=789, cycle=1)
        assert summary is not None and summary.time_reduction_hours == total
        embed = DonationOverview.create_embed(
            guild, restored, rush_start_at=start, accelerated_hours=total
        )
        assert next(
            f.value for f in embed.fields if f.name == "Endzeit"
        ) == discord.utils.format_dt(rush_end_at(start, total), "F")
    assert not await donate(8)
    results = await asyncio.gather(donate(1), donate(1))
    assert sorted(results) == [False, True]
    assert not await donate(1)
    summary = await repo.get_summary(guild=guild, channel_id=789, cycle=1)
    assert summary is not None and summary.time_reduction_hours == 33
    embed = DonationOverview.create_embed(
        guild, restored, rush_start_at=start, accelerated_hours=33
    )
    highlighted = next(f for f in embed.fields if f.name == "ZIELZEIT")
    assert highlighted.inline is False
    assert highlighted.value.startswith(f"**{discord.utils.format_dt(target, 'F')}**")
    assert "Ziel erreicht" in highlighted.value

    snapshot = await DonationSnapshotBuilder(guild=guild, donations=repo).build(
        configuration=restored,
        destination_channel_id=321,
        event_type="snapshot",
    )
    assert snapshot is not None
    assert (
        snapshot.payload["target_at"]
        == snapshot.payload["end_at"]
        == target.isoformat()
    )

    new_start = now + timedelta(days=10)
    new_target = rush_end_at(new_start, 8)
    assert await repo.reset_cycle(
        guild=guild, channel_id=789, rush_start_at=new_start, target_at=new_target
    )
    restored = await repo.get_channel(guild=guild, channel_id=789)
    assert restored is not None and restored.target_at == new_target
    assert await repo.reset_cycle(guild=guild, channel_id=789, rush_start_at=new_start)
    restored = await repo.get_channel(guild=guild, channel_id=789)
    assert restored is not None and restored.target_at is None

    # A confirmation issued without a target must obey a subsequently saved target.
    assert await repo.reset_cycle(guild=guild, channel_id=789, rush_start_at=start)
    assert await repo.configure_channel(
        guild=guild,
        channel_id=789,
        title="Rush",
        description="",
        rush_start_at=start,
        target_at=rush_end_at(start, 1),
    )
    assert not await repo.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=donation_type,
        amount=Decimal(223),
        time_reduction="8h",
        rush_quoted_at=now,
        cycle=4,
    )


@pytest.mark.asyncio
async def test_repository_rejects_invalid_targets_without_overwriting_configuration(
    tmp_path: Path,
) -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="Test"))
    repo = DonationRepository(
        Database(folder=str(tmp_path), filename="invalid-target.db")
    )
    assert await repo.ensure_schema()
    start = datetime.now(UTC)
    assert await repo.configure_channel(
        guild=guild, channel_id=789, title="Rush", description="", rush_start_at=start
    )
    invalid = rush_end_at(start) - timedelta(minutes=30)
    assert not await repo.configure_channel(
        guild=guild,
        channel_id=789,
        title="Changed",
        description="",
        rush_start_at=start,
        target_at=invalid,
    )
    assert not await repo.reset_cycle(
        guild=guild,
        channel_id=789,
        rush_start_at=start,
        target_at=invalid,
    )
    stored = await repo.get_channel(guild=guild, channel_id=789)
    assert stored is not None and stored.title == "Rush" and stored.current_cycle == 1
