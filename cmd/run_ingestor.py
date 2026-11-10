"""Ingestor: listens to the Telegram groups (LIVE) or replays a JSONL file (REPLAY) and stores the deals."""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from src.infrastructure.ingestion.factory import IngestionFactory
from src.infrastructure.telegram.client import TelegramService
from src.services.ingestor import IngestorService
from src.services.schedule import within_active_hours

# Load env in case it's run locally without docker compose
load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("cazachollos.ingestor")


async def main() -> int:
    mode = os.getenv("INGESTION_MODE", "LIVE").upper()
    # Scheduled passes (WEB): outside ACTIVE_HOURS (Madrid time, e.g. "7-24") the pass ends right away
    active = os.getenv("ACTIVE_HOURS", "")
    if mode == "WEB" and not within_active_hours(active):
        logger.info("Outside the active hours (%s, Madrid time): nothing to do.", active)
        return 0
    telegram_service = None
    if mode == "LIVE":
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        if not api_id or not api_hash:
            logger.error(
                "TELEGRAM_API_ID and TELEGRAM_API_HASH are required in LIVE mode (or use INGESTION_MODE=REPLAY)."
            )
            return 1
        try:
            api_id_int = int(api_id)
        except ValueError:
            logger.error("TELEGRAM_API_ID must be an integer, got %r", api_id)
            return 1
        session_name = os.getenv("TELEGRAM_SESSION_NAME", "cazachollos_ingestor")
        telegram_service = TelegramService(session_name, api_id_int, api_hash)

    try:
        strategy = IngestionFactory.get_strategy(telegram_service)
        await IngestorService(strategy).start()
    except Exception:
        logger.exception("Ingestor failed")
        return 1
    logger.info("Ingestion finished (%s mode).", mode)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Ingestor stopped.")
