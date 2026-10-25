from discord.app_commands import Group, checks, locale_str

from hmwz.i18n import CommandLocalizations

from . import manage, reset, setup

__all__ = ["DonationGroup"]


@checks.bot_has_permissions(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    embed_links=True,
)
class DonationGroup(Group):
    """Commands for donation entry and channel setup."""

    def __init__(self) -> None:
        super().__init__(
            name="donation",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.donation.group",
                    "Configure donations and manage donation data",
                ),
                key="donation.group.description",
            ),
        )
        self.add_command(setup.setup)
        self.add_command(manage.remove)
        self.add_command(reset.reset)
