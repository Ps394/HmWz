from discord.app_commands import Group, checks, default_permissions, locale_str

from hmwz.i18n import CommandLocalizations

from . import configure, message, purge_channels, roles

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
        self.add_command(configure.configure)
        self.add_command(message.message)
        self.add_command(roles.add.add)
        self.add_command(roles.remove.remove)
        self.add_command(purge_channels.add.add)
        self.add_command(purge_channels.remove.remove)
