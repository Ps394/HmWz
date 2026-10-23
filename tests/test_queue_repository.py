from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
import pytest

from hmwz.modules.queue.repository import QueueRepository
from hmwz.sqlite_db import Database


@pytest.mark.asyncio
async def test_queue_configuration_and_run_confirmations_persist(
    tmp_path: Path,
) -> None:
    database = Database(folder=str(tmp_path), filename="queues.db")
    repository = QueueRepository(database)
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))

    assert await repository.ensure_schema()
    assert await repository.configure(
        guild=guild,
        channel_id=456,
        name="Evening Run",
        min_players=0,
        max_players=2,
        confirmation_delay_minutes=30,
        reminder_interval_minutes=15,
    )
    configuration = await repository.get(guild=guild, channel_id=456)
    assert configuration is not None
    assert configuration.max_players == 2
    assert configuration.confirmation_delay_minutes == 30
    assert configuration.reminder_interval_minutes == 15

    assert await repository.join(
        guild=guild, channel_id=456, member_id=11, joined_at=10.0
    )
    assert await repository.join(
        guild=guild, channel_id=456, member_id=12, joined_at=11.0
    )
    assert await repository.get_members(guild=guild, channel_id=456) == (11, 12)
    run_id = await repository.create_run(
        guild=guild,
        channel_id=456,
        thread_id=789,
        message_id=987,
        members=(11, 12),
        started_at=100.0,
        confirmation_available_at=1900.0,
    )
    assert run_id is not None
    assert await repository.get_members(guild=guild, channel_id=456) == ()

    run = await repository.get_run(run_id)
    assert run is not None
    assert run.status == "active"
    assert run.confirmation_available_at == 1900.0
    assert await repository.confirm(run_id=run_id, member_id=11, confirmed_at=2000.0)
    assert await repository.mark_reminded(
        run_id=run_id, member_id=12, reminded_at=2010.0
    )
    participants = await repository.get_run_participants(run_id)
    assert participants[0].confirmed_at == 2000.0
    assert participants[1].last_reminded_at == 2010.0

    assert await repository.confirm(run_id=run_id, member_id=12, confirmed_at=2020.0)
    assert await repository.complete_run(run_id)
    assert await repository.completed_count(guild=guild, channel_id=456) == 1
