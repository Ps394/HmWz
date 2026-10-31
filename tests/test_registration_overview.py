from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.modules.overview import OverviewModule
from hmwz.modules.registration.overview import RegistrationHandler, RegistrationOverview
from hmwz.modules.registration.repositories import (
    MemberRegistrationRepository,
    RegistrationRoleRepository,
    RegistrationSettingsRepository,
)


@pytest.fixture
def overview() -> RegistrationOverview:
    result = RegistrationOverview(
        guild=cast(discord.Guild, SimpleNamespace(id=1, name="guild")),
        client=cast(discord.Client, SimpleNamespace()),
        registration=cast(RegistrationSettingsRepository, SimpleNamespace()),
        roles=cast(RegistrationRoleRepository, SimpleNamespace()),
        registrations=cast(MemberRegistrationRepository, SimpleNamespace()),
        registration_handler=cast(RegistrationHandler, AsyncMock()),
        overview_module=cast(OverviewModule, SimpleNamespace()),
        channel_id=123,
    )
    result._compose_min_interval_seconds = 0
    return result


@pytest.mark.asyncio
async def test_simultaneous_requests_share_one_composition(
    overview: RegistrationOverview, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose = AsyncMock(return_value=True)
    monkeypatch.setattr(overview, "_compose", compose)
    results = await asyncio.gather(*(overview.compose(force=True) for _ in range(20)))
    assert all(results)
    compose.assert_awaited_once()


@pytest.mark.asyncio
async def test_requests_during_each_pass_are_coalesced_without_losing_changes(
    overview: RegistrationOverview, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = [asyncio.Event() for _ in range(3)]
    release = [asyncio.Event() for _ in range(3)]
    current_value = 0
    published: list[int] = []

    async def compose() -> bool:
        index = len(published)
        published.append(current_value)
        started[index].set()
        await release[index].wait()
        return True

    monkeypatch.setattr(overview, "_compose", compose)
    tasks = [asyncio.create_task(overview.compose(force=True))]
    await started[0].wait()
    current_value = 1
    tasks.extend(asyncio.create_task(overview.compose(force=True)) for _ in range(20))
    await asyncio.sleep(0)
    release[0].set()
    await started[1].wait()
    assert not any(task.done() for task in tasks)
    current_value = 2
    tasks.extend(asyncio.create_task(overview.compose(force=True)) for _ in range(20))
    await asyncio.sleep(0)
    release[1].set()
    await started[2].wait()
    release[2].set()

    assert all(await asyncio.gather(*tasks))
    assert published == [0, 1, 2]


@pytest.mark.asyncio
async def test_normal_requests_are_delayed_and_force_wakes_shared_update(
    overview: RegistrationOverview, monkeypatch: pytest.MonkeyPatch
) -> None:
    overview._last_compose_at = time.monotonic()
    overview._compose_min_interval_seconds = 60
    compose = AsyncMock(return_value=True)
    monkeypatch.setattr(overview, "_compose", compose)
    normal = asyncio.create_task(overview.compose())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    compose.assert_not_awaited()
    forced = asyncio.create_task(overview.compose(force=True))
    assert all(await asyncio.wait_for(asyncio.gather(normal, forced), timeout=1))
    compose.assert_awaited_once()


@pytest.mark.asyncio
async def test_normal_request_is_eventually_published_without_force(
    overview: RegistrationOverview, monkeypatch: pytest.MonkeyPatch
) -> None:
    overview._last_compose_at = time.monotonic()
    overview._compose_min_interval_seconds = 0.001
    compose = AsyncMock(return_value=True)
    monkeypatch.setattr(overview, "_compose", compose)
    assert await overview.compose()
    compose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, RuntimeError("Failed synchronization")])
async def test_shared_failure_is_not_hidden_and_next_request_can_retry(
    overview: RegistrationOverview,
    monkeypatch: pytest.MonkeyPatch,
    failure: bool | RuntimeError,
) -> None:
    compose = AsyncMock(side_effect=[failure, True])
    monkeypatch.setattr(overview, "_compose", compose)
    results = await asyncio.gather(
        *(overview.compose(force=True) for _ in range(3)), return_exceptions=True
    )
    if isinstance(failure, RuntimeError):
        assert all(result is failure for result in results)
    else:
        assert results == [False, False, False]
    assert overview._last_compose_at == 0
    assert await overview.compose(force=True)
    assert compose.await_count == 2


@pytest.mark.asyncio
async def test_failed_first_pass_is_not_hidden_by_successful_followup(
    overview: RegistrationOverview, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def compose() -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
            return False
        return True

    monkeypatch.setattr(overview, "_compose", compose)
    first = asyncio.create_task(overview.compose(force=True))
    await started.wait()
    second = asyncio.create_task(overview.compose(force=True))
    await asyncio.sleep(0)
    release.set()
    assert await asyncio.gather(first, second) == [False, False]
    assert calls == 2


@pytest.mark.asyncio
async def test_cancelling_one_caller_does_not_cancel_shared_synchronization(
    overview: RegistrationOverview, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def compose() -> bool:
        started.set()
        await release.wait()
        return True

    compose_mock = AsyncMock(side_effect=compose)
    monkeypatch.setattr(overview, "_compose", compose_mock)
    cancelled = asyncio.create_task(overview.compose(force=True))
    remaining = asyncio.create_task(overview.compose(force=True))
    await started.wait()
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release.set()
    assert await remaining
    compose_mock.assert_awaited_once()
