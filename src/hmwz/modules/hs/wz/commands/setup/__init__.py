from discord.app_commands import Group, checks, default_permissions, locale_str

from hmwz.i18n import CommandLocalizations

from .channel.add import add as channel_add
from .channel.remove import remove as channel_remove
from .role.add import add as role_add
from .role.remove import remove as role_remove

__all__ = ["SetupGroup"]


@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@default_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
class SetupGroup(Group):
    def __init__(self):
        super().__init__(
            name="setup",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.wz.setup.group", "Setup Commands"
                ),
                key="wz.setup.group.description",
            ),
        )
        self.add_command(channel_add)
        self.add_command(channel_remove)
        self.add_command(role_add)
        self.add_command(role_remove)
