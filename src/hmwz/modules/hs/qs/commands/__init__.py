from discord.app_commands import Group, checks, locale_str

from hmwz.i18n import CommandLocalizations

from . import reset_channels, reset_roles
from .setup.menu import setup


@checks.bot_has_permissions(
    manage_roles=True,
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    embed_links=True,
)
class QsGroup(Group):
    def __init__(self) -> None:
        super().__init__(
            name="qs",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.qs.group", "QS registration commands"
                ),
                key="qs.group.description",
            ),
        )
        self.add_command(setup)
        self.add_command(reset_roles.reset_roles)
        self.add_command(reset_channels.reset_channels)


__all__ = ["QsGroup"]
