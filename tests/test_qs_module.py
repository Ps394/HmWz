import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import aiosqlite
import discord
import pytest

from hmwz.client import Client
from hmwz.i18n import RuntimeLocalizations
from hmwz.modules.hs.qs.commands import QsGroup
from hmwz.modules.hs.qs.models import BaseReport, Configuration, Phase, PingSettings
from hmwz.modules.hs.qs.models.ping_settings import PING_EVENTS, PingEvent
from hmwz.modules.hs.qs.commands.maintenance import QsMaintenanceConfirmation
from hmwz.modules.hs.qs.module import QsModule
from hmwz.modules.hs.qs.notifications import QsNotifications
from hmwz.modules.hs.qs.overview import (
    bases_embeds,
    member_list,
    overview_embed,
    phase_embed,
)
from hmwz.modules.hs.qs.setup import (
    HourSelect,
    DateModal,
    DurationSelect,
    PhaseSelect,
    PhaseCountSelect,
    QsRoleSelection,
    QsSetupView,
    PingButton,
    setup_view,
    SetupButton,
)
from hmwz.modules.hs.qs.views import (
    BaseReportConfirmation,
    OverviewView,
    PhaseView,
)
from hmwz.modules.manager import Manager
from hmwz.modules.protocols import MessageModuleProtocol
from hmwz.sqlite_db import Database
from hmwz.utils.loaders import fetch_message


def missing() -> discord.NotFound:
    return discord.NotFound(Mock(status=404, reason="Not Found"), "missing")


@pytest.fixture
def notification_worker() -> object:
    with patch.object(QsNotifications, "start"):
        yield


@pytest.fixture
async def environment(tmp_path: Path, notification_worker: object) -> SimpleNamespace:
    database = Database(folder=str(tmp_path), filename="module.db")
    assert await database.execute("CREATE TABLE Servers (Guild INTEGER PRIMARY KEY)")
    assert await database.execute("INSERT INTO Servers VALUES (10)")
    ids = count(1000)
    messages: dict[int, Mock] = {}
    threads: dict[int, Mock] = {}
    role = Mock(spec=discord.Role, id=30, name="Qs", mention="<@&30>")
    role.is_default.return_value = False
    role.mentionable = True
    moderator = Mock(spec=discord.Role, id=31, name="Moderator")
    moderator.name = "Moderator"
    moderator.is_default.return_value = False
    guild = Mock(spec=discord.Guild)
    guild.id, guild.name, guild.preferred_locale = 10, "Guild", discord.Locale.german
    guild.roles = [role, moderator]
    guild.get_role.side_effect = lambda role_id: next(
        (item for item in guild.roles if item.id == role_id), None
    )
    guild.get_thread.side_effect = threads.get
    guild.get_member.return_value = None

    async def fetch_message(message_id: int) -> Mock:
        if message_id not in messages:
            raise missing()
        return messages[message_id]

    async def send(**kwargs: object) -> Mock:
        message = Mock(spec=discord.Message)
        message.id = next(ids)
        message.edit = AsyncMock(return_value=message)
        message.sent_kwargs = kwargs
        message.delete = AsyncMock(
            side_effect=lambda **kwargs: messages.pop(message.id, None)
        )
        messages[message.id] = message
        return message

    async def create_thread(**kwargs: object) -> Mock:
        thread = Mock(spec=discord.Thread)
        thread.id, thread.parent_id, thread.archived, thread.locked = (
            next(ids),
            20,
            False,
            False,
        )
        thread.guild = guild

        async def thread_send(**kwargs: object) -> Mock:
            message = await send(**kwargs)
            message.channel = thread
            return message

        async def purge(**kwargs: object) -> list[Mock]:
            deleted = [
                message for message in messages.values() if message.channel == thread
            ]
            for message in deleted:
                messages.pop(message.id)
            return deleted

        thread.send = AsyncMock(side_effect=thread_send)
        thread.purge = AsyncMock(side_effect=purge)
        thread.delete = AsyncMock(
            side_effect=lambda **kwargs: threads.pop(thread.id, None)
        )
        thread.fetch_message = AsyncMock(side_effect=fetch_message)
        thread.edit = AsyncMock(return_value=thread)
        threads[thread.id] = thread
        return thread

    channel = Mock(spec=discord.TextChannel)
    channel.id, channel.guild = 20, guild

    async def channel_send(**kwargs: object) -> Mock:
        message = await send(**kwargs)
        message.channel = channel
        return message

    async def channel_purge(**kwargs: object) -> list[Mock]:
        deleted = [
            message for message in messages.values() if message.channel == channel
        ]
        for message in deleted:
            messages.pop(message.id)
        return deleted

    channel.send = AsyncMock(side_effect=channel_send)
    channel.purge = AsyncMock(side_effect=channel_purge)
    channel.fetch_message = AsyncMock(side_effect=fetch_message)
    channel.create_thread = AsyncMock(side_effect=create_thread)
    guild.get_channel.side_effect = lambda channel_id: (
        channel if channel_id == 20 else None
    )
    client = Mock(spec=Client)
    client._database = database

    async def fetch_channel(channel_id: int) -> Mock:
        if channel_id not in threads:
            raise missing()
        return threads[channel_id]

    client.fetch_channel = AsyncMock(side_effect=fetch_channel)
    client.get_guild_timezone = AsyncMock(return_value="UTC")
    guild.fetch_channel = AsyncMock(side_effect=fetch_channel)
    module = QsModule(guild, client)
    assert await module.configure(20, 30, "2026-11-01", (0, 2, 4, 6, 22))
    return SimpleNamespace(
        module=module,
        guild=guild,
        channel=channel,
        role=role,
        moderator=moderator,
        client=client,
        messages=messages,
        threads=threads,
    )


def interaction(
    environment: SimpleNamespace, *, member_id: int = 100, roles: bool = True
) -> Mock:
    member = Mock(spec=discord.Member)
    member.id, member.guild = member_id, environment.guild
    member.display_name = f"Player {member_id}"
    member.roles = [environment.role, environment.moderator] if roles else []
    context = Mock(spec=discord.Interaction)
    context.type = discord.InteractionType.component
    context.guild_id, context.guild = 10, environment.guild
    context.channel, context.channel_id = environment.channel, 20
    context.user, context.locale = member, discord.Locale.german
    response_done = False

    async def acknowledge(**kwargs: object) -> None:
        nonlocal response_done
        response_done = True

    context.response = SimpleNamespace(
        send_message=AsyncMock(),
        defer=AsyncMock(side_effect=acknowledge),
        send_modal=AsyncMock(),
        edit_message=AsyncMock(),
        is_done=lambda: response_done,
    )
    context.followup = SimpleNamespace(send=AsyncMock(return_value=Mock()))
    original = Mock(spec=discord.InteractionMessage)
    original.delete = AsyncMock()
    context.original_response = AsyncMock(return_value=original)
    context.permissions = discord.Permissions(manage_messages=True)
    context.app_permissions = discord.Permissions(
        manage_messages=True, manage_threads=True
    )
    return context


def setup_button(panel: QsSetupView, action: str) -> SetupButton:
    return next(
        item
        for item in panel.children
        if isinstance(item, SetupButton) and item.action == action
    )


@pytest.mark.parametrize(
    ("locale", "label"),
    [
        (discord.Locale.german, "Anmeldungen"),
        (discord.Locale.american_english, "Signups"),
    ],
)
@pytest.mark.parametrize("count", [0, 1, 12, 100])
def test_main_overview_highlights_localized_signup_count(
    locale: discord.Locale,
    label: str,
    count: int,
) -> None:
    guild = Mock(spec=discord.Guild, preferred_locale=locale)
    phase = Phase(1, 1793491200, 42, None)
    embed = overview_embed(
        guild,
        Configuration(20, 30, "2026-11-01", None, None),
        (phase,),
        {1: tuple(range(count))},
        0,
    )
    field = embed.fields[0]
    assert field.name == "Phase 1"
    assert field.value.splitlines() == [
        f"👥 **{label}: {count}**",
        f"<t:{phase.starts_at}:F> – <t:{phase.ends_at}:t>",
        "<#42>",
    ]
    assert not field.inline
    assert len(field.value) <= 1024


@pytest.mark.parametrize(
    ("locale", "start_label", "end_label", "instructions"),
    [
        (
            discord.Locale.german,
            "Eruptionsstart",
            "Eruptionsende",
            (
                "- Anmelden: Phasenbutton klicken.",
                "- Abmelden: denselben Button erneut klicken.",
                "- Mehrere Phasen möglich – jede Anmeldung ist unabhängig.",
            ),
        ),
        (
            discord.Locale.american_english,
            "Eruption start",
            "Eruption end",
            (
                "- Join: click a phase button.",
                "- Leave: click the same button again.",
                "- Multiple phases allowed – each signup is independent.",
            ),
        ),
    ],
)
def test_main_overview_explains_signups_and_shows_eruption_without_role(
    locale: discord.Locale,
    start_label: str,
    end_label: str,
    instructions: tuple[str, ...],
) -> None:
    guild = Mock(spec=discord.Guild, preferred_locale=locale)
    configuration = Configuration(
        20, 30, "2026-11-01", None, None, eruption_start=1793570400
    )
    phase = Phase(1, configuration.eruption_start + 3600, 42, None)
    embed = overview_embed(guild, configuration, (phase,), {1: (100,)}, 3)
    description = embed.description
    assert description is not None
    assert f"{start_label}: <t:{configuration.eruption_start}:F>" in description
    assert f"{end_label}: <t:{configuration.eruption_end}:F>" in description
    assert description.split("\n\n")[-1].splitlines() == list(instructions)
    assert "**3 / 40**" in description
    assert "<@&" not in str(embed.to_dict())
    assert "Qs-Rolle" not in description
    assert "Qs role" not in description
    assert len(embed) <= 6000


