from discord.app_commands import Group, locale_str

from hmwz.i18n import CommandLocalizations

from . import configure, message, role_add, role_remove


class QsSetupGroup(Group):
    def __init__(self) -> None:
        super().__init__(
            name="setup",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.qs.setup.group", "Configure QS registration"
                ),
                key="qs.setup.group.description",
            ),
        )
        self.add_command(configure.configure)
        self.add_command(role_add.role_add)
        self.add_command(role_remove.role_remove)
        self.add_command(message.message)


__all__ = ["QsSetupGroup", "configure", "message", "role_add", "role_remove"]
