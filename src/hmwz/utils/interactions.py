"""Formatting helpers for interaction and guild log context."""

from __future__ import annotations

import discord


def log_guild(guild: discord.Guild) -> str:
    """Return a consistent guild name and ID for log messages."""
    return f"{guild.name} ({guild.id}) =>"


def log_interaction(interaction: discord.Interaction) -> str:
    """Format member, channel, and guild names alongside IDs for logs."""
    user = interaction.user
    user_context = f"{user.name} / {user.display_name} ({user.id})"
    guild_context = (
        f"{interaction.guild.name} ({interaction.guild.id})"
        if interaction.guild is not None
        else "direct message"
    )
    channel = interaction.channel
    channel_context = (
        f"{channel.name} ({channel.id})"
        if channel is not None and hasattr(channel, "name")
        else f"channel ({channel.id})"
        if channel is not None
        else "unknown channel"
    )
    return f"{guild_context} - {channel_context} - {user_context}"
