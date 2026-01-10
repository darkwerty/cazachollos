import asyncio
import os
import logging
from src.infrastructure.telegram.client import TelegramService
from src.services.ingestor import IngestorService
from dotenv import load_dotenv

# Load env in case it's run locally without docker-compose for testing
load_dotenv()

logging.basicConfig(level=logging.INFO)

async def main():
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    session_name = os.getenv("TELEGRAM_SESSION_NAME", "cazachollos_ingestor")

    if not api_id or not api_hash:
        print("Error: TELEGRAM_API_ID or TELEGRAM_API_HASH not set.")
        return

    try:
        telegram_service = TelegramService(session_name, int(api_id), api_hash)
    except ValueError:
        print(f"Error: TELEGRAM_API_ID in .env must be an integer. Current value: '{api_id}'")
        return
    ingestor = IngestorService(telegram_service)
    
    await ingestor.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ingestor stopped.")