@pytest.mark.asyncio
@pytest.mark.parametrize("reset_mode", [False, True])
@pytest.mark.parametrize(
    "locale", [discord.Locale.german, discord.Locale.american_english]
)
async def test_setup_menu_keeps_overview_and_separates_phase_controls(
    environment: SimpleNamespace,
    reset_mode: bool,
    locale: discord.Locale,
) -> None:
    environment.guild.preferred_locale = locale
    panel = await setup_view(environment.module, 20, 100, reset_mode=reset_mode)
    if locale == discord.Locale.german:
        expected = (
            [
                "Eruptionsstart festlegen",
                "Phasen Einstellung",
                "Bestätigung",
                "Abbrechen",
            ]
            if reset_mode
            else [
                "QS-Rolle",
                "Eruptionsstart festlegen",
                "Phasen Einstellung",
                "Ping Einstellungen",
                "Speichern",
                "Abbrechen",
            ]
        )
    else:
        expected = (
            ["Set eruption start", "Phase settings", "Confirmation", "Cancel"]
            if reset_mode
            else [
                "QS role",
                "Set eruption start",
                "Phase settings",
                "Ping settings",
                "Save",
                "Cancel",
            ]
        )
    assert [item.label for item in panel.children] == expected
    assert all(isinstance(item, SetupButton) and item.emoji for item in panel.children)
    assert all(len(row["components"]) <= 5 for row in panel.to_components())
    summary = panel.embed().to_dict()["fields"]
    assert all(len(field["value"]) <= 1024 for field in summary)
    assert len(panel.embed()) <= 6000
    context = interaction(environment)
    await setup_button(panel, "phases").callback(context)
    assert [type(item) for item in panel.children] == [
        PhaseCountSelect,
        PhaseSelect,
        HourSelect,
        DurationSelect,
        SetupButton,
    ]
    assert (
        context.response.edit_message.await_args.kwargs["embed"].to_dict()["fields"]
        == summary
    )
    await setup_button(panel, "back").callback(context)
    assert [item.label for item in panel.children] == expected
    assert panel.embed().to_dict()["fields"] == summary
    panel.stop()


@pytest.mark.asyncio
async def test_setup_role_and_date_actions_keep_the_overview(
    environment: SimpleNamespace,
) -> None:
    panel = await setup_view(environment.module, 20, 100)
    context = interaction(environment)
    await setup_button(panel, "role").callback(context)
    arguments = context.response.edit_message.await_args.kwargs
    assert arguments["embed"].to_dict()["fields"] == panel.embed().to_dict()["fields"]
    picker = arguments["view"]
    assert isinstance(picker, QsRoleSelection)
    back = next(item for item in picker.children if isinstance(item, SetupButton))
    await back.callback(context)
    assert picker.is_finished()
    assert context.response.edit_message.await_args.kwargs["view"] is panel
    await setup_button(panel, "date").callback(context)
    modal = context.response.send_modal.await_args.args[0]
    assert isinstance(modal, DateModal)
    with patch.object(
        modal.eruption, "parse", return_value=datetime(2026, 11, 2, tzinfo=UTC)
    ):
        await modal.on_submit(context)
    assert panel.date == "2026-11-02"
    assert context.response.edit_message.await_args.kwargs["view"] is panel
    assert len(panel.children) == 6
    panel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("event", PING_EVENTS)
async def test_ping_settings_are_draft_only_until_save(
    environment: SimpleNamespace,
    event: PingEvent,
) -> None:
    panel = await setup_view(environment.module, 20, 100)
    context = interaction(environment)
    await setup_button(panel, "pings").callback(context)
    assert len(panel.children) == 5
    toggle = next(
        item
        for item in panel.children
        if isinstance(item, PingButton) and item.event == event
    )
    await toggle.callback(context)
    assert not panel.ping_settings.is_enabled(event)
    summary = next(
        field for field in panel.embed().fields if field.name == "🔔 Automatische Pings"
    )
    assert "Aus" in summary.value
    configuration = await environment.module.qs.get(10, 20)
    assert configuration.ping_settings == PingSettings()
    await setup_button(panel, "back").callback(context)
    with patch.object(panel, "finish", AsyncMock()):
        await setup_button(panel, "save").callback(context)
    restored = await setup_view(environment.module, 20, 100)
    assert restored.ping_settings == replace(PingSettings(), **{event: False})
    panel.stop()
    restored.stop()


@pytest.mark.asyncio
async def test_setup_cancel_discards_all_draft_changes_and_rejects_strangers(
    environment: SimpleNamespace,
) -> None:
    panel = await setup_view(environment.module, 20, 100)
    context = interaction(environment)
    await setup_button(panel, "pings").callback(context)
    toggle = next(item for item in panel.children if isinstance(item, PingButton))
    await toggle.callback(interaction(environment, member_id=101))
    assert panel.ping_settings == PingSettings()
    await toggle.callback(context)
    await setup_button(panel, "back").callback(context)
    panel.role_id = 31
    panel.hours[0] = 1
    await setup_button(panel, "cancel").callback(context)
    context.delete_original_response.assert_awaited_once()
    assert panel.is_finished()
    restored = await setup_view(environment.module, 20, 100)
    assert restored.role_id == 30
    assert restored.hours[0] == 0
    assert restored.ping_settings == PingSettings()
    restored.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("disabled_event", PING_EVENTS)
async def test_automatic_ping_switches_are_independent_and_manual_ping_is_unaffected(
    environment: SimpleNamespace,
    disabled_event: PingEvent,
) -> None:
    module = environment.module
    settings = replace(PingSettings(), **{disabled_event: False})
    assert await module.configure(
        20, 30, "2026-11-01", (0, 2, 4, 6, 22), ping_settings=settings
    )
    phase = (await module.qs.phases(10, 20))[0]
    assert await module.qs.toggle(10, 20, 1, 100)
    thread = environment.threads[phase.thread_id]
    for event in PING_EVENTS:
        sends = environment.channel.send.await_count
        thread_sends = thread.send.await_count
        if event == "phase_start":
            assert await module.ping_participants(20, phase)
            assert thread.send.await_count - thread_sends == (event != disabled_event)
            assert environment.channel.send.await_count == sends
        else:
            assert await module.ping(20, event=event, phase_index=1)
            assert environment.channel.send.await_count - sends == (
                event != disabled_event
            )
            assert thread.send.await_count == thread_sends
    sends = environment.channel.send.await_count
    assert await module.ping(20)
    assert environment.channel.send.await_count == sends + 1


