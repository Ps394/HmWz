"""
BotEmbed - Eine benutzerdefinierte Embed-Klasse für den Bot, die von discord.Embed erbt und ein einheitliches Format für alle Embeds bereitstellt.
"""
import discord
import typing

class BotEmbed(discord.Embed):
        """Erweiterung der Standard-Embed-Klasse von discord.py, um benutzerdefinierte Embeds mit einem einheitlichen Format zu erstellen."""
        def __init__(self, title: str, description: str, color: discord.Color, client_avatar: typing.Optional[discord.Asset] = None):
            super().__init__(title=title, description=description, color=color)
            self.set_footer(text=f"|", icon_url=client_avatar.url if client_avatar else None)
            self.timestamp = discord.utils.utcnow()