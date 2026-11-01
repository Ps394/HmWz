"""Slash-command group for registration management."""

from discord.app_commands import Group, checks, locale_str

from hmwz.i18n import CommandLocalizations

from . import  deregister, register, reset, snapshot, csv
from .setup import remove as registration_remove
from .setup import setup as registration_setup

__all__ = ["RegistrationGroup"]


@checks.bot_has_permissions(
    manage_roles=True,
    manage_channels=True,
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    attach_files=True,
    embed_links=True,
)
@checks.cooldown(
    1, 10, key=lambda interaction: (interaction.guild_id, interaction.user.id)
)
class RegistrationGroup(Group):
    """Group registration commands under the ``/registration`` namespace."""

    def __init__(self) -> None:
        super().__init__(
            name="registration",
            description=locale_str(
                CommandLocalizations.get("en", {}).get(
                    "group.description.registration.group", "Registration commands"
                ),
                key="registration.group.description",
            ),
        )
        #self.add_command(csv.csv)
        self.add_command(register.register)
        self.add_command(deregister.deregister)
        self.add_command(reset.reset)
        self.add_command(csv.csv)
        self.add_command(snapshot.snapshot)
        self.add_command(registration_setup)
        self.add_command(registration_remove)
