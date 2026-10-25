from discord.app_commands import Group, checks, locale_str

from . import manage, reset, setup, submit

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
                "Configure donations, record donations, and manage donation data"
            ),
        )
        self.add_command(setup.setup)
        self.add_command(manage.remove)
        self.add_command(manage.delete)
        self.add_command(reset.reset)
        self.add_command(submit.submit)
