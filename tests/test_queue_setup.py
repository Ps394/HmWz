from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz.modules.queue.module import QueueModule
from hmwz.modules.queue import module as queue_module
from hmwz.modules.queue.commands import setup as queue_setup
from hmwz.modules.queue.modes import create_queue_modes
from hmwz.modules.queue.modes.protocol import QueueModeSetup, QueuePool
from hmwz.modules.queue.views import QueueOverviewView
from hmwz.modules.queue.wizard import (
    QueueConfigView,
    QueueModeChangeConfirmationView,
    QueueSeasonDurationSelect,
    QueueSetupModeSelect,
    QueueSetupDraft,
    QueueSeasonHoursSelect,
)


@pytest.mark.asyncio
async def test_setup_starts_with_type_selection_and_opens_settings_menu() -> None:
    module = cast(QueueModule, SimpleNamespace(guild=SimpleNamespace()))
    for mode in ("continuous", "stages", "seasons"):
        draft = QueueSetupDraft(
            module=module,
            channel_id=456,
            owner_id=789,
            mode=mode,
        )
        settings_view = QueueConfigView(draft)
        selector = cast(discord.ui.Select, settings_view.children[0])
        controls = {
            item.custom_id
            for item in settings_view.children
            if isinstance(item, discord.ui.Button)
        }

        assert [option.value for option in selector.options] == [
            "continuous",
            "stages",
            "seasons",
        ]
        assert {
            "queue:setup:title",
            "queue:setup:description",
            "queue:setup:ping",
            "queue:setup:save",
        }.issubset(controls)
        assert ("queue:setup:range" in controls) == (mode != "seasons")
        assert ("queue:setup:mode" in controls) == (mode != "continuous")
        assert ("queue:setup:schedule" in controls) == (mode == "seasons")
        assert ("queue:setup:duration" in controls) == (mode == "seasons")
        assert ("queue:setup:tasks" in controls) == (mode == "seasons")


def test_season_hour_options_cover_each_hour_once() -> None:
    module = cast(QueueModule, SimpleNamespace(guild=SimpleNamespace()))
    draft = QueueSetupDraft(
        module=module,
        channel_id=456,
        owner_id=789,
        mode="seasons",
    )
    selector = QueueSeasonHoursSelect(draft)

    assert selector.max_values == 6
    assert [option.value for option in selector.options] == [
        f"{hour:02}:00" for hour in range(24)
    ]


def test_season_duration_options_are_limited_to_supported_hours() -> None:
    module = cast(QueueModule, SimpleNamespace(guild=SimpleNamespace()))
    draft = QueueSetupDraft(
        module=module,
        channel_id=456,
        owner_id=789,
        mode="seasons",
    )
    selector = QueueSeasonDurationSelect(draft)

    assert [option.value for option in selector.options] == [
        "12",
        "24",
        "36",
        "48",
        "60",
        "72",
    ]


@pytest.mark.asyncio
async def test_season_queue_uses_one_join_leave_control() -> None:
    module = cast(QueueModule, SimpleNamespace(guild=SimpleNamespace()))

    view = QueueOverviewView(
        module,
        456,
        mode="seasons",
        pools=tuple(QueuePool(hour, f"{hour:02}:00", ()) for hour in range(6)),
    )

    assert len(view.children) == 6
    assert [item.custom_id for item in view.children] == [
        f"queue:season:toggle:456:{hour}" for hour in range(6)
    ]
    assert all(item.custom_id != "queue:vote:456" for item in view.children)


@pytest.mark.asyncio
async def test_existing_queue_type_change_requires_confirmation(monkeypatch) -> None:
    module = cast(QueueModule, SimpleNamespace(guild=SimpleNamespace()))
    draft = QueueSetupDraft(
        module=module,
        channel_id=456,
        owner_id=789,
        mode="continuous",
        configuration=SimpleNamespace(mode="continuous"),
        stages=["old stage"],
    )
    setup_view = QueueConfigView(draft)
    selector = cast(QueueSetupModeSelect, setup_view.children[0])
    selector._values = ["stages"]
    interaction = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()))
    monkeypatch.setattr("hmwz.modules.queue.wizard.t", Mock(return_value="confirm"))

    await selector.callback(cast(discord.Interaction, interaction))

    confirmation = interaction.response.edit_message.await_args.kwargs["view"]
    assert isinstance(confirmation, QueueModeChangeConfirmationView)
    assert confirmation.selected_mode == "stages"


@pytest.mark.asyncio
async def test_other_queue_modes_use_a_single_toggle_button() -> None:
    module = cast(QueueModule, SimpleNamespace(guild=SimpleNamespace()))

    view = QueueOverviewView(module, 456, mode="continuous")
    registration_buttons = [
        item
        for item in view.children
        if isinstance(item, discord.ui.Button)
        and item.custom_id in {"queue:toggle:456", "queue:join:456", "queue:leave:456"}
    ]

    assert len(registration_buttons) == 1
    assert registration_buttons[0].custom_id == "queue:toggle:456"

    stage_view = QueueOverviewView(
        module,
        456,
        mode="stages",
        pools=(QueuePool(1, "S1", ()), QueuePool(2, "S2", ())),
    )
    assert [item.custom_id for item in stage_view.children] == [
        "queue:stage:toggle:456:1",
        "queue:stage:toggle:456:2",
        "queue:vote:456",
    ]
    assert [item.label for item in stage_view.children[:2]] == ["S1", "S2"]

    maximum_stage_view = QueueOverviewView(
        module,
        456,
        mode="stages",
        pools=tuple(QueuePool(index, f"Stage {index}", ()) for index in range(1, 25)),
    )
    assert len(maximum_stage_view.children) == 25


