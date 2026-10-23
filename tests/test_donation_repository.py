from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.modules.donation.repository import DonationRepository, DonationType
from hmwz.modules.donation.overview import DonationOverview
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
    donations = DonationRepository(database)

    assert await donations.ensure_schema()
    assert await donations.add_type(guild=guild, name="Credits", extra_field=None)
    assert await donations.add_type(guild=guild, name="Kristalle", extra_field="Zeit")
    assert await donations.get_types(guild=guild) == (
        DonationType(name="Credits", extra_field=None),
        DonationType(name="Kristalle", extra_field="Zeit"),
    )
    assert await donations.add_channel(guild=guild, channel_id=789)
    assert await donations.add_channel(guild=guild, channel_id=987)
    assert await donations.get_channels(guild=guild) == (789, 987)

    crystal_type = await donations.get_type(guild=guild, name="Kristalle")
    assert crystal_type is not None
    assert await donations.add_donation(
        guild=guild,
        channel_id=789,
        member=member,
        donation_type=crystal_type,
        amount="500",
        extra_value="24h",
    )
    records = await donations.get_donations(guild=guild, channel_id=789)
    assert len(records) == 1
    assert records[0].member_id == 456
    assert records[0].member_name == "Donor One"
    assert records[0].type_name == "Kristalle"
    assert records[0].amount == "500"
    assert records[0].extra_label == "Zeit"
    assert records[0].extra_value == "24h"
    overview = DonationOverview.create_embed(guild, (), records)
    assert "Zeit: 24h" in overview.fields[1].value

    assert await donations.remove_type(guild=guild, name="Kristalle")
    assert await donations.get_type(guild=guild, name="Kristalle") is None
    assert await donations.get_donations(guild=guild, channel_id=789) == records
    assert await donations.remove_channel(guild=guild, channel_id=789)
    assert await donations.get_channels(guild=guild) == (987,)
    assert await donations.get_donations(guild=guild, channel_id=789) == records
