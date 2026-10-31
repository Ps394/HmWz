"""Shared embed construction helpers."""

from __future__ import annotations

from datetime import datetime

import discord

DEFAULT_EMBED_COLOR = discord.Color.blurple()


def create_embed(
    *,
    title: str | None = None,
    description: str | None = None,
    color: discord.Color | int | None = None,
    client_avatar: discord.Asset | None = None,
    footer_text: str | None = "|",
    timestamp: datetime | None = None,
) -> discord.Embed:
    """Create an embed with the bot's shared color, footer, and timestamp defaults."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=DEFAULT_EMBED_COLOR if color is None else color,
        timestamp=discord.utils.utcnow() if timestamp is None else timestamp,
    )
    if footer_text is not None:
        embed.set_footer(
            text=footer_text,
            icon_url=client_avatar.url if client_avatar is not None else None,
        )
    return embed
