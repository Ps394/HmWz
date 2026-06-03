from discord.app_commands import command, locale_str
from discord import Interaction
from i18n import CommandLocalizations, t

__all__ = [
    "AboutBot"
]

@command(
    name="about-bot",
    description=locale_str(
        CommandLocalizations.get("en", {}).get("wz.about.description", "About the bot"),
        key="wz.about.description"
    )
)
async def AboutBot(interaction: Interaction, ephemeral: bool = True):
    bot_name = interaction.client.user.name if interaction.client and interaction.client.user else "Bot"
    message = "\n".join(
        [
            t(interaction, "wz.about.title", bot_name=bot_name),
            t(interaction, "wz.about.line1"),
            t(interaction, "wz.about.line2"),
            t(interaction, "wz.about.line3"),
            t(interaction, "wz.about.line4"),
            t(interaction, "wz.about.link")
        ]
    )
    await interaction.response.send_message(message, ephemeral=ephemeral)




