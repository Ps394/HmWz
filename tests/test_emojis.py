"""Application emoji synchronization and module rendering without Discord calls."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from hmwz.client import Client
from hmwz.emojis import EmojiUploader, UploadResult, emojis
from hmwz.emojis.uploader import ASSET_DIRECTORY, MAX_IMAGE_BYTES
from hmwz.modules.donation.models import (
    DonationRank,
    DonationRecord,
    DonationSummary,
    DonationType,
)
from hmwz.modules.donation.overview import DonationOverview
from hmwz.modules.donation.type.credit.views import DonationAmountOptionButton
from hmwz.modules.donation.type.rush.views import DonationTimeReductionButton
from hmwz.ui.messages import send_temporary_followup, send_temporary_response


@pytest.fixture
def client() -> Client:
    return Client(intents=discord.Intents.none())


@pytest.fixture
def guild(client: Client) -> discord.Guild:
    return discord.Guild(
        data={"id": "123", "name": "Test", "roles": [], "emojis": []},
        state=client._connection,
    )


def make_emoji(
    client: Client, name: str, emoji_id: int = 456, *, available: bool = True
) -> discord.Emoji:
    return discord.Emoji(
        guild=discord.Object(0),
        state=client._connection,
        data={
            "id": str(emoji_id),
            "name": name,
            "animated": False,
            "available": available,
        },
    )


@pytest.fixture
def uploader(client: Client, tmp_path: Path) -> EmojiUploader:
    client.emoji_uploader = EmojiUploader(client, tmp_path)
    return client.emoji_uploader


def write_asset(directory: Path, name: str = "credit.png") -> Path:
    asset = directory / name
    asset.write_bytes((ASSET_DIRECTORY / "credit.png").read_bytes())
    return asset


@pytest.mark.asyncio
async def test_uploads_missing_asset_and_reuses_it_on_next_sync(
    client: Client, uploader: EmojiUploader, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = write_asset(uploader.asset_directory)
    emoji = make_emoji(client, "credit")
    fetch = AsyncMock(side_effect=[[], [emoji]])
    create = AsyncMock(return_value=emoji)
    monkeypatch.setattr(client, "fetch_application_emojis", fetch)
    monkeypatch.setattr(client, "create_application_emoji", create)

    assert await uploader.sync() == UploadResult(created=("credit",))
    create.assert_awaited_once_with(name="credit", image=asset.read_bytes())
    assert emojis.get("credit", client) == "<:credit:456>"
    assert await uploader.sync() == UploadResult(reused=("credit",))
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_existing_emojis_are_available_without_local_assets(
    client: Client, uploader: EmojiUploader, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        client,
        "fetch_application_emojis",
        AsyncMock(
            return_value=[make_emoji(client, "success"), make_emoji(client, "other")]
        ),
    )
    assert await uploader.sync() == UploadResult()
    assert emojis.get("success", client) == "<:success:456>"
    assert emojis.get("other", client) == "<:other:456>"


@pytest.mark.asyncio
async def test_fetch_failure_clears_stale_mentions_and_logs_error(
    client: Client,
    uploader: EmojiUploader,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    uploader.mentions["credit"] = "<:credit:456>"
    monkeypatch.setattr(
        client,
        "fetch_application_emojis",
        AsyncMock(side_effect=discord.MissingApplicationID()),
    )
    assert await uploader.sync() == UploadResult(failed=("application",))
    assert emojis.get("credit", client) == emojis.CREDIT
    assert "Failed to fetch application emojis" in caplog.text


@pytest.mark.asyncio
async def test_upload_failure_does_not_prevent_later_assets(
    client: Client,
    uploader: EmojiUploader,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    write_asset(uploader.asset_directory)
    write_asset(uploader.asset_directory, "cristall.png")
    response = SimpleNamespace(status=403, reason="Forbidden")
    monkeypatch.setattr(client, "fetch_application_emojis", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        client,
        "create_application_emoji",
        AsyncMock(
            side_effect=[
                discord.Forbidden(response, "No access"),
                make_emoji(client, "cristall"),
            ]
        ),
    )
    assert await uploader.sync() == UploadResult(
        created=("cristall",), failed=("credit",)
    )
    assert emojis.get("credit", client) == emojis.CREDIT
    assert emojis.get("crystal", client) == "<:cristall:456>"
    assert "Failed to upload emoji credit" in caplog.text


@pytest.mark.asyncio
async def test_missing_asset_directory_is_reported(
    client: Client, uploader: EmojiUploader, monkeypatch: pytest.MonkeyPatch
) -> None:
    uploader.asset_directory /= "missing"
    monkeypatch.setattr(client, "fetch_application_emojis", AsyncMock(return_value=[]))
    assert await uploader.sync() == UploadResult(failed=("assets",))


@pytest.mark.asyncio
async def test_unavailable_existing_emoji_is_not_duplicated(
    client: Client, uploader: EmojiUploader, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_asset(uploader.asset_directory)
    monkeypatch.setattr(
        client,
        "fetch_application_emojis",
        AsyncMock(return_value=[make_emoji(client, "credit", available=False)]),
    )
    create = AsyncMock()
    monkeypatch.setattr(client, "create_application_emoji", create)
    assert await uploader.sync() == UploadResult(failed=("credit",))
    create.assert_not_awaited()
    assert emojis.get("credit", client) == emojis.CREDIT


@pytest.mark.asyncio
async def test_unavailable_uploaded_emoji_is_reported(
    client: Client,
    uploader: EmojiUploader,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    write_asset(uploader.asset_directory)
    monkeypatch.setattr(client, "fetch_application_emojis", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        client,
        "create_application_emoji",
        AsyncMock(return_value=make_emoji(client, "credit", available=False)),
    )
    assert await uploader.sync() == UploadResult(failed=("credit",))
    assert emojis.get("credit", client) == emojis.CREDIT
    assert "Uploaded application emoji credit is unavailable" in caplog.text


@pytest.mark.asyncio
async def test_invalid_duplicate_and_ignored_assets(
    client: Client, uploader: EmojiUploader, monkeypatch: pytest.MonkeyPatch
) -> None:
    for filename in (
        "bad-name.png",
        "x.png",
        "credit.png",
        "credit.gif",
        "ignored.txt",
    ):
        write_asset(uploader.asset_directory, filename)
    monkeypatch.setattr(client, "fetch_application_emojis", AsyncMock(return_value=[]))
    create = AsyncMock(return_value=make_emoji(client, "credit"))
    monkeypatch.setattr(client, "create_application_emoji", create)
    result = await uploader.sync()
    assert result.created == ()
    assert result.failed == ("bad-name.png", "credit.gif", "credit.png", "x.png")
    create.assert_not_awaited()


@pytest.mark.parametrize(
    "size,valid", [(0, False), (MAX_IMAGE_BYTES, True), (MAX_IMAGE_BYTES + 1, False)]
)
def test_image_size_limit(tmp_path: Path, size: int, valid: bool) -> None:
    image = (b"\x89PNG\r\n\x1a\n" + bytes(size))[:size]
    asset = tmp_path / "test.png"
    asset.write_bytes(image)
    if valid:
        assert EmojiUploader._read_image(asset) == image
    else:
        with pytest.raises(ValueError, match="256 KiB"):
            EmojiUploader._read_image(asset)


@pytest.mark.parametrize("header", [b"\xff\xd8\xff", b"GIF87a", b"GIF89a"])
def test_supported_image_headers(tmp_path: Path, header: bytes) -> None:
    asset = tmp_path / "test.gif"
    asset.write_bytes(header + b"image")
    assert EmojiUploader._read_image(asset) == header + b"image"


def test_invalid_image_header(tmp_path: Path) -> None:
    asset = tmp_path / "test.png"
    asset.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="PNG, JPEG, or GIF"):
        EmojiUploader._read_image(asset)


def test_lookup_is_client_scoped_and_supports_guilds(
    client: Client, guild: discord.Guild
) -> None:
    client.emoji_uploader.mentions["cristall"] = "<:cristall:456>"
    assert emojis.get("CRYSTAL", guild) == "<:cristall:456>"
    assert emojis.get("crystal", client) == "<:cristall:456>"
    assert emojis.get("crystal") == emojis.CRYSTAL
    assert emojis.get("success", guild) == emojis.SUCCESS
    with pytest.raises(KeyError):
        emojis.get("typo", client)


def test_render_uses_custom_mentions_without_changing_unicode_constants(
    client: Client,
) -> None:
    client.emoji_uploader.mentions["success"] = "<:success:456>"
    assert emojis.render(f"{emojis.SUCCESS} Saved {emojis.ERROR}", client) == (
        f"<:success:456> Saved {emojis.ERROR}"
    )
    assert emojis.SUCCESS == "\u2705"
    assert emojis.render("<:success:456>", client) == "<:success:456>"


@pytest.mark.asyncio
async def test_donation_buttons_use_emoji_properties_not_labels(
    client: Client, guild: discord.Guild
) -> None:
    from hmwz.modules.donation.module import DonationModule

    client.emoji_uploader.mentions.update(
        credit="<:credit:123456789012345678>",
        cristall="<:cristall:987654321098765432>",
    )
    module = DonationModule(guild, client)
    donation_type = DonationType("Credits", "simple", "credits", "free", (), ())
    credit = DonationAmountOptionButton(module, 1, donation_type, Decimal("500"), 0)
    rush = DonationTimeReductionButton(module, 1, "1h", Decimal("10"))
    assert credit.emoji is not None and credit.emoji.id == 123456789012345678
    assert rush.emoji is not None and rush.emoji.id == 987654321098765432
    assert "<:" not in (credit.label or "")
    assert "<:" not in (rush.label or "")


def test_ranking_uses_uploaded_currency_icon(
    client: Client, guild: discord.Guild
) -> None:
    client.emoji_uploader.mentions["credit"] = "<:credit:456>"
    embed = DonationOverview.create_ranking_embed(
        guild,
        DonationType("Credits", "simple", "credits", "free", (), ()),
        (DonationRank(1, "Donor", Decimal("500"), 0),),
    )
    assert "<:credit:456> 500 credits" in (embed.description or "")


def test_history_uses_uploaded_crystal_icon(
    client: Client, guild: discord.Guild
) -> None:
    client.emoji_uploader.mentions["cristall"] = "<:cristall:456>"
    embed = DonationOverview.create_history_embed(
        guild,
        DonationType("Rush", "time_reduction", "crystals", "choice", (), ("1h",)),
        (DonationRecord(1, "Donor", Decimal("10"), "crystals", "1h", "2026-10-31"),),
        DonationSummary(1, 1),
    )
    assert "<:cristall:456> 10" in (embed.description or "")


@pytest.mark.asyncio
async def test_concurrent_syncs_do_not_create_duplicates(
    client: Client, uploader: EmojiUploader, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_asset(uploader.asset_directory)
    emoji = make_emoji(client, "credit")
    monkeypatch.setattr(
        client, "fetch_application_emojis", AsyncMock(side_effect=[[], [emoji]])
    )
    create = AsyncMock(return_value=emoji)
    monkeypatch.setattr(client, "create_application_emoji", create)
    results = await asyncio.gather(uploader.sync(), uploader.sync())
    assert results == [
        UploadResult(created=("credit",)),
        UploadResult(reused=("credit",)),
    ]
    create.assert_awaited_once()


@pytest.mark.parametrize(
    "name,valid",
    [("ab", True), ("a" * 32, True), ("a" * 33, False), ("Ab_12", True)],
)
@pytest.mark.asyncio
async def test_emoji_name_limits(
    client: Client,
    uploader: EmojiUploader,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    valid: bool,
) -> None:
    write_asset(uploader.asset_directory, f"{name}.PNG")
    monkeypatch.setattr(client, "fetch_application_emojis", AsyncMock(return_value=[]))
    create = AsyncMock(return_value=make_emoji(client, name))
    monkeypatch.setattr(client, "create_application_emoji", create)
    result = await uploader.sync()
    if valid:
        assert result.created == (name,)
        assert emojis.get(name, client) == f"<:{name}:456>"
        create.assert_awaited_once()
    else:
        assert result.failed == (f"{name}.PNG",)
        create.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_syncs_emojis_before_registering_commands(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    for target, name in (
        (client._database, "execute"),
        (client._database, "remove_legacy_tables"),
        (client._servers, "migrate_legacy_servers"),
        (client.CommandTree, "set_translator"),
    ):
        monkeypatch.setattr(target, name, AsyncMock(return_value=True))
    sync = AsyncMock(return_value=UploadResult())
    monkeypatch.setattr(client.emoji_uploader, "sync", sync)

    async def register() -> None:
        sync.assert_awaited_once()

    monkeypatch.setattr(client, "register_commands", register)
    monkeypatch.setattr(
        "hmwz.client.monitoring.resource_monitor_loop", AsyncMock(return_value=None)
    )
    await client.setup_hook()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_temporary_messages_render_application_icons(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    client.emoji_uploader.mentions["success"] = "<:success:456>"
    interaction = Mock(spec=discord.Interaction)
    interaction.client = client
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock(return_value=None)
    interaction.original_response = AsyncMock(return_value=SimpleNamespace())
    delete = AsyncMock()
    monkeypatch.setattr("hmwz.ui.messages.delete_message", delete)
    await send_temporary_response(interaction, emojis.SUCCESS)
    interaction.response.send_message.assert_awaited_once_with(
        "<:success:456>", ephemeral=True
    )
    await send_temporary_followup(interaction, emojis.SUCCESS, delay=None)
    interaction.followup.send.assert_awaited_once_with(
        "<:success:456>", ephemeral=True, wait=True
    )
