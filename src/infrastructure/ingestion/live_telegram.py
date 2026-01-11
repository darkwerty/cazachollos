import asyncio
import logging
from typing import AsyncIterator
from telethon import events

from src.domain.ingestion.strategy import IngestionStrategy
from src.domain.ingestion.models import IngestionEvent, IngestionSourceType
from src.infrastructure.telegram.client import TelegramService

logger = logging.getLogger(__name__)

class LiveTelegramStrategy(IngestionStrategy):
    """
    Ingestion Strategy that listens to real-time Telegram events.
    Adapts Telethon events to standard IngestionEvents.
    """
    def __init__(self, telegram_service: TelegramService):
        self.telegram = telegram_service
        self.queue = asyncio.Queue()
        self._running = False

    async def _event_handler(self, event):
        """Callback for Telethon that pushes formatted events to the queue."""
        try:
            message = event.message
            if not message.text:
                return

            chat = await event.get_chat()
            sender_id = chat.id
            title = getattr(chat, 'title', '') or getattr(chat, 'username', '') or str(sender_id)

            ingestion_event = IngestionEvent(
                content=message.text,
                source_type=IngestionSourceType.LIVE,
                # In live mode occurred_at is now. Telethon msg date is also available.
                # using message.date might be better for precision.
                occurred_at=message.date.replace(tzinfo=None) if message.date else None, 
                source_metadata={
                    "chat_id": sender_id,
                    "chat_title": title,
                    "msg_id": message.id
                }
            )
            await self.queue.put(ingestion_event)
            
        except Exception as e:
            logger.error(f"Error processing Telegram event: {e}", exc_info=True)

    async def stream(self) -> AsyncIterator[IngestionEvent]:
        logger.info("Starting Live Telegram Ingestion...")
        self._running = True
        
        # Register handler
        # We need to access the inner client to register the event handler
        # Assuming TelegramService has add_event_handler or exposes client
        self.telegram.add_event_handler(self._event_handler, events.NewMessage())
        
        # Start the client (if not already started external to this strategy)
        await self.telegram.start()

        try:
            while self._running:
                # Wait for next event
                event = await self.queue.get()
                yield event
        except asyncio.CancelledError:
            logger.info("Live stream cancelled.")
        finally:
            await self.stop()

    async def stop(self):
        logger.info("Stopping Live Ingestion...")
        self._running = False
        await self.telegram.stop()
