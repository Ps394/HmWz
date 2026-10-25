from discord.app_commands import Group, checks, default_permissions, locale_str

from hmwz.i18n import CommandLocalizations

from . import config_command, remove

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
        self.add_command(config_command.config)
        self.add_command(remove.remove)
