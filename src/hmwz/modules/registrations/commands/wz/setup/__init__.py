from discord.app_commands import Group, checks, default_permissions, locale_str

from hmwz.i18n import CommandLocalizations

from . import configure, message, roles


@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@default_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
class RegistrationSetupGroup(Group):
    def __init__(self) -> None:
        super().__init__(
            name="setup",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.wz.registration.setup.group",
                    "Registration setup commands",
                ),
                key="wz.registration.setup.group.description",
            ),
        )
        self.add_command(configure.configure)
        self.add_command(message.message)
        self.add_command(roles.add.add)
        self.add_command(roles.remove.remove)


__all__ = ["RegistrationSetupGroup", "configure", "message", "roles"]
