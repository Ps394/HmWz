"""Synchronize bundled images with Discord application emojis."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import discord

_logger = logging.getLogger(__name__)
ASSET_DIRECTORY: Final[Path] = Path(__file__).parent / "assets"
MAX_IMAGE_BYTES: Final[int] = 256 * 1024
_IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset({".png", ".jpg", ".jpeg", ".gif"})


@dataclass(frozen=True, slots=True)
class UploadResult:
    """Report created, reused, and failed emoji names for one synchronization."""

    created: tuple[str, ...] = ()
    reused: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()


class EmojiUploader:
    """Upload missing assets and retain application emoji mentions per client."""

    def __init__(
        self, client: discord.Client, asset_directory: Path = ASSET_DIRECTORY
    ) -> None:
        self.client = client
        self.asset_directory = asset_directory
        self.mentions: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def sync(self) -> UploadResult:
        """Reuse existing names and upload missing PNG, JPEG, or GIF assets.

        Discord and filesystem failures are logged and included in the result.
        Failed emojis remain unavailable so callers can use Unicode fallbacks.
        """
        async with self._lock:
            return await self._sync()

    async def _sync(self) -> UploadResult:
        self.mentions.clear()
        try:
            existing = await self.client.fetch_application_emojis()
        except (
            discord.HTTPException,
            discord.RateLimited,
            discord.MissingApplicationID,
        ):
            _logger.exception("Failed to fetch application emojis; using Unicode.")
            return UploadResult(failed=("application",))
        self.mentions.update(
            (emoji.name.lower(), str(emoji)) for emoji in existing if emoji.available
        )
        try:
            assets = sorted(
                asset
                for asset in self.asset_directory.iterdir()
                if asset.is_file() and asset.suffix.lower() in _IMAGE_SUFFIXES
            )
        except OSError:
            _logger.exception("Failed to read emoji assets: %s", self.asset_directory)
            return UploadResult(failed=("assets",))

        created: list[str] = []
        reused: list[str] = []
        failed: list[str] = []
        name_counts = Counter(asset.stem.lower() for asset in assets)
        for asset in assets:
            name = asset.stem
            if (
                re.fullmatch(r"[A-Za-z0-9_]{2,32}", name) is None
                or name_counts[name.lower()] > 1
            ):
                _logger.error("Invalid or duplicate emoji asset name: %s", asset.name)
                failed.append(asset.name)
                continue
            if name.lower() in self.mentions:
                reused.append(name)
                continue
            if any(emoji.name.lower() == name.lower() for emoji in existing):
                _logger.error("Application emoji %s exists but is unavailable.", name)
                failed.append(name)
                continue
            try:
                image = await asyncio.to_thread(self._read_image, asset)
                emoji = await self.client.create_application_emoji(
                    name=name, image=image
                )
            except (
                OSError,
                ValueError,
                discord.HTTPException,
                discord.RateLimited,
                discord.MissingApplicationID,
            ):
                _logger.exception("Failed to upload emoji %s; using Unicode.", name)
                failed.append(name)
                continue
            if not emoji.available:
                _logger.error("Uploaded application emoji %s is unavailable.", name)
                failed.append(name)
                continue
            self.mentions[name.lower()] = str(emoji)
            created.append(name)
        result = UploadResult(tuple(created), tuple(reused), tuple(failed))
        _logger.info(
            "Application emojis: %s created, %s reused, %s failed.",
            len(created),
            len(reused),
            len(failed),
        )
        return result

    @staticmethod
    def _read_image(asset: Path) -> bytes:
        with asset.open("rb") as source:
            image = source.read(MAX_IMAGE_BYTES + 1)
        if not image or len(image) > MAX_IMAGE_BYTES:
            raise ValueError("Emoji images must be nonempty and at most 256 KiB.")
        if not (
            image.startswith(b"\x89PNG\r\n\x1a\n")
            or image.startswith(b"\xff\xd8\xff")
            or image.startswith((b"GIF87a", b"GIF89a"))
        ):
            raise ValueError("Emoji images must be PNG, JPEG, or GIF.")
        return image