@pytest.mark.asyncio
async def test_disabled_notifications_are_consumed_and_settings_survive_reset(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    settings = PingSettings(False, False, False, False)
    assert await module.configure(
        20, 30, "2026-11-01", (0, 2, 4, 6, 22), ping_settings=settings
    )
    assert await module.qs.toggle(10, 20, 1, 100)
    for number in range(8):
        await module.qs.report(10, 20, 1, number, f"Player {number}", number)
    configuration = await module.qs.get(10, 20)
    start, end = configuration.eruption_start, configuration.eruption_end
    sends = environment.channel.send.await_count
    thread_sends = sum(
        thread.send.await_count for thread in environment.threads.values()
    )
    await module.notifications.tick(start + 1, start - 1)
    await module.notifications.tick(end + 1, start + 1)
    assert environment.channel.send.await_count == sends
    assert (
        sum(thread.send.await_count for thread in environment.threads.values())
        == thread_sends
    )
    current = await module.qs.get(10, 20)
    assert current.start_notified and current.end_notified
    phases = await module.qs.phases(10, 20)
    assert all(phase.start_notified for phase in phases)
    assert phases[0].goal_notified
    assert not module.notifications.pending
    await module.qs.configure(
        10,
        20,
        30,
        "2026-11-01",
        "UTC",
        tuple(phase.starts_at for phase in phases),
        ping_settings=PingSettings(),
    )
    await module.notifications.tick(end + 31, end + 1)
    assert environment.channel.send.await_count == sends
    assert (
        sum(thread.send.await_count for thread in environment.threads.values())
        == thread_sends
    )
    await module.qs.configure(
        10,
        20,
        30,
        "2026-11-01",
        "UTC",
        tuple(phase.starts_at for phase in phases),
        ping_settings=settings,
    )
    panel = await setup_view(module, 20, 100, reset_mode=True)
    context = interaction(environment)
    panel.date, panel.eruption_start = "2026-11-02", end
    await setup_button(panel, "save").callback(context)
    confirmation = context.response.edit_message.await_args.kwargs["view"]
    environment.channel.purge.assert_not_awaited()
    with patch.object(confirmation, "finish", AsyncMock()):
        await confirmation.confirm.callback(context)
    current = await module.qs.get(10, 20)
    assert current.eruption_start == end
    assert current.ping_settings == settings
    assert not current.start_notified and not current.end_notified
    assert not await module.qs.reports(10, 20)
    panel.stop()


@pytest.mark.asyncio
async def test_setup_creates_exact_five_threads_and_persistent_views(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    assert isinstance(module, MessageModuleProtocol)
    assert environment.channel.create_thread.await_count == 5
    assert len(module._views) == 6
    assert all(view.is_persistent() for view in module._views.values())
    configuration = await module.qs.get(10, 20)
    overview = environment.messages[configuration.message_id]
    embed = overview.sent_kwargs["embeds"][0]
    assert "0 / 40" in embed.description
    assert len(embed.fields) == 5
    assert [field.name for field in embed.fields] == [
        f"Phase {index}" for index in range(1, 6)
    ]
    assert all(
        field.value.startswith("👥 **Anmeldungen: 0**\n") for field in embed.fields
    )
    assert len(overview.sent_kwargs["view"].children) == 5
    assert all(
        len(environment.messages[phase.message_id].sent_kwargs["view"].children) == 2
        for phase in await module.qs.phases(10, 20)
    )


@pytest.mark.asyncio
async def test_restart_restores_views_without_duplicate_threads_or_messages(
    environment: SimpleNamespace,
) -> None:
    restored = QsModule(environment.guild, environment.client)
    assert await restored.sync(startup=True)
    assert await restored.ensure()
    assert environment.channel.create_thread.await_count == 5
    assert len(environment.messages) == 12
    assert len(restored._views) == 6


@pytest.mark.asyncio
async def test_archived_uncached_thread_is_reused(environment: SimpleNamespace) -> None:
    phase = (await environment.module.qs.phases(10, 20))[0]
    thread = environment.threads[phase.thread_id]
    thread.archived = True
    environment.guild.get_thread.side_effect = lambda thread_id: None
    assert await environment.module.ensure()
    thread.edit.assert_awaited_once_with(name="Phase 1 - 00:00 – 02:00", archived=False)
    assert environment.channel.create_thread.await_count == 5


@pytest.mark.asyncio
async def test_deleted_overview_restored_without_losing_data(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.qs.toggle(10, 20, 1, 100)
    await module.qs.report(10, 20, 1, 100, "Player", 1)
    configuration = await module.qs.get(10, 20)
    del environment.messages[configuration.message_id]
    assert await module.on_raw_message_delete(
        SimpleNamespace(guild_id=10, message_id=configuration.message_id)
    )
    new_configuration = await module.qs.get(10, 20)
    assert new_configuration.message_id != configuration.message_id
    assert await module.qs.members(10, 20, 1) == (100,)
    assert len(await module.qs.reports(10, 20)) == 1


@pytest.mark.asyncio
async def test_deleted_phase_thread_restored_and_link_updated(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    phase = (await module.qs.phases(10, 20))[0]
    del environment.threads[phase.thread_id]
    del environment.messages[phase.message_id]
    assert await module.on_raw_thread_delete(
        SimpleNamespace(guild_id=10, thread_id=phase.thread_id)
    )
    replacement = (await module.qs.phases(10, 20))[0]
    assert replacement.thread_id != phase.thread_id
    assert replacement.message_id != phase.message_id
    configuration = await module.qs.get(10, 20)
    embed = environment.messages[configuration.message_id].edit.await_args.kwargs[
        "embeds"
    ][0]
    assert f"<#{replacement.thread_id}>" in embed.fields[0].value


@pytest.mark.asyncio
async def test_multi_phase_signup_updates_both_overviews(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    for index in (1, 5):
        await module.toggle_phase(interaction(environment), 20, index)
    assert await module.qs.members(10, 20, 1) == (100,)
    assert await module.qs.members(10, 20, 5) == (100,)
    phase = (await module.qs.phases(10, 20))[0]
    embed = environment.messages[phase.members_message_id].edit.await_args.kwargs[
        "embeds"
    ][0]
    assert embed.fields[0].value == "1. <@100>"
    await module.toggle_phase(interaction(environment), 20, 1)
    assert await module.qs.members(10, 20, 1) == ()
    assert await module.qs.members(10, 20, 5) == (100,)


@pytest.mark.asyncio
async def test_member_without_role_cannot_join_or_report(
    environment: SimpleNamespace,
) -> None:
    context = interaction(environment, roles=False)
    await environment.module.toggle_phase(context, 20, 1)
    context.followup.send.assert_awaited()
    await environment.module.report_base(interaction(environment, roles=False), 20, 1)
    assert await environment.module.qs.members(10, 20, 1) == ()
    assert await environment.module.qs.reports(10, 20) == ()


@pytest.mark.asyncio
async def test_reporting_once_across_phases_updates_every_counter(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.report_base(interaction(environment), 20, 1)
    repeated = interaction(environment)
    await module.report_base(repeated, 20, 5)
    assert "bereits" in repeated.followup.send.await_args.args[0]
    assert len(await module.qs.reports(10, 20)) == 1
    for phase in await module.qs.phases(10, 20):
        message = environment.messages[phase.message_id]
        kwargs = (
            message.edit.await_args.kwargs
            if message.edit.await_args
            else message.sent_kwargs
        )
        embed = kwargs["embeds"][0]
        assert f"{1 if phase.index == 1 else 0} / 8" in embed.description


@pytest.mark.asyncio
async def test_invalid_phase_is_rejected_without_data(
    environment: SimpleNamespace,
) -> None:
    for number in (0, 41):
        context = interaction(environment)
        await environment.module.report_base(context, 20, number)
        context.followup.send.assert_awaited()
    assert await environment.module.qs.reports(10, 20) == ()


@pytest.mark.asyncio
async def test_role_rechecked_when_modal_is_submitted(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    phase = (await module.qs.phases(10, 20))[0]
    view = module._views[phase.message_id]
    context = interaction(environment)
    await view.children[0].callback(context)
    confirmation = context.response.send_message.await_args.kwargs["view"]
    assert isinstance(confirmation, BaseReportConfirmation)
    denied = interaction(environment, roles=False)
    denied.message = SimpleNamespace(delete=AsyncMock())
    await confirmation.confirm.callback(denied)
    confirmation.message.delete.assert_awaited_once_with()
    denied.message.delete.assert_not_awaited()
    assert await module.qs.reports(10, 20) == ()


@pytest.mark.asyncio
async def test_role_loss_removes_signups_but_keeps_base_history(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.qs.toggle(10, 20, 1, 100)
    await module.qs.report(10, 20, 1, 100, "Player", 0)
    before = interaction(environment).user
    after = interaction(environment, roles=False).user
    assert await module.on_member_update(before, after)
    assert await module.qs.members(10, 20, 1) == ()
    assert len(await module.qs.reports(10, 20)) == 1


@pytest.mark.asyncio
async def test_ping_explicitly_allows_only_configured_role(
    environment: SimpleNamespace,
) -> None:
    assert await environment.module.ping(20)
    mentions = environment.channel.send.await_args.kwargs["allowed_mentions"]
    assert mentions.roles == [environment.role]
    assert not mentions.users
    assert not mentions.everyone
    configuration = await environment.module.qs.get(10, 20)
    assert (
        environment.messages[configuration.message_id]
        .sent_kwargs["allowed_mentions"]
        .to_dict()["parse"]
        == []
    )


@pytest.mark.asyncio
async def test_ping_does_not_claim_notification_without_permission(
    environment: SimpleNamespace,
) -> None:
    environment.role.mentionable = False
    environment.guild.me = Mock(spec=discord.Member)
    environment.channel.permissions_for.return_value = discord.Permissions.none()
    initial_sends = environment.channel.send.await_count
    assert not await environment.module.ping(20)
    assert environment.channel.send.await_count == initial_sends


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["signup", "report"])
async def test_database_failure_is_explicitly_reported(
    environment: SimpleNamespace, action: str
) -> None:
    module = environment.module
    context = interaction(environment)
    if action == "signup":
        with patch.object(
            module.qs,
            "toggle",
            AsyncMock(side_effect=aiosqlite.OperationalError("locked")),
        ):
            await module.toggle_phase(context, 20, 1)
    else:
        with patch.object(
            module.qs,
            "report",
            AsyncMock(side_effect=aiosqlite.OperationalError("locked")),
        ):
            await module.report_base(context, 20, 1)
    assert "nicht gespeichert" in context.followup.send.await_args.args[0]
    assert await module.qs.members(10, 20, 1) == ()
    assert await module.qs.reports(10, 20) == ()


@pytest.mark.asyncio
async def test_discord_failure_is_visible_and_retry_reuses_thread(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    phase = (await module.qs.phases(10, 20))[0]
    environment.messages[phase.members_message_id].edit.side_effect = discord.Forbidden(
        Mock(status=403, reason="Forbidden"), "denied"
    )
    context = interaction(environment)
    await module.toggle_phase(context, 20, 1)
    assert await module.qs.members(10, 20, 1) == (100,)
    assert "nicht vollständig" in context.followup.send.await_args.args[0]
    environment.messages[phase.members_message_id].edit.side_effect = None
    assert await module.ensure()
    assert environment.channel.create_thread.await_count == 5


@pytest.mark.asyncio
async def test_setup_uses_project_role_picker_and_all_24_hours(
    environment: SimpleNamespace,
) -> None:
    panel = await setup_view(environment.module, 20, 100)
    await setup_button(panel, "phases").callback(interaction(environment))
    assert (
        next(item for item in panel.children if isinstance(item, HourSelect))
        .options[-1]
        .value
        == "23"
    )
    assert (
        len(
            next(
                item for item in panel.children if isinstance(item, HourSelect)
            ).options
        )
        == 24
    )
    assert (
        len(
            next(
                item for item in panel.children if isinstance(item, PhaseSelect)
            ).options
        )
        == 5
    )
    assert isinstance(QsRoleSelection(panel), QsRoleSelection)
    assert await panel.interaction_check(interaction(environment))
    assert not await panel.interaction_check(interaction(environment, member_id=101))
    assert not await panel.interaction_check(interaction(environment, roles=False))
    panel.stop()


def test_destroyed_base_listing_obeys_discord_limits_and_lists_all_40() -> None:
    guild = Mock(spec=discord.Guild, preferred_locale=discord.Locale.german)
    guild.get_member.return_value = None
    reports = tuple(
        BaseReport(999999999999999999 + index, (index % 5) + 1, f"Player {index}", 0)
        for index in range(1, 41)
    )
    embeds = bases_embeds(guild, reports)
    assert sum(len(embed) for embed in embeds) <= 6000
    assert all(len(embed.description) <= 4096 for embed in embeds)
    listing = "\n".join(embed.description for embed in embeds)
    assert all(f"Player {index}" in listing for index in range(1, 41))
    assert [line.split(". ", 1)[0] for line in listing.splitlines()] == [
        str(index) for index in range(1, 41)
    ]
    assert (
        len(
            member_list(
                guild, tuple(999999999999999999 + index for index in range(200))
            )
        )
        < 1024
    )


def test_numbered_lists_preserve_phase_filtering_and_embed_limits() -> None:
    guild = Mock(spec=discord.Guild, preferred_locale=discord.Locale.german)
    guild.get_member.return_value = None
    assert member_list(guild, (100, 101)) == "1. <@100>\n2. <@101>"
    assert (
        len(member_list(guild, tuple(10**20 - 1 - index for index in range(200))))
        <= 1024
    )
    reports = (
        BaseReport(100, 2, "Other", 0),
        BaseReport(101, 1, "First", 1),
        BaseReport(102, 1, "Second", 2),
    )
    embed = phase_embed(guild, Phase(1, 0, None, None), reports)
    assert embed.fields[0].value == "1. First\n2. Second"
    worst_case = tuple(BaseReport(index, 1, "*" * 32, index) for index in range(40))
    pages = bases_embeds(guild, worst_case)
    assert len(pages) > 1
    lines = [line for page in pages for line in page.description.splitlines()]
    assert [line.split(". ", 1)[0] for line in lines] == [
        str(index) for index in range(1, 41)
    ]
    assert all(len(page.description) <= 3000 for page in pages)
    assert sum(len(page) for page in pages) <= 6000


@pytest.mark.asyncio
async def test_setup_draft_editing_and_save_end_to_end(
    environment: SimpleNamespace,
) -> None:
    panel = await setup_view(environment.module, 20, 100)
    context = interaction(environment)
    await setup_button(panel, "phases").callback(context)
    phase_select = next(
        item for item in panel.children if isinstance(item, PhaseSelect)
    )
    with patch.object(
        discord.ui.Select, "values", new_callable=PropertyMock, return_value=["5"]
    ):
        await phase_select.callback(context)
    hour_select = next(item for item in panel.children if isinstance(item, HourSelect))
    with patch.object(
        discord.ui.Select, "values", new_callable=PropertyMock, return_value=["22"]
    ):
        await hour_select.callback(context)
    await setup_button(panel, "back").callback(context)
    picker = QsRoleSelection(panel)
    await picker.select_entities(context, [31])
    modal = DateModal(panel)
    with patch.object(
        modal.eruption, "parse", return_value=datetime(2026, 11, 2, tzinfo=UTC)
    ):
        await modal.on_submit(context)
    configuration = await environment.module.qs.get(10, 20)
    assert configuration.role_id == 30
    assert configuration.date == "2026-11-01"
    with patch.object(panel, "finish", AsyncMock()) as finish:
        save = next(
            item
            for item in panel.children
            if isinstance(item, SetupButton) and item.action == "save"
        )
        await save.callback(context)
        finish.assert_awaited_once()
    configuration = await environment.module.qs.get(10, 20)
    assert configuration.role_id == 31
    assert configuration.date == "2026-11-02"
    phases = await environment.module.qs.phases(10, 20)
    assert phases[-1].starts_at == 1793656800
    assert len(environment.messages) == 12
    panel.stop()


@pytest.mark.asyncio
async def test_qs_setup_command_opens_owner_bound_shared_panel(
    environment: SimpleNamespace,
) -> None:
    context = interaction(environment)
    context.client = SimpleNamespace(
        module_manager=SimpleNamespace(
            get_module=AsyncMock(return_value=environment.module)
        )
    )
    group = QsGroup()
    await group.setup.callback(group, context)
    view = context.response.send_message.await_args.kwargs["view"]
    assert view.owner_id == 100
    assert view.message is context.original_response.return_value
    assert context.response.send_message.await_args.kwargs["ephemeral"]
    view.stop()


@pytest.mark.asyncio
async def test_successful_and_invalid_base_form_submission(
    environment: SimpleNamespace,
) -> None:
    confirmation = BaseReportConfirmation(environment.module, 20, 5, 100)
    invalid = interaction(environment)
    invalid.user.id = 101
    await confirmation.confirm.callback(invalid)
    invalid.response.send_message.assert_awaited()
    assert await environment.module.qs.reports(10, 20) == ()
    context = interaction(environment)
    context.message = SimpleNamespace(delete=AsyncMock())
    assert all(isinstance(item, discord.ui.Button) for item in confirmation.children)
    await confirmation.confirm.callback(context)
    reports = await environment.module.qs.reports(10, 20)
    assert len(reports) == 1
    assert reports[0].display_name == "Player 100"
    assert reports[0].phase_index == 5


@pytest.mark.asyncio
async def test_channel_deletion_removes_only_qs_state_and_stops_views(
    environment: SimpleNamespace,
) -> None:
    views = tuple(environment.module._views.values())
    assert await environment.module.on_guild_channel_delete(environment.channel)
    assert await environment.module.qs.get(10, 20) is None
    assert not environment.module._views
    assert all(view.is_finished() for view in views)
    assert await environment.module.qs.database.fetch_one(
        "SELECT 1 FROM Servers WHERE Guild=10"
    )


def test_qs_commands_registered_without_queue_dependency() -> None:
    client = Client.__new__(Client)
    client.CommandTree = discord.app_commands.CommandTree(
        discord.Client(intents=discord.Intents.none())
    )
    client.registered_commands = 0
    asyncio.run(Client.register_commands(client))
    assert "qs" in {command.name for command in client.CommandTree.get_commands()}
    assert "queue" not in {
        command.name for command in client.CommandTree.get_commands()
    }
    assert {command.name for command in QsGroup().commands} == {
        "setup",
        "remove",
        "reset",
        "ping",
        "report",
        "withdraw",
    }


def test_catalogs_cover_all_new_qs_keys_in_both_languages() -> None:
    german = {
        key
        for key in RuntimeLocalizations["de"]
        if key.startswith(("qs.event.", "qs.admin."))
    }
    english = {
        key
        for key in RuntimeLocalizations["en"]
        if key.startswith(("qs.event.", "qs.admin."))
    }
    assert german == english


@pytest.mark.asyncio
async def test_manager_routes_raw_phase_thread_deletion(
    environment: SimpleNamespace,
) -> None:
    client = Mock()
    client.get_guild.return_value = environment.guild
    manager = Manager(client)
    receiver = SimpleNamespace(on_raw_thread_delete=AsyncMock(return_value=True))
    manager._modules_by_guild[10] = [receiver]
    payload = SimpleNamespace(guild_id=10, thread_id=123)
    assert await manager.on_raw_thread_delete(payload)
    receiver.on_raw_thread_delete.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_four_phases_and_durations_saved_from_setup(
    environment: SimpleNamespace,
) -> None:
    panel = await setup_view(environment.module, 20, 100)
    context = interaction(environment)
    await setup_button(panel, "phases").callback(context)
    selector = next(
        item for item in panel.children if isinstance(item, PhaseCountSelect)
    )
    with patch.object(
        discord.ui.Select, "values", new_callable=PropertyMock, return_value=["4"]
    ):
        await selector.callback(context)
    assert len(panel.hours) == 4
    assert (
        len(
            next(
                item for item in panel.children if isinstance(item, PhaseSelect)
            ).options
        )
        == 4
    )
    duration = next(item for item in panel.children if isinstance(item, DurationSelect))
    with patch.object(
        discord.ui.Select, "values", new_callable=PropertyMock, return_value=["3"]
    ):
        await duration.callback(context)
    await setup_button(panel, "back").callback(context)
    with patch.object(panel, "finish", AsyncMock()):
        save = next(
            item
            for item in panel.children
            if isinstance(item, SetupButton) and item.action == "save"
        )
        await save.callback(context)
    phases = await environment.module.qs.phases(10, 20)
    assert len(phases) == 4
    assert phases[0].duration_hours == 3
    assert phases[0].ends_at - phases[0].starts_at == 10800
    assert len(environment.threads) == 4
    panel.stop()


@pytest.mark.asyncio
async def test_single_role_selection_rejects_multiple_and_non_moderator(
    environment: SimpleNamespace,
) -> None:
    panel = await setup_view(environment.module, 20, 100)
    picker = QsRoleSelection(panel)
    await picker.select_entities(interaction(environment), [30, 31])
    assert panel.role_id == 30
    await picker.select_entities(interaction(environment, roles=False), [31])
    assert panel.role_id == 30
    picker.stop()
    panel.stop()


@pytest.mark.asyncio
async def test_reset_preserves_threads_clears_all_messages_data_and_notifications(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.qs.toggle(10, 20, 1, 100)
    await module.qs.report(10, 20, 1, 100, "Player", 1)
    await module.qs.notified(10, 20, "start")
    await module.qs.notified(10, 20, "end")
    await module.qs.notified(10, 20, "goal", 1)
    phases = await module.qs.phases(10, 20)
    for thread in environment.threads.values():
        await thread.send(content="unrelated pinned message")
    await environment.channel.send(content="unrelated main channel message")
    old_ids = set(environment.messages)
    assert await module.reset_tool(
        20,
        "2026-11-02",
        (0, 3, 6, 22),
        eruption_start=1793577600,
        durations=(3, 1, 2, 2),
    )
    new_phases = await module.qs.phases(10, 20)
    assert [phase.thread_id for phase in new_phases] == [
        phase.thread_id for phase in phases[:4]
    ]
    assert len(environment.threads) == 4
    environment.channel.purge.assert_awaited_once()
    channel_purge = environment.channel.purge.await_args.kwargs
    assert channel_purge["limit"] is None
    assert channel_purge["bulk"] is True
    assert channel_purge["reason"] == "Qs cycle reset"
    assert callable(channel_purge["check"])
    for phase in new_phases:
        purge = environment.threads[phase.thread_id].purge
        purge.assert_awaited_once()
        thread_purge = purge.await_args.kwargs
        assert thread_purge["limit"] is None
        assert thread_purge["bulk"] is False
        assert thread_purge["reason"] == "Qs cycle reset"
        assert callable(thread_purge["check"])
    assert await module.qs.members(10, 20, 1) == ()
    assert await module.qs.reports(10, 20) == ()
    configuration = await module.qs.get(10, 20)
    assert configuration.eruption_start == 1793577600
    assert configuration.eruption_end == 1793664000
    assert not configuration.start_notified and not configuration.end_notified
    assert all(not phase.goal_notified for phase in new_phases)
    assert not old_ids & {phase.message_id for phase in new_phases}
    assert all(phase.members_message_id in environment.messages for phase in new_phases)
    assert not {phase.members_message_id for phase in phases} & {
        phase.members_message_id for phase in new_phases
    }


@pytest.mark.asyncio
async def test_remove_deletes_only_managed_resources_and_data(
    environment: SimpleNamespace,
) -> None:
    unrelated = await environment.channel.send(content="keep this")
    phases = await environment.module.qs.phases(10, 20)
    assert await environment.module.remove_tool(20)
    assert await environment.module.qs.get(10, 20) is None
    assert await environment.module.qs.phases(10, 20) == ()
    assert not environment.threads
    assert unrelated.id in environment.messages
    assert not environment.module._views
    environment.channel.purge.assert_not_awaited()
    assert len(phases) == 5
    assert await environment.module.qs.database.fetch_one(
        "SELECT 1 FROM Servers WHERE Guild=10"
    )


@pytest.mark.asyncio
async def test_reset_rejects_schedule_before_deleting_anything(
    environment: SimpleNamespace,
) -> None:
    with pytest.raises(ValueError):
        await environment.module.reset_tool(
            20,
            "2026-11-02",
            (0, 3, 6, 23),
            eruption_start=1793577600,
            durations=(1, 2, 3, 3),
        )
    environment.channel.purge.assert_not_awaited()
    assert len(environment.threads) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reset", "remove"])
async def test_partial_cleanup_blocks_restoration_and_is_retryable(
    environment: SimpleNamespace, action: str
) -> None:
    module = environment.module
    phase = (await module.qs.phases(10, 20))[1]
    thread = environment.threads[phase.thread_id]
    operation = thread.purge if action == "reset" else thread.delete
    original = operation.side_effect
    operation.side_effect = discord.Forbidden(
        Mock(status=403, reason="Forbidden"), "denied"
    )

    async def execute() -> bool:
        if action == "remove":
            return await module.remove_tool(20)
        return await module.reset_tool(
            20,
            "2026-11-02",
            (0, 2, 4, 6, 22),
            eruption_start=1793577600,
            durations=(2,) * 5,
        )

    assert not await execute()
    configuration = await module.qs.get(10, 20)
    assert configuration.state == ("removing" if action == "remove" else "resetting")
    sends = environment.channel.send.await_count
    assert await module.on_raw_message_delete(
        SimpleNamespace(guild_id=10, message_id=configuration.message_id)
    )
    assert await module.ensure()
    assert environment.channel.send.await_count == sends
    operation.side_effect = original
    assert await execute()


@pytest.mark.asyncio
async def test_reset_draft_does_not_delete_until_confirmation(
    environment: SimpleNamespace,
) -> None:
    panel = await setup_view(environment.module, 20, 100, reset_mode=True)
    context = interaction(environment)
    save = next(
        item
        for item in panel.children
        if isinstance(item, SetupButton) and item.action == "save"
    )
    await save.callback(context)
    confirmation = context.response.edit_message.await_args.kwargs["view"]
    assert isinstance(confirmation, QsMaintenanceConfirmation)
    environment.channel.purge.assert_not_awaited()
    with patch.object(confirmation, "finish", AsyncMock()):
        await confirmation.confirm.callback(context)
    environment.channel.purge.assert_awaited()
    panel.stop()


@pytest.mark.asyncio
async def test_confirmation_rechecks_owner_permissions_and_cancel_is_safe(
    environment: SimpleNamespace,
) -> None:
    view = QsMaintenanceConfirmation(environment.module, 20, 100, action="remove")
    stranger = interaction(environment, member_id=101)
    await view.confirm.callback(stranger)
    environment.channel.purge.assert_not_awaited()
    assert await environment.module.qs.get(10, 20) is not None
    context = interaction(environment)
    context.permissions = discord.Permissions.none()
    assert not await view.interaction_check(context)
    context.permissions = discord.Permissions(manage_messages=True)
    context.message = SimpleNamespace(delete=AsyncMock())
    await view.cancel.callback(context)
    context.delete_original_response.assert_awaited_once()
    assert await environment.module.qs.get(10, 20) is not None


@pytest.mark.asyncio
async def test_start_end_notifications_once_and_no_offline_catchup(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    configuration = await module.qs.get(10, 20)
    start, end = configuration.eruption_start, configuration.eruption_end
    with patch.object(module, "ping", AsyncMock(return_value=True)) as ping:
        await module.notifications.tick(start - 1, None)
        ping.assert_not_awaited()
        await module.notifications.tick(start + 1, start - 1)
        ping.assert_awaited_once_with(20, event="start")
        await module.notifications.tick(start + 30, start + 1)
        assert ping.await_count == 1
        await module.notifications.tick(end + 1, end - 1)
        assert ping.await_count == 2
        assert ping.await_args.kwargs["event"] == "end"
    await module.qs.configure(
        10,
        20,
        30,
        "2026-11-02",
        "UTC",
        (end, end + 7200, end + 14400, end + 21600),
        eruption_start=end,
    )
    with patch.object(module, "ping", AsyncMock(return_value=True)) as ping:
        await module.notifications.tick(end + 86401, None)
        ping.assert_not_awaited()
    current = await module.qs.get(10, 20)
    assert current.start_notified and current.end_notified


@pytest.mark.asyncio
async def test_eight_base_target_ping_exactly_once_per_phase(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    with patch.object(module, "ping", AsyncMock(return_value=True)) as ping:
        for number in range(1, 8):
            await module.report_base(interaction(environment, member_id=number), 20, 1)
        ping.assert_not_awaited()
        await module.report_base(interaction(environment, member_id=8), 20, 1)
        ping.assert_awaited_once_with(20, event="goal", phase_index=1)
        await module.report_base(interaction(environment, member_id=9), 20, 1)
        await module.notifications.goals(20)
        assert ping.await_count == 1
    reports = await module.qs.reports(10, 20)
    assert len(reports) == 9
    phases = await module.qs.phases(10, 20)
    embed = environment.messages[phases[0].message_id].edit.await_args.kwargs["embeds"][
        0
    ]
    assert "9 / 8" in embed.description
    assert "überschritten" not in embed.description
    restored = QsModule(environment.guild, environment.client)
    assert (await restored.qs.phases(10, 20))[0].goal_notified


@pytest.mark.asyncio
async def test_notification_failure_retries_without_marking_delivered(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    start = (await module.qs.get(10, 20)).eruption_start
    with patch.object(module, "ping", AsyncMock(side_effect=[False, True])) as ping:
        await module.notifications.tick(start + 1, start - 1)
        assert not (await module.qs.get(10, 20)).start_notified
        await module.notifications.tick(start + 31, start + 1)
        assert ping.await_count == 2
        assert (await module.qs.get(10, 20)).start_notified


@pytest.mark.asyncio
async def test_disconnect_discards_window_and_shutdown_stops_worker(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    module.notifications.last_tick = 123.0
    client = Mock()
    manager = Manager(client)
    manager._modules_by_guild[10] = [module]
    await manager.on_disconnect()
    assert module.notifications.last_tick is None
    with patch.object(module.notifications.worker, "cancel") as cancel:
        await manager.close()
        cancel.assert_called_once()


@pytest.mark.asyncio
async def test_past_schedule_configured_online_does_not_trigger_catchup(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    start = (await module.qs.get(10, 20)).eruption_start
    with patch.object(module, "ping", AsyncMock(return_value=True)) as ping:
        await module.notifications.tick(start + 100, start + 70)
        ping.assert_not_awaited()
    assert (await module.qs.get(10, 20)).start_notified


@pytest.mark.asyncio
async def test_actual_notification_worker_starts_and_can_be_cancelled(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    module.client.is_ready.return_value = True
    ticked = asyncio.Event()

    async def tick(now: float, previous: float | None) -> None:
        ticked.set()

    with patch.object(module.notifications, "tick", side_effect=tick):
        task = module.notifications.worker.start()
        try:
            await asyncio.wait_for(ticked.wait(), timeout=2)
            assert module.notifications.worker.is_running()
        finally:
            module.notifications.stop()
            with pytest.raises(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_reset_command_opens_schedule_draft_and_remove_command_only_previews(
    environment: SimpleNamespace,
) -> None:
    context = interaction(environment)
    context.client = SimpleNamespace(
        module_manager=SimpleNamespace(
            get_module=AsyncMock(return_value=environment.module)
        )
    )
    group = QsGroup()
    await group.reset.callback(group, context)
    draft = context.response.send_message.await_args.kwargs["view"]
    assert draft.reset_mode
    draft.stop()
    await group.remove.callback(group, context)
    confirmation = context.response.send_message.await_args.kwargs["view"]
    assert isinstance(confirmation, QsMaintenanceConfirmation)
    environment.channel.purge.assert_not_awaited()
    assert len(environment.threads) == 5
    confirmation.stop()


@pytest.mark.asyncio
async def test_setup_refuses_to_drop_phase_with_reported_bases(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.qs.report(10, 20, 5, 100, "Player", 1)
    assert not await module.configure(20, 30, "2026-11-01", (0, 2, 4, 6))
    assert len(await module.qs.phases(10, 20)) == 5
    assert len(environment.threads) == 5
    assert len(await module.qs.reports(10, 20)) == 1


@pytest.mark.asyncio
async def test_evening_schedule_saved_displayed_and_reset_consistently(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    start = int(datetime(2026, 11, 1, 22, tzinfo=UTC).timestamp())
    assert await module.configure(
        20,
        30,
        "2026-11-01",
        (22, 8, 12, 16, 19),
        eruption_start=start,
        durations=(3, 3, 3, 3, 2),
    )
    phases = await module.qs.phases(10, 20)
    assert phases[0].starts_at == start
    assert phases[1].starts_at == start + 10 * 3600
    panel = await setup_view(module, 20, 100)
    fields = panel.embed().fields
    assert f"<t:{phases[0].starts_at}:F>" in fields[5].value
    assert f"<t:{phases[1].starts_at}:F>" in fields[6].value
    panel.stop()
    assert await module.reset_tool(
        20,
        "2026-11-02",
        (22, 8, 12, 16, 19),
        eruption_start=start + 86400,
        durations=(3, 3, 3, 3, 2),
    )
    reset_phases = await module.qs.phases(10, 20)
    assert [phase.starts_at for phase in reset_phases] == [
        phase.starts_at + 86400 for phase in phases
    ]


@pytest.mark.asyncio
async def test_target_notification_failure_is_reported_and_retryable(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    for number in range(1, 8):
        await module.qs.report(10, 20, 1, number, "Player", 1)
    context = interaction(environment, member_id=8)
    with patch.object(module, "ping", AsyncMock(return_value=False)):
        await module.report_base(context, 20, 1)
    assert "Ziel-Ping" in context.followup.send.await_args.args[0]
    assert not (await module.qs.phases(10, 20))[0].goal_notified
    with patch.object(module, "ping", AsyncMock(return_value=True)) as ping:
        assert await module.notifications.goals(20)
        ping.assert_awaited_once_with(20, event="goal", phase_index=1)


@pytest.mark.asyncio
async def test_player_name_is_shown_without_mentions_and_survives_departure(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    context = interaction(environment)
    context.user.display_name = "Moon Player"
    await module.report_base(context, 20, 1)
    reports = await module.qs.reports(10, 20)
    assert reports[0].display_name == "Moon Player"
    listing = bases_embeds(environment.guild, reports)[0].description
    assert "Moon Player" in listing
    assert "<@100>" not in listing
    environment.guild.get_member.return_value = SimpleNamespace(display_name="New Name")
    assert "New Name" in bases_embeds(environment.guild, reports)[0].description
    environment.guild.get_member.return_value = None
    assert "Moon Player" in bases_embeds(environment.guild, reports)[0].description


@pytest.mark.asyncio
async def test_cancel_base_report_does_not_record_data(
    environment: SimpleNamespace,
) -> None:
    view = BaseReportConfirmation(environment.module, 20, 1, 100)
    context = interaction(environment)
    context.message = SimpleNamespace(delete=AsyncMock())
    await view.cancel.callback(context)
    context.delete_original_response.assert_awaited_once()
    assert await environment.module.qs.reports(10, 20) == ()
    assert view.is_finished()


def test_player_report_names_remain_within_embed_limits() -> None:
    guild = Mock(spec=discord.Guild, preferred_locale=discord.Locale.german)
    guild.get_member.return_value = None
    reports = tuple(BaseReport(index, 1, "*" * 32, index) for index in range(40))
    from hmwz.modules.hs.qs.models import Phase

    embed = phase_embed(guild, Phase(1, 0, None, None), reports)
    assert all(len(field.value) <= 1024 for field in embed.fields)
    assert sum(len(embed) for embed in bases_embeds(guild, reports)) <= 6000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("timezone", "duration", "expected"),
    [
        ("UTC", 2, "21:00 – 23:00"),
        ("Europe/Berlin", 2, "22:00 – 00:00"),
        ("Europe/Berlin", 3, "22:00 – 01:00"),
    ],
)
async def test_signup_buttons_show_phase_period_in_configured_timezone(
    environment: SimpleNamespace, timezone: str, duration: int, expected: str
) -> None:
    start = int(datetime(2026, 11, 1, 21, tzinfo=UTC).timestamp())
    phase = Phase(1, start, None, None, duration)
    overview = OverviewView(environment.module, 20, (phase,), timezone)
    thread = PhaseView(environment.module, 20, phase)
    button = overview.children[0]
    assert button.label == f"Phase 1 : {expected}"
    assert button.custom_id == "qs:toggle:20:1"
    assert len(thread.children) == 2
    assert thread.children[0].custom_id == "qs:report:20:1"
    overview.stop()
    thread.stop()


@pytest.mark.asyncio
async def test_guild_timezone_update_refreshes_phase_period_buttons(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    environment.client.get_guild_timezone = AsyncMock(return_value="UTC")
    start = int(datetime(2026, 11, 1, 21, tzinfo=UTC).timestamp())
    assert await module.configure(
        20,
        30,
        "2026-11-01",
        (22, 8, 12, 16),
        durations=(3, 2, 2, 2),
        eruption_start=start,
    )
    assert await module._refresh(20)
    configuration = await module.qs.get(10, 20)
    overview = module._views[configuration.message_id]
    assert [button.label for button in overview.children] == [
        "Phase 1 : 22:00 – 01:00",
        "Phase 2 : 08:00 – 10:00",
        "Phase 3 : 12:00 – 14:00",
        "Phase 4 : 16:00 – 18:00",
    ]

    environment.client.get_guild_timezone.return_value = "Europe/Berlin"
    assert await module.on_guild_timezone_update()

    configuration = await module.qs.get(10, 20)
    phases = await module.qs.phases(10, 20)
    overview = module._views[configuration.message_id]
    assert [button.label for button in overview.children] == [
        "Phase 1 : 23:00 – 02:00",
        "Phase 2 : 09:00 – 11:00",
        "Phase 3 : 13:00 – 15:00",
        "Phase 4 : 17:00 – 19:00",
    ]
    for phase, button in zip(phases, overview.children):
        thread = module._views[phase.message_id]
        assert len(thread.children) == 2
        assert thread.children[0].custom_id == f"qs:report:20:{phase.index}"
        environment.threads[phase.thread_id].edit.assert_awaited_with(
            name=button.label.replace(" : ", " - "), archived=False
        )


@pytest.mark.asyncio
async def test_created_threads_use_number_and_period(
    environment: SimpleNamespace,
) -> None:
    names = [
        call.kwargs["name"]
        for call in environment.channel.create_thread.await_args_list
    ]
    assert names == [
        "Phase 1 - 00:00 – 02:00",
        "Phase 2 - 02:00 – 04:00",
        "Phase 3 - 04:00 – 06:00",
        "Phase 4 - 06:00 – 08:00",
        "Phase 5 - 22:00 – 00:00",
    ]


@pytest.mark.asyncio
async def test_participant_lists_are_only_posted_in_their_phase_threads(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.toggle_phase(interaction(environment, member_id=100), 20, 1)
    await module.toggle_phase(interaction(environment, member_id=101), 20, 2)
    configuration = await module.qs.get(10, 20)
    overview = environment.messages[configuration.message_id].edit.await_args.kwargs[
        "embeds"
    ][0]
    assert "<@100>" not in str(overview.to_dict())
    assert "<@101>" not in str(overview.to_dict())
    for phase in await module.qs.phases(10, 20):
        assert f"<#{phase.thread_id}>" in overview.fields[phase.index - 1].value
        field = overview.fields[phase.index - 1]
        assert field.name == f"Phase {phase.index}"
        assert field.value.splitlines()[0] == (
            f"👥 **Anmeldungen: {1 if phase.index in (1, 2) else 0}**"
        )
        participants = environment.messages[phase.members_message_id]
        kwargs = (
            participants.edit.await_args.kwargs
            if participants.edit.await_args
            else participants.sent_kwargs
        )
        embed = kwargs["embeds"][0]
        assert ("<@100>" in embed.fields[0].value) == (phase.index == 1)
        assert ("<@101>" in embed.fields[0].value) == (phase.index == 2)
        status = environment.messages[phase.message_id].sent_kwargs["embeds"][0]
        assert "<@100>" not in str(status.to_dict())
        assert "<@101>" not in str(status.to_dict())
        assert kwargs["view"] is None


@pytest.mark.asyncio
async def test_deleted_participant_embed_is_restored_without_duplicate_status(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.toggle_phase(interaction(environment), 20, 1)
    phase = (await module.qs.phases(10, 20))[0]
    old_id = phase.members_message_id
    del environment.messages[old_id]
    assert await module.on_raw_message_delete(
        SimpleNamespace(guild_id=10, message_id=old_id)
    )
    restored = (await module.qs.phases(10, 20))[0]
    assert restored.members_message_id != old_id
    assert restored.message_id == phase.message_id
    message = environment.messages[restored.members_message_id]
    assert message.sent_kwargs["view"] is None
    assert message.sent_kwargs["embeds"][0].fields[0].value == "1. <@100>"
    assert len(environment.messages) == 12


@pytest.mark.asyncio
async def test_refresh_uses_shared_message_loader(environment: SimpleNamespace) -> None:
    with patch(
        "hmwz.modules.hs.qs.module.fetch_message", wraps=fetch_message
    ) as loader:
        assert await environment.module.ensure()
    assert loader.await_count == 12
    assert all(
        call.kwargs == {"raise_on_error": True} for call in loader.await_args_list
    )


@pytest.mark.asyncio
async def test_main_overview_counts_track_join_leave_and_restart(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.toggle_phase(interaction(environment, member_id=100), 20, 1)
    await module.toggle_phase(interaction(environment, member_id=101), 20, 1)
    await module.toggle_phase(interaction(environment, member_id=100), 20, 2)
    configuration = await module.qs.get(10, 20)
    message = environment.messages[configuration.message_id]
    embed = message.edit.await_args.kwargs["embeds"][0]
    assert [field.name for field in embed.fields[:2]] == ["Phase 1", "Phase 2"]
    assert [field.value.splitlines()[0] for field in embed.fields[:2]] == [
        "👥 **Anmeldungen: 2**",
        "👥 **Anmeldungen: 1**",
    ]
    await module.toggle_phase(interaction(environment, member_id=100), 20, 1)
    restored = QsModule(environment.guild, environment.client)
    assert await restored.ensure()
    embed = message.edit.await_args.kwargs["embeds"][0]
    assert [field.name for field in embed.fields[:2]] == ["Phase 1", "Phase 2"]
    assert all(
        field.value.startswith("👥 **Anmeldungen: 1**\n") for field in embed.fields[:2]
    )
    assert "<@100>" not in str(embed.to_dict())
    assert "<@101>" not in str(embed.to_dict())


@pytest.mark.asyncio
async def test_remove_uses_shared_message_loader(environment: SimpleNamespace) -> None:
    with patch(
        "hmwz.modules.hs.qs.maintenance.fetch_message", wraps=fetch_message
    ) as loader:
        assert await environment.module.remove_tool(20)
    assert loader.await_count == 2
    assert all(
        call.kwargs == {"raise_on_error": True} for call in loader.await_args_list
    )


@pytest.mark.asyncio
async def test_player_withdraws_own_report_and_can_report_again(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.report_base(interaction(environment), 20, 1)
    player = interaction(environment)
    player.user.roles = [environment.role]
    phase = (await module.qs.phases(10, 20))[0]
    await module._views[phase.message_id].children[1].callback(player)
    confirmation = player.response.send_message.await_args.kwargs["view"]
    assert isinstance(confirmation, BaseReportConfirmation)
    confirmed = interaction(environment)
    confirmed.user.roles = [environment.role]
    await confirmation.confirm.callback(confirmed)
    assert await module.qs.reports(10, 20) == ()
    configuration = await module.qs.get(10, 20)
    assert (
        "0 / 40"
        in environment.messages[configuration.message_id]
        .edit.await_args.kwargs["embeds"][0]
        .description
    )
    await module.report_base(interaction(environment), 20, 2)
    assert (await module.qs.reports(10, 20))[0].phase_index == 2


@pytest.mark.asyncio
async def test_withdrawal_rejects_other_player_wrong_phase_and_lost_role(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.report_base(interaction(environment), 20, 1)
    player = interaction(environment, member_id=101)
    player.user.roles = [environment.role]
    await module.withdraw_base(player, 20, 1, 100)
    assert player.followup.send.await_count == 1
    own = interaction(environment)
    own.user.roles = [environment.role]
    await module.withdraw_base(own, 20, 2, 100)
    assert "Keine passende" in own.followup.send.await_args.args[0]
    denied = interaction(environment, roles=False)
    await module.withdraw_base(denied, 20, 1, 100)
    assert len(await module.qs.reports(10, 20)) == 1


@pytest.mark.asyncio
async def test_moderator_command_withdraws_foreign_report_and_revalidates_permissions(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.report_base(interaction(environment, member_id=101), 20, 1)
    moderator = interaction(environment)
    moderator.user.roles = [environment.moderator]
    phase = (await module.qs.phases(10, 20))[0]
    await module._views[phase.message_id].children[1].callback(moderator)
    assert "Keine passende" in moderator.response.send_message.await_args.args[0]
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    moderator.client = SimpleNamespace(module_manager=manager)
    target = interaction(environment, member_id=101).user
    target.display_name = "Moon"
    group = QsGroup()
    await group.withdraw.callback(group, moderator, target)
    confirmation = moderator.response.send_message.await_args.kwargs["view"]
    assert isinstance(confirmation, BaseReportConfirmation)
    assert "Moon" in moderator.response.send_message.await_args.args[0]
    assert "101" not in moderator.response.send_message.await_args.args[0]
    foreign = interaction(environment, member_id=102)
    await confirmation.confirm.callback(foreign)
    assert len(await module.qs.reports(10, 20)) == 1
    lost_privileges = interaction(environment)
    lost_privileges.user.roles = [environment.role]
    await confirmation.confirm.callback(lost_privileges)
    assert len(await module.qs.reports(10, 20)) == 1
    allowed = interaction(environment)
    allowed.user.roles = [environment.moderator]
    await module.withdraw_base(allowed, 20, 1, 101)
    assert await module.qs.reports(10, 20) == ()


@pytest.mark.asyncio
async def test_withdrawal_cancel_retains_data_and_closes_dialog(
    environment: SimpleNamespace,
) -> None:
    await environment.module.report_base(interaction(environment), 20, 1)
    confirmation = BaseReportConfirmation(
        environment.module, 20, 1, 100, withdraw_member_id=100
    )
    context = interaction(environment)
    await confirmation.cancel.callback(context)
    context.delete_original_response.assert_awaited_once()
    assert len(await environment.module.qs.reports(10, 20)) == 1


@pytest.mark.asyncio
async def test_withdrawal_does_not_retrigger_goal_ping(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    with patch.object(module, "ping", AsyncMock(return_value=True)) as ping:
        for member_id in range(1, 9):
            await module.report_base(
                interaction(environment, member_id=member_id), 20, 1
            )
        await module.withdraw_base(interaction(environment), 20, 1, 8)
        assert len(await module.qs.reports(10, 20)) == 7
        await module.report_base(interaction(environment, member_id=8), 20, 1)
        assert ping.await_count == 1
    assert (await module.qs.phases(10, 20))[0].goal_notified


@pytest.mark.asyncio
async def test_moderator_button_retracts_only_own_report_without_selection(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.report_base(interaction(environment), 20, 1)
    context = interaction(environment)
    phase = (await module.qs.phases(10, 20))[0]
    await module._views[phase.message_id].children[1].callback(context)
    view = context.response.send_message.await_args.kwargs["view"]
    assert isinstance(view, BaseReportConfirmation)
    assert view.withdraw_member_id == 100
    assert all(isinstance(item, discord.ui.Button) for item in view.children)
    assert "Player 100" in context.response.send_message.await_args.args[0]
    view.stop()


@pytest.mark.asyncio
async def test_moderator_report_command_saves_target_display_name(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    moderator = interaction(environment)
    moderator.user.roles = [environment.moderator]
    moderator.client = SimpleNamespace(
        module_manager=SimpleNamespace(get_module=AsyncMock(return_value=module))
    )
    target = interaction(environment, member_id=101).user
    target.roles = []
    target.display_name = "Moon Player"
    group = QsGroup()
    await group.report.callback(group, moderator, target, 2)
    view = moderator.response.send_message.await_args.kwargs["view"]
    assert "Moon Player" in moderator.response.send_message.await_args.args[0]
    assert "101" not in moderator.response.send_message.await_args.args[0]
    assert await module.qs.reports(10, 20) == ()
    confirmed = interaction(environment)
    confirmed.user.roles = [environment.moderator]
    await view.confirm.callback(confirmed)
    reports = await module.qs.reports(10, 20)
    assert len(reports) == 1
    assert reports[0].member_id == 101
    assert reports[0].display_name == "Moon Player"
    assert reports[0].phase_index == 2
    await module.report_base(interaction(environment), 20, 1, member=target)
    assert len(await module.qs.reports(10, 20)) == 1


@pytest.mark.asyncio
async def test_moderator_addition_rejects_lost_permissions_and_invalid_phase(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    group = QsGroup()
    moderator = interaction(environment)
    moderator.client = SimpleNamespace(
        module_manager=SimpleNamespace(get_module=AsyncMock(return_value=module))
    )
    target = interaction(environment, member_id=101).user
    await group.report.callback(group, moderator, target, 2)
    view = moderator.response.send_message.await_args.kwargs["view"]
    denied = interaction(environment)
    denied.user.roles = [environment.role]
    await view.confirm.callback(denied)
    assert await module.qs.reports(10, 20) == ()
    invalid = interaction(environment)
    await module.report_base(invalid, 20, 6, member=target)
    assert await module.qs.reports(10, 20) == ()
    assert invalid.followup.send.await_count == 1


def test_unavailable_legacy_report_does_not_display_numeric_identity() -> None:
    guild = Mock(spec=discord.Guild, preferred_locale=discord.Locale.german)
    guild.get_member.return_value = None
    report = BaseReport(123456789012345678, 1, "", 0)
    description = bases_embeds(guild, (report,))[0].description
    assert "123456789012345678" not in description
    assert "Anzeigename nicht verfügbar" in description


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["signup", "report", "withdraw"])
async def test_actions_acknowledge_before_waiting_for_channel_lock(
    environment: SimpleNamespace, action: str
) -> None:
    module = environment.module
    context = interaction(environment)
    acknowledged = asyncio.Event()
    original_defer = context.response.defer.side_effect

    async def defer(**kwargs: object) -> None:
        await original_defer(**kwargs)
        acknowledged.set()

    context.response.defer.side_effect = defer
    lock = module._lock(20)
    await lock.acquire()
    if action == "signup":
        task = asyncio.create_task(module.toggle_phase(context, 20, 1))
    elif action == "report":
        task = asyncio.create_task(module.report_base(context, 20, 1))
    else:
        task = asyncio.create_task(module.withdraw_base(context, 20, 1, 100))
    try:
        await asyncio.wait_for(acknowledged.wait(), timeout=1)
        assert not task.done()
        context.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        assert await module.qs.members(10, 20, 1) == ()
        assert await module.qs.reports(10, 20) == ()
    finally:
        lock.release()
        await task
    context.response.send_message.assert_not_awaited()
    context.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_acknowledgement_does_not_change_signup(
    environment: SimpleNamespace,
) -> None:
    context = interaction(environment)
    context.response.defer.side_effect = missing()
    with pytest.raises(discord.NotFound):
        await environment.module.toggle_phase(context, 20, 1)
    assert await environment.module.qs.members(10, 20, 1) == ()


@pytest.mark.asyncio
async def test_burst_signups_patch_only_affected_lists_and_overview_once(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    phases = await module.qs.phases(10, 20)
    configuration = await module.qs.get(10, 20)
    with patch("hmwz.modules.hs.qs.module.fetch_message", wraps=fetch_message) as fetch:
        await asyncio.gather(
            module.toggle_phase(interaction(environment, member_id=100), 20, 1),
            module.toggle_phase(interaction(environment, member_id=101), 20, 1),
            module.toggle_phase(interaction(environment, member_id=102), 20, 2),
        )
    assert fetch.await_count == 3
    expected = {
        configuration.message_id,
        phases[0].members_message_id,
        phases[1].members_message_id,
    }
    for message_id, message in environment.messages.items():
        assert message.edit.await_count == (1 if message_id in expected else 0)
    embed = environment.messages[configuration.message_id].edit.await_args.kwargs[
        "embeds"
    ][0]
    assert embed.fields[0].name == "Phase 1"
    assert embed.fields[0].value.startswith("👥 **Anmeldungen: 2**\n")
    assert embed.fields[1].name == "Phase 2"
    assert embed.fields[1].value.startswith("👥 **Anmeldungen: 1**\n")
    assert not module._pending_updates


@pytest.mark.asyncio
async def test_mixed_mutations_coalesce_without_editing_unrelated_messages(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    phases = await module.qs.phases(10, 20)
    configuration = await module.qs.get(10, 20)
    await asyncio.gather(
        module.toggle_phase(interaction(environment, member_id=100), 20, 1),
        module.report_base(interaction(environment, member_id=101), 20, 2),
        module.report_base(interaction(environment, member_id=102), 20, 2),
    )
    expected = {
        configuration.message_id,
        configuration.bases_message_id,
        phases[0].members_message_id,
        phases[1].message_id,
    }
    for message_id, message in environment.messages.items():
        assert message.edit.await_count == (1 if message_id in expected else 0)
    status = environment.messages[phases[1].message_id].edit.await_args.kwargs[
        "embeds"
    ][0]
    assert "2 / 8" in status.description


@pytest.mark.asyncio
async def test_batched_failure_notifies_every_saved_signup(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    phase = (await module.qs.phases(10, 20))[0]
    environment.messages[phase.members_message_id].edit.side_effect = discord.Forbidden(
        Mock(status=403, reason="Forbidden"), "denied"
    )
    first, second = (
        interaction(environment, member_id=100),
        interaction(environment, member_id=101),
    )
    await asyncio.gather(
        module.toggle_phase(first, 20, 1), module.toggle_phase(second, 20, 1)
    )
    assert await module.qs.members(10, 20, 1) == (100, 101)
    for context in (first, second):
        assert "nicht vollständig" in context.followup.send.await_args.args[0]
    assert environment.messages[phase.members_message_id].edit.await_count == 1
    environment.messages[phase.members_message_id].edit.side_effect = None
    assert await module.ensure()


@pytest.mark.asyncio
async def test_update_arriving_during_flush_is_not_lost(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    entered, release = asyncio.Event(), asyncio.Event()
    refresh = module._refresh
    calls = 0

    async def blocked_refresh(channel_id: int, **kwargs: object) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return await refresh(channel_id, **kwargs)

    with patch.object(module, "_refresh", side_effect=blocked_refresh):
        first = asyncio.create_task(
            module.toggle_phase(interaction(environment, member_id=100), 20, 1)
        )
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(
            module.toggle_phase(interaction(environment, member_id=101), 20, 1)
        )
        release.set()
        await asyncio.gather(first, second)
    assert calls == 2
    configuration = await module.qs.get(10, 20)
    assert (
        environment.messages[configuration.message_id]
        .edit.await_args.kwargs["embeds"][0]
        .fields[0]
        .value.splitlines()[0]
        == "👥 **Anmeldungen: 2**"
    )


@pytest.mark.asyncio
async def test_close_drains_queued_updates(environment: SimpleNamespace) -> None:
    module = environment.module
    async with module._lock(20):
        await module.qs.toggle(10, 20, 1, 100)
        task = module._queue_update(20, 1)
    await module.close()
    assert task.done() and task.result()
    assert not module._pending_updates


@pytest.mark.asyncio
async def test_withdrawal_batch_updates_only_base_surfaces(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.qs.report(10, 20, 1, 100, "First", 0)
    await module.qs.report(10, 20, 1, 101, "Second", 1)
    assert await module.ensure()
    for message in environment.messages.values():
        message.edit.reset_mock()
    configuration = await module.qs.get(10, 20)
    phases = await module.qs.phases(10, 20)
    await asyncio.gather(
        module.withdraw_base(interaction(environment), 20, 1, 100),
        module.withdraw_base(interaction(environment), 20, 1, 101),
    )
    expected = {
        configuration.message_id,
        configuration.bases_message_id,
        phases[0].message_id,
    }
    for message_id, message in environment.messages.items():
        assert message.edit.await_count == (1 if message_id in expected else 0)
    assert await module.qs.reports(10, 20) == ()


@pytest.mark.asyncio
async def test_selective_signup_update_recreates_deleted_participant_message(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    phase = (await module.qs.phases(10, 20))[0]
    del environment.messages[phase.members_message_id]
    await module.toggle_phase(interaction(environment), 20, 1)
    restored = (await module.qs.phases(10, 20))[0]
    assert restored.members_message_id != phase.members_message_id
    assert restored.message_id == phase.message_id
    assert (
        environment.messages[restored.members_message_id]
        .sent_kwargs["embeds"][0]
        .fields[0]
        .value
        == "1. <@100>"
    )
    environment.messages[phase.message_id].edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_phase_start_mentions_only_enrolled_players_once(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.qs.toggle(10, 20, 1, 100)
    await module.qs.toggle(10, 20, 1, 101)
    await module.qs.toggle(10, 20, 2, 102)
    phase = (await module.qs.phases(10, 20))[0]
    thread = environment.threads[phase.thread_id]
    thread.send.reset_mock()
    await module.notifications.tick(phase.starts_at + 1, phase.starts_at - 1)
    calls = [call for call in thread.send.await_args_list if "content" in call.kwargs]
    assert len(calls) == 1
    message = calls[0].kwargs
    assert "<@100>" in message["content"] and "<@101>" in message["content"]
    assert "<@102>" not in message["content"]
    mentions = message["allowed_mentions"]
    assert {member.id for member in mentions.users} == {100, 101}
    assert not mentions.roles and not mentions.everyone
    assert (await module.qs.phases(10, 20))[0].start_notified
    restored = QsModule(environment.guild, environment.client)
    await restored.notifications.tick(phase.starts_at + 31, phase.starts_at + 1)
    assert (
        len([call for call in thread.send.await_args_list if "content" in call.kwargs])
        == 1
    )


@pytest.mark.asyncio
async def test_phase_start_offline_skip_and_empty_phase(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    phase = (await module.qs.phases(10, 20))[0]
    await module.qs.toggle(10, 20, 1, 100)
    with patch.object(
        module, "ping_participants", AsyncMock(return_value=True)
    ) as ping:
        await module.notifications.tick(phase.starts_at + 1, None)
        ping.assert_not_awaited()
    second = (await module.qs.phases(10, 20))[1]
    thread = environment.threads[second.thread_id]
    thread.send.reset_mock()
    await module.notifications.tick(second.starts_at + 1, second.starts_at - 1)
    thread.send.assert_not_awaited()
    assert (await module.qs.phases(10, 20))[1].start_notified


@pytest.mark.asyncio
async def test_failed_phase_start_ping_retries_online(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    phase = (await module.qs.phases(10, 20))[0]
    with patch.object(
        module, "ping_participants", AsyncMock(side_effect=[False, True])
    ) as ping:
        await module.notifications.tick(phase.starts_at + 1, phase.starts_at - 1)
        assert not (await module.qs.phases(10, 20))[0].start_notified
        await module.notifications.tick(phase.starts_at + 31, phase.starts_at + 1)
        assert ping.await_count == 2
    assert (await module.qs.phases(10, 20))[0].start_notified


@pytest.mark.asyncio
async def test_phase_start_markers_reset_with_new_schedule(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.qs.notified(10, 20, "phase_start", 1)
    assert (await module.qs.phases(10, 20))[0].start_notified
    await module.qs.configure(
        10, 20, 30, "2026-11-01", "UTC", (0, 7200, 14400, 21600), reset=True
    )
    assert all(not phase.start_notified for phase in await module.qs.phases(10, 20))


@pytest.mark.asyncio
async def test_withdrawal_database_error_keeps_report_and_notifies(
    environment: SimpleNamespace,
) -> None:
    module = environment.module
    await module.report_base(interaction(environment), 20, 1)
    context = interaction(environment)
    with patch.object(
        module.qs,
        "withdraw_report",
        AsyncMock(side_effect=aiosqlite.OperationalError("failed")),
    ):
        await module.withdraw_base(context, 20, 1, 100)
    assert len(await module.qs.reports(10, 20)) == 1
    assert context.followup.send.await_count == 1