def test_configuration_validation_applies_mode_specific_requirements() -> None:
    base = {
        "min_players": 1,
        "max_players": 5,
        "mode": "continuous",
        "confirmation_delay_minutes": 30,
        "stages": (),
        "seasons": (),
        "season_goal_limit": 1,
        "season_goal_description": "",
        "season_start_date": None,
        "timezone": "Europe/Berlin",
        "stage_prefix": "",
    }

    module = SimpleNamespace(queue_modes=create_queue_modes())
    assert QueueModule._is_valid_configuration(module, **base)
    assert not QueueModule._is_valid_configuration(
        module, **(base | {"mode": "stages", "stages": ("1", "3")})
    )
    assert QueueModule._is_valid_configuration(
        module,
        **(
            base
            | {
                "mode": "stages",
                "stages": ("Level 1", "Level 2"),
                "stage_prefix": "Level ",
            }
        ),
    )
    assert not create_queue_modes()["stages"].validate_setup(
        QueueModeSetup(
            stage_count=25,
            stage_prefix="",
            stage_labels=tuple(str(index) for index in range(1, 26)),
            seasons=(),
            season_goal_limit=1,
            season_goal_description="",
            season_start_date=None,
            timezone="Europe/Berlin",
            season_duration_hours=24,
            season_tasks=(),
        )
    )
    assert not QueueModule._is_valid_configuration(
        module,
        **(
            base
            | {
                "mode": "seasons",
                "seasons": ("08:00",),
                "season_goal_description": "Goals",
                "season_start_date": None,
            }
        ),
    )


@pytest.mark.asyncio
async def test_run_details_use_stage_name_or_season_name() -> None:
    module = cast(
        QueueModule,
        SimpleNamespace(
            guild=SimpleNamespace(name="test guild", locale="de"),
            queues=SimpleNamespace(
                get_stages=AsyncMock(
                    return_value=(SimpleNamespace(index=2, name="2"),)
                ),
                get_next_season=AsyncMock(
                    return_value=SimpleNamespace(name="08:00", starts_at=0)
                ),
            ),
        ),
    )
    stage_configuration = SimpleNamespace(
        channel_id=456,
        title="Queue",
        mode="stages",
    )
    season_configuration = SimpleNamespace(
        channel_id=456,
        title="Queue",
        mode="seasons",
    )

    assert await QueueModule._resolve_run_details(
        module, stage_configuration, stage_index=2
    ) == ("2", None)
    assert await QueueModule._resolve_run_details(
        module, season_configuration, stage_index=0
    ) == ("08:00", module.queues.get_next_season.return_value)


