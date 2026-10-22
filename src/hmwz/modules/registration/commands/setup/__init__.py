from discord.app_commands import Group, checks, default_permissions, locale_str

from hmwz.i18n import CommandLocalizations

from . import configure, event_log, message, remove, role

__all__ = ["RegistrationSetupGroup"]


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
        self.add_command(remove.remove)
        self.add_command(message.message)
        self.add_command(event_log.event_log)
        self.add_command(role.add.add)
        self.add_command(role.remove.remove)
