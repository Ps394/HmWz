from __future__ import annotations

import sys

import discord
from HmLogger import get_logger, logging, setup_logging

from .hm_client import Client
from .token_storage import Token


def main() -> None:
    setup_logging(
        log_file="bot.log", level=logging.INFO, file_logging=True, async_logging=True
    )
    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.INFO)
    logging.getLogger("aiosqlite").setLevel(logging.INFO)

    logger = get_logger("HmWz")
    token = Token().get()
    if not token:
        logger.error("No bot token found!")
        logger.error(
            "Please set WZ_BOT_TOKEN environment variable or run install script to configure token."
        )
        sys.exit(1)

    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.message_content = True

    bot = Client(intents=intents, global_command_sync=True)
    logger.info("Starting bot...")
    bot.run(token)
    logger.info("Bot stopped...")


if __name__ == "__main__":
    main()
