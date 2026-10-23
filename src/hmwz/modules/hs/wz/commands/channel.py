from discord.app_commands import Group, checks, default_permissions, locale_str

from hmwz.i18n import CommandLocalizations

from .setup.channel.add import add
from .setup.channel.remove import remove

__all__ = ["ChannelGroup"]


@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@default_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
class ChannelGroup(Group):
    def __init__(self) -> None:
        super().__init__(
            name="channel",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.wz.channel.group", "Manage WZ channels"
                ),
                key="wz.channel.group.description",
            ),
        )
        self.add_command(add)
        self.add_command(remove)
