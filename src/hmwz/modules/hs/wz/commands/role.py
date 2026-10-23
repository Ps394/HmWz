from discord.app_commands import Group, checks, default_permissions, locale_str

from hmwz.i18n import CommandLocalizations

from .setup.role.add import add
from .setup.role.remove import remove

__all__ = ["RoleGroup"]


@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@default_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
class RoleGroup(Group):
    def __init__(self) -> None:
        super().__init__(
            name="role",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.wz.role.group", "Manage WZ roles"
                ),
                key="wz.role.group.description",
            ),
        )
        self.add_command(add)
        self.add_command(remove)
