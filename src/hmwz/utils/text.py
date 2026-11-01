"""Safe formatting of user-provided Discord text."""

import discord


def escape_discord_text(text: str) -> str:
    """Escape Markdown and mentions without truncating user-provided text.

    Args:
        text: Plain text to insert into a Discord message or embed.

    Returns:
        Text with Markdown and mention syntax escaped.
    """
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text))
