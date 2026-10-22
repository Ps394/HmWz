from discord.app_commands import Group, checks, locale_str

from hmwz.i18n import CommandLocalizations
from hmwz.modules.registrations.commands.qs import reset
from hmwz.modules.registrations.commands.qs.setup import QsSetupGroup


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
        self.add_command(QsSetupGroup())
        self.add_command(reset.reset)


__all__ = ["QsGroup"]
