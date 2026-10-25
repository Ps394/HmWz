from discord.app_commands import Group, checks, locale_str

from hmwz.i18n import CommandLocalizations

from . import clean_channels, reset_roles
from .setup.menu import setup

__all__ = ["WzGroup"]


@checks.bot_has_permissions(
    manage_roles=True,
    manage_channels=True,
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    attach_files=True,
    embed_links=True,
)
@checks.cooldown(1, 10, key=lambda i: (i.guild_id, i.user.id))
class WzGroup(Group):
    def __init__(self, bot):
        super().__init__(
            name="wz",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.wz.group", "WZ Commands"
                ),
                key="wz.group.description",
            ),
        )
        self.bot = bot
        self.add_command(setup)
        self.add_command(clean_channels.clean_channels)
        self.add_command(reset_roles.reset_roles)
