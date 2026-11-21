import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from hmwz import events
from hmwz.modules.donation.models import DonationChannel, DonationSummary, DonationType
from hmwz.modules.donation.module import DonationModule
from hmwz.modules.donation.overview import DonationOverview


@pytest.mark.asyncio
async def test_donation_close_cancels_maintenance_task() -> None:
    finished = asyncio.Event()

    async def worker() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    task = asyncio.create_task(worker())
    module = cast(DonationModule, SimpleNamespace(_maintenance_task=task))
    await asyncio.sleep(0)

    await DonationModule.close(module)

    assert task.cancelled()
    assert finished.is_set()
    assert module._maintenance_task is None


@pytest.mark.asyncio
async def test_remove_channel_deletes_setup_and_history_before_messages() -> None:
    operations: list[str] = []
    configuration = SimpleNamespace(
        overview_message_id=501,
        ranking_message_id=502,
        history_message_id=503,
        ranking_channel_id=None,
    )
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=123,
            name="test guild",
            get_channel=Mock(),
        ),
    )

    async def on_message_delete(message_id: int) -> None:
        operations.append(f"message:{message_id}")
        payload = cast(
            events.RawMessageDeleteEvent,
            SimpleNamespace(
                guild_id=guild.id,
                channel_id=456,
                message_id=message_id,
            ),
        )
        assert await DonationModule.on_raw_message_delete(module, payload)

    def create_message(message_id: int) -> SimpleNamespace:
        async def delete() -> None:
            await on_message_delete(message_id)

        return SimpleNamespace(delete=AsyncMock(side_effect=delete))

    messages = {
        message_id: create_message(message_id) for message_id in (501, 502, 503)
    }
    channel = Mock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(side_effect=messages.__getitem__)
    guild.get_channel.return_value = channel
    donations = SimpleNamespace(
        get_channel=AsyncMock(side_effect=(configuration, None, None, None)),
        get_channels_by_ranking_message=AsyncMock(return_value=()),
        delete_channel=AsyncMock(
            side_effect=lambda **_: operations.append("setup") or True
        ),
    )
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=guild,
            donations=donations,
            _views={456: object()},
            _registered_message_ids={501},
            _rush_view_states={},
        ),
    )

    assert await DonationModule._remove_channel(module, 456)

    assert operations == ["setup", "message:501", "message:502", "message:503"]
    donations.delete_channel.assert_awaited_once_with(guild=guild, channel_id=456)
    assert 456 not in module._views


@pytest.mark.asyncio
async def test_sync_message_registers_replacement_view_for_existing_message() -> None:
    view = Mock(spec=discord.ui.View)
    embed = discord.Embed()
    message = SimpleNamespace(id=501, edit=AsyncMock())
    channel = Mock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    client = SimpleNamespace(add_view=Mock())
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=SimpleNamespace(name="test guild"),
            client=client,
            donations=SimpleNamespace(set_message=AsyncMock(return_value=True)),
            _registered_message_ids=set(),
        ),
    )

    assert await DonationModule._sync_message(
        module,
        channel=channel,
        channel_id=456,
        message_id=501,
        embed=embed,
        view=view,
    )

    client.add_view.assert_called_once_with(view, message_id=501)
    message.edit.assert_awaited_once_with(embed=embed, view=view)


@pytest.mark.asyncio
async def test_sync_message_persists_standalone_summary_message() -> None:
    embed = discord.Embed(
        title="2 Spenden | Aktuelles Enddatum: Montag 02.11.2026 - 12:00"
    )
    message = SimpleNamespace(id=503)
    channel = Mock(spec=discord.TextChannel)
    channel.send = AsyncMock(return_value=message)
    donations = SimpleNamespace(set_message=AsyncMock(return_value=True))
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=SimpleNamespace(name="test guild"),
            client=SimpleNamespace(add_view=Mock()),
            donations=donations,
            _registered_message_ids=set(),
        ),
    )

    assert await DonationModule._sync_message(
        module,
        channel=channel,
        channel_id=456,
        message_id=None,
        embed=embed,
        history=True,
    )

    donations.set_message.assert_awaited_once_with(
        guild=module.guild,
        channel_id=456,
        message_id=503,
        ranking=False,
        history=True,
    )


@pytest.mark.asyncio
async def test_deleting_donation_channel_removes_external_ranking() -> None:
    operations: list[str] = []
    message = SimpleNamespace(
        delete=AsyncMock(side_effect=lambda: operations.append("ranking"))
    )
    ranking_channel = Mock(spec=discord.TextChannel)
    ranking_channel.fetch_message = AsyncMock(return_value=message)
    guild = SimpleNamespace(
        id=123, name="test guild", get_channel=Mock(return_value=ranking_channel)
    )
    configuration = SimpleNamespace(ranking_channel_id=654, ranking_message_id=502)
    donations = SimpleNamespace(
        get_channel=AsyncMock(return_value=configuration),
        remove_channel=AsyncMock(
            side_effect=lambda **_: operations.append("setup") or True
        ),
        clear_ranking_channel=AsyncMock(return_value=()),
    )
    module = cast(DonationModule, SimpleNamespace(guild=guild, donations=donations))
    channel = cast(discord.abc.GuildChannel, SimpleNamespace(id=456, guild=guild))

    assert await DonationModule.on_guild_channel_delete(module, channel)

    assert operations == ["setup", "ranking"]
    ranking_channel.fetch_message.assert_awaited_once_with(502)
    donations.clear_ranking_channel.assert_awaited_once_with(
        guild=guild, ranking_channel_id=456
    )


