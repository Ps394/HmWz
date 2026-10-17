from discord import Interaction
from discord.app_commands import command, describe, locale_str

from hmwz.i18n import CommandLocalizations, t

__all__ = ["AboutBot"]


@command(
    name="about-bot",
    description=locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.about", "About the bot"
        ),
        key="wz.about.description",
    ),
)
@describe(
    ephemeral=locale_str(
        CommandLocalizations.get("en", {}).get("parameter.description.ephemeral", "-"),
        key="ephemeral.description",
    )
)
async def AboutBot(interaction: Interaction, ephemeral: bool = True):
    bot_name = (
        interaction.client.user.name
        if interaction.client and interaction.client.user
        else "Bot"
    )
    message = "\n".join(
        [
            t(interaction, "wz.about.title", bot_name=bot_name),
            t(interaction, "wz.about.text"),
            t(interaction, "wz.about.link"),
        ]
    )
    await interaction.response.send_message(message, ephemeral=ephemeral)
