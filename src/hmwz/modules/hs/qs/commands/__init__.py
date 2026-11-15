"""Slash-command group for Qs event management."""

from discord import app_commands


from .remove import remove
from .report import report
from .reset import reset
from .setup import setup
from .withdraw import withdraw

__all__ = ["QsGroup"]


@app_commands.guild_only()
@app_commands.checks.bot_has_permissions(
    view_channel=True,
    send_messages=True,
    embed_links=True,
    read_message_history=True,
    create_public_threads=True,
    send_messages_in_threads=True,
    manage_threads=True,
)
class QsGroup(app_commands.Group):
    """Expose Qs commands under the ``/qs`` namespace."""

    def __init__(self) -> None:
        super().__init__(
            name="qs",
            description=app_commands.locale_str(
                "Qs event commands", key="qs.event.group"
            ),
        )
        for command in (report, withdraw, setup, remove, reset):
            self.add_command(command)
