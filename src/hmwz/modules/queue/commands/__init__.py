from discord.app_commands import Group, checks, locale_str

from .setup import QueueSetupGroup


@checks.bot_has_permissions(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    embed_links=True,
    create_private_threads=True,
    manage_threads=True,
    send_messages_in_threads=True,
)
class QueueGroup(Group):
    def __init__(self) -> None:
        super().__init__(
            name="queue",
            description=locale_str(
                "Queue management",
                key="queue.group.description.queue",
            ),
        )
        self.add_command(QueueSetupGroup())


__all__ = ["QueueGroup"]
