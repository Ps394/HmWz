import sys
import logging
from HmWz import setup_logging, Client, Intents, Token

setup_logging(log_file="bot.log", level=logging.INFO)

logging.getLogger("discord").setLevel(logging.INFO)
logging.getLogger("asyncio").setLevel(logging.INFO)
logging.getLogger("aiosqlite").setLevel(logging.INFO)

logger = logging.getLogger("Bot")

TOKEN = Token().get()

if not TOKEN:
    logger.error("No bot token found!")
    logger.error("Please set WZ_BOT_TOKEN environment variable or run install script to configure token.")
    sys.exit(1)

intents = Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

if __name__ == "__main__":
    bot = Client(intents=intents, global_command_sync=True)
    logger.info("Starting bot...")
    bot.run(TOKEN)
    logger.info("Bot stopped...")