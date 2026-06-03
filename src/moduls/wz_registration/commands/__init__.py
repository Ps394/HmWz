from discord.app_commands import Group, checks, locale_str, command
from discord import Interaction

from i18n import CommandLocalizations, t

from . import setup, registration

__all__ = ["WzGroup"]


@checks.bot_has_permissions(
    manage_roles=True,
    manage_channels=True,
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    attach_files=True,
)
@checks.cooldown(1, 10, key=lambda i: (i.guild_id, i.user.id))
class WzGroup(Group):
    def __init__(self, bot):
        super().__init__(
            name="wz",
            description=locale_str(
                CommandLocalizations.get("en", {}).get("wz.group.description", "WZ Commands"),
                key="wz.group.description",
            ),
        )
        self.bot = bot
        self.add_command(setup.SetupGroup())
        self.add_command(registration.RegistrationGroup())

    @command(
        name="about-bot",
        description=locale_str(
            CommandLocalizations.get("en", {}).get("wz.about.description", "About the bot"),
            key="wz.about.description",
        ),
    )
    async def about_bot(self, interaction: Interaction, ephemeral: bool = True):
        bot_name = self.bot.user.name if self.bot and self.bot.user else "Bot"
        message = "\n".join(
            [
                t(interaction, "wz.about.title", bot_name=bot_name),
                t(interaction, "wz.about.line1"),
                t(interaction, "wz.about.line2"),
                t(interaction, "wz.about.line3"),
                t(interaction, "wz.about.line4"),
                t(interaction, "wz.about.link"),
            ]
        )
        await interaction.response.send_message(message, ephemeral=ephemeral)