@pytest.mark.asyncio
async def test_due_season_start_notifies_registered_members(monkeypatch) -> None:
    guild = SimpleNamespace(name="test guild")
    thread = SimpleNamespace(
        mention="<#123>",
        send=AsyncMock(),
    )
    season = SimpleNamespace(
        index=8,
        name="08:00",
        starts_at=100,
        thread_id=123,
    )
    queues = SimpleNamespace(
        get_due_seasons=AsyncMock(return_value=((456, 8),)),
        activate_season=AsyncMock(return_value=True),
        get_unnotified_started_seasons=AsyncMock(return_value=((456, 8),)),
        get=AsyncMock(return_value=SimpleNamespace(ping_participants=True)),
        get_season=AsyncMock(return_value=season),
        get_season_members=AsyncMock(return_value=(42,)),
        mark_season_start_notified=AsyncMock(return_value=True),
    )
    module = cast(
        QueueModule,
        SimpleNamespace(
            guild=guild,
            queues=queues,
            _refresh_season_thread=AsyncMock(return_value=True),
            _fetch_thread=AsyncMock(return_value=thread),
        ),
    )
    translate = Mock(return_value="Season started")
    monkeypatch.setattr(queue_module, "t", translate)

    await QueueModule._process_due_season_starts(module, now=100)

    queues.activate_season.assert_awaited_once_with(
        guild=guild,
        channel_id=456,
        season_index=8,
        now=100,
    )
    thread.send.assert_awaited_once()
    assert thread.send.await_args.kwargs["allowed_mentions"].users == [
        discord.Object(id=42)
    ]
    queues.mark_season_start_notified.assert_awaited_once_with(
        guild=guild,
        channel_id=456,
        season_index=8,
    )
    translate.assert_any_call(
        guild,
        "queue.season.started",
        name="08:00",
        thread="<#123>",
        members="<@42>",
        start="<t:100:F>",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("author_id", "include_user_messages"),
    [(999, False), (111, True)],
)
async def test_reset_skips_system_messages(
    author_id: int, include_user_messages: bool
) -> None:
    system_message = SimpleNamespace(
        author=SimpleNamespace(id=author_id),
        id=123,
        is_system=Mock(return_value=True),
        delete=AsyncMock(),
    )

    async def history(*, limit: int | None):
        assert limit is None
        yield system_message

    channel = SimpleNamespace(id=456, history=Mock(side_effect=history))
    module = cast(
        QueueModule,
        SimpleNamespace(
            client=SimpleNamespace(user=SimpleNamespace(id=999)),
            guild=SimpleNamespace(name="test guild"),
        ),
    )

    assert await QueueModule._clear_messages(
        module,
        channel,
        include_user_messages=include_user_messages,
    )

    system_message.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_confirmation_falls_back_when_message_is_gone(monkeypatch) -> None:
    module = SimpleNamespace(
        guild=SimpleNamespace(name="test guild", locale="de"),
        reset_season_queue=AsyncMock(return_value=True),
    )
    reset_view = queue_setup.QueueSeasonResetConfirmation(
        cast(QueueModule, module), channel_id=456, owner_id=789
    )
    button = cast(queue_setup.QueueSeasonResetButton, reset_view.children[0])
    message = SimpleNamespace(
        edit=AsyncMock(
            side_effect=discord.NotFound(
                SimpleNamespace(status=404, reason="Not Found"),
                {"message": "Unknown Message", "code": 10008},
            )
        )
    )
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
        message=message,
    )
    monkeypatch.setattr(queue_setup, "t", Mock(return_value="Queue reset"))

    await button.callback(cast(discord.Interaction, interaction))

    module.reset_season_queue.assert_awaited_once_with(456)
    message.edit.assert_awaited_once_with(content="Queue reset", view=None)
    interaction.followup.send.assert_awaited_once_with("Queue reset", ephemeral=True)


@pytest.mark.asyncio
async def test_queue_toggle_leaves_when_member_is_already_waiting() -> None:
    module = cast(
        QueueModule,
        SimpleNamespace(
            guild=SimpleNamespace(id=123),
            queues=SimpleNamespace(
                get_waiting_members=AsyncMock(return_value=((42, 0),))
            ),
            _validate_queue_interaction=AsyncMock(
                return_value=SimpleNamespace(mode="stages")
            ),
            _leave_queue=AsyncMock(),
        ),
    )
    interaction = cast(
        discord.Interaction, SimpleNamespace(user=SimpleNamespace(id=42))
    )

    await QueueModule.handle_queue_action(module, interaction, 456, "toggle")

    module._leave_queue.assert_awaited_once_with(interaction, 456)


@pytest.mark.asyncio
@pytest.mark.parametrize("active_run", [False, True])
async def test_remove_queue_clears_waiting_members_but_blocks_active_runs(
    active_run: bool,
) -> None:
    guild = SimpleNamespace(
        id=123,
        name="test guild",
        get_channel=Mock(),
    )
    queues = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(message_id=None)),
        get_waiting_members=AsyncMock(return_value=((11, 0),)),
        get_active_runs=AsyncMock(
            return_value=(SimpleNamespace(channel_id=456),) if active_run else ()
        ),
        get_runs=AsyncMock(return_value=()),
        get_seasons=AsyncMock(return_value=()),
        remove=AsyncMock(return_value=True),
    )
    module = cast(
        QueueModule,
        SimpleNamespace(
            guild=guild,
            queues=queues,
            _delete_run_threads=AsyncMock(return_value=True),
            _delete_season_threads=AsyncMock(return_value=True),
            _confirmation_enabled_runs=set(),
            _overview_messages={},
        ),
    )

    removed = await QueueModule.remove_queue(module, channel_id=456)

    assert removed is not active_run
    if active_run:
        queues.remove.assert_not_awaited()
    else:
        queues.remove.assert_awaited_once_with(guild=guild, channel_id=456)


@pytest.mark.asyncio
async def test_remove_queue_removes_setup_before_deleting_overview() -> None:
    operations: list[str] = []
    message = SimpleNamespace(
        delete=AsyncMock(side_effect=lambda: operations.append("message"))
    )
    channel = Mock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    guild = SimpleNamespace(
        id=123,
        name="test guild",
        get_channel=Mock(return_value=channel),
    )
    queues = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(message_id=789)),
        get_active_runs=AsyncMock(return_value=()),
        get_runs=AsyncMock(return_value=()),
        get_seasons=AsyncMock(return_value=()),
        remove=AsyncMock(side_effect=lambda **_: operations.append("setup") or True),
    )
    module = cast(
        QueueModule,
        SimpleNamespace(
            guild=guild,
            queues=queues,
            _delete_run_threads=AsyncMock(return_value=True),
            _delete_season_threads=AsyncMock(return_value=True),
            _confirmation_enabled_runs=set(),
            _overview_messages={},
        ),
    )

    assert await QueueModule.remove_queue(module, channel_id=456)

    assert operations == ["setup", "message"]
