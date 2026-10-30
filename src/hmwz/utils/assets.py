from __future__ import annotations

import discord

def get_client_avatar(client: discord.Client) -> discord.Asset | None:
    return client.user.avatar if client.user else None
