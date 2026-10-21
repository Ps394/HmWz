from discord.app_commands import Group, locale_str

from hmwz.i18n import CommandLocalizations

from . import add, list, remove

__all__ = ["AccountGroup"]


class AccountGroup(Group):
    def __init__(self) -> None:
        super().__init__(
            name="account",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.account.group", "Account Commands"
                ),
                key="account.group.description",
            ),
        )
        self.add_command(add.account_add)
        self.add_command(remove.account_remove)
        self.add_command(list.account_list)
