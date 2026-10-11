from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "HmWz"))

import discord
from hmClient import Client
from HmLogger import get_logger, logging, setup_logging
from hmToken import Token

setup_logging(log_file="bot.log", level=logging.INFO, file_logging=True, async_logging=True)

logging.getLogger("discord").setLevel(logging.INFO)
logging.getLogger("asyncio").setLevel(logging.INFO)
logging.getLogger("aiosqlite").setLevel(logging.INFO)

logger = get_logger("HmDcBot")

TOKEN = Token().get()

if not TOKEN:
    logger.error("No bot token found!")
    logger.error("Please set WZ_BOT_TOKEN environment variable or run install script to configure token.")
    sys.exit(1)

intents: discord.Intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True


def main():
    bot = Client(intents=intents, global_command_sync=True)
    logger.info("Starting bot...")
    bot.run(TOKEN)
    logger.info("Bot stopped...")


if __name__ == "__main__":
    main()