@pytest.mark.asyncio
async def test_deleting_external_ranking_restores_its_donation_channel() -> None:
    guild = SimpleNamespace(id=123)
    owner = SimpleNamespace(channel_id=456, ranking_channel_id=654)
    donations = SimpleNamespace(
        get_channel=AsyncMock(return_value=None),
        get_channels_by_ranking_message=AsyncMock(return_value=(owner,)),
        set_message=AsyncMock(return_value=True),
    )
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=guild,
            donations=donations,
            compose_overview=AsyncMock(return_value=True),
        ),
    )
    payload = cast(
        events.RawMessageDeleteEvent,
        SimpleNamespace(guild_id=123, channel_id=654, message_id=502),
    )

    assert await DonationModule.on_raw_message_delete(module, payload)

    donations.set_message.assert_awaited_once_with(
        guild=guild, channel_id=456, message_id=None, ranking=True
    )
    module.compose_overview.assert_awaited_once_with(456)


@pytest.mark.asyncio
async def test_overview_publishes_all_time_ranking_in_selected_channel() -> None:
    donation_channel = Mock(spec=discord.TextChannel)
    ranking_channel = Mock(spec=discord.TextChannel)
    guild = SimpleNamespace(
        id=123,
        name="test guild",
        locale="de",
        get_channel=Mock(
            side_effect=lambda channel_id: {
                456: donation_channel,
                654: ranking_channel,
            }.get(channel_id)
        ),
    )
    configuration = DonationChannel(
        channel_id=456,
        overview_message_id=None,
        ranking_message_id=502,
        title="Donations",
        description="",
        goal_hours=None,
        show_ranking=True,
        show_donations=False,
        ranking_channel_id=654,
    )
    donations = SimpleNamespace(
        get_channel=AsyncMock(return_value=configuration),
        get_type=AsyncMock(
            return_value=DonationType("Credits", "simple", "Credits", "free", (), ())
        ),
        get_donations=AsyncMock(return_value=()),
        get_ranking=AsyncMock(return_value=()),
        get_summary=AsyncMock(return_value=DonationSummary(0, 0)),
    )
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=guild,
            donations=donations,
            _views={},
            _rush_view_states={},
            _sync_message=AsyncMock(return_value=True),
            _clear_history_message=AsyncMock(return_value=True),
        ),
    )

    assert await DonationModule.compose_overview(module, 456)

    ranking_call = module._sync_message.await_args_list[1].kwargs
    assert ranking_call["channel"] is ranking_channel
    assert ranking_call["channel_id"] == 456
    assert ranking_call["message_id"] == 502
    assert ranking_call["ranking"] is True
    assert ranking_call["embed"].title == "All-Time-Spendencharts – Donations"
    donations.get_ranking.assert_awaited_once_with(
        guild=guild, channel_id=456, unit="Credits"
    )


@pytest.mark.parametrize(
    ("locale", "prefix"),
    [("de", "All-Time-Spendencharts"), ("en", "All-time donation charts")],
)
def test_ranking_title_includes_donation_name_within_discord_limit(
    locale: str, prefix: str
) -> None:
    guild = cast(discord.Guild, SimpleNamespace(locale=locale))
    donation_type = DonationType("Credits", "simple", "Credits", "free", (), ())

    embed = DonationOverview.create_ranking_embed(
        guild, donation_type, (), donation_title="A" * 256
    )

    assert embed.title is not None
    assert embed.title.startswith(f"{prefix} – ")
    assert embed.title.endswith("…")
    assert len(embed.title) == 256


@pytest.mark.asyncio
async def test_moving_ranking_removes_old_message_before_saving() -> None:
    operations: list[str] = []
    guild = SimpleNamespace(id=123, name="test guild")
    configuration = SimpleNamespace(ranking_channel_id=654, ranking_message_id=502)
    donations = SimpleNamespace(
        get_history_units=AsyncMock(return_value=()),
        get_channel=AsyncMock(return_value=configuration),
        configure_channel=AsyncMock(
            side_effect=lambda **_: operations.append("save") or True
        ),
        configure_type=AsyncMock(return_value=True),
    )
    connection = object()

    @asynccontextmanager
    async def transaction():
        yield connection

    database = SimpleNamespace(transaction=transaction)
    module = cast(
        DonationModule,
        SimpleNamespace(
            guild=guild,
            database=database,
            client=SimpleNamespace(get_guild_timezone=AsyncMock(return_value="UTC")),
            donations=donations,
            _cycle_lock=lambda _: asyncio.Lock(),
            _clear_ranking_message=AsyncMock(
                side_effect=lambda *args, **kwargs: operations.append("clear") or True
            ),
            compose_overview=AsyncMock(return_value=True),
        ),
    )

    assert await DonationModule.configure_donation(
        module,
        456,
        title="Donations",
        description="",
        donation_type=DonationType("Credits", "simple", "Credits", "free", (), ()),
        show_ranking=True,
        ranking_channel_id=987,
    )

    assert operations == ["clear", "save"]
    module._clear_ranking_message.assert_awaited_once_with(
        456, 502, ranking_channel_id=654
    )
    assert donations.configure_channel.await_args.kwargs["ranking_channel_id"] == 987
    assert donations.configure_channel.await_args.kwargs["connection"] is connection
    assert donations.configure_type.await_args.kwargs["connection"] is connection
    module.compose_overview.assert_awaited_once_with(456)
