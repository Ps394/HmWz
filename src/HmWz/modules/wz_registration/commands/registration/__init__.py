from discord.app_commands import Group, checks, locale_str

from hmwz.i18n import CommandLocalizations

from . import csv, purge, reset

__all__ = ["RegistrationGroup"]


@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
class RegistrationGroup(Group):
    def __init__(self):
        super().__init__(
            name="registration",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.wz.registration.group", "Registration Commands"
                ),
                key="wz.registration.group.description",
            ),
        )
        self.add_command(reset.reset)
        self.add_command(purge.purge)
        self.add_command(csv.csv)
