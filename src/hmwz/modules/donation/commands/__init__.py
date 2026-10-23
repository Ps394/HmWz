from discord.app_commands import Group, checks, locale_str

from . import setup, submit

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
            name="spenden",
            description=locale_str("Spendenübersicht und Spenden erfassen"),
        )
        self.add_command(setup.DonationSetupGroup())
        self.add_command(submit.submit)
