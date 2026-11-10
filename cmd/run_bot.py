"""Telegram bot: answers searches with the deals stored in PostgreSQL."""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from src.infrastructure.telegram.client import TelegramService
from src.services.bot import BotService

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("cazachollos.bot")


async def main() -> int:
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    bot_token = os.getenv("BOT_TOKEN")
    if not api_id or not api_hash or not bot_token:
        logger.error("TELEGRAM_API_ID, TELEGRAM_API_HASH and BOT_TOKEN are required for the bot.")
        return 1

    telegram_service = TelegramService("cazachollos_bot", int(api_id), api_hash)
    bot = BotService(telegram_service)
    bot.register_handlers()  # before connecting, so no message is missed
    await telegram_service.start(bot_token=bot_token)
    logger.info("Bot started.")
    await telegram_service.run_until_disconnected()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
