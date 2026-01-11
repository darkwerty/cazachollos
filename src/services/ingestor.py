import logging
import hashlib
import os
from datetime import datetime

from sqlalchemy.future import select

from src.infrastructure.telegram.client import TelegramService
from src.domain.models import Deal, RawMessage
from src.domain.schemas import DealCreate
from src.infrastructure.db.session import AsyncSessionLocal
from src.services.parser import DealParser
from src.domain.ingestion.strategy import IngestionStrategy

logger = logging.getLogger(__name__)

class IngestorService:
    def __init__(self, strategy: IngestionStrategy):
        self.strategy = strategy
        self.parser = DealParser()
        self.allowed_groups = self._load_allowed_groups()

    def _load_allowed_groups(self) -> set:
        """Loads allowed groups from env var. Returns a set of strings (titles) and ints (ids)."""
        env_val = os.getenv("TELEGRAM_ALLOWED_GROUPS", "")
        if not env_val:
            return set()
        
        allowed = set()
        for item in env_val.split(","):
            item = item.strip()
            if not item:
                continue
            # Try to convert to int for IDs
            try:
                allowed.add(int(item))
            except ValueError:
                # Keep as string for Titles/Usernames
                allowed.add(item)
        return allowed

    def _is_allowed_source(self, chat_id: int, title: str) -> bool:
        """Checks if the source is allowed based on config."""
        if not self.allowed_groups:
            return True # Allow all if config is empty
        
        # Check title
        if title in self.allowed_groups:
            return True

        # Check exact ID
        if chat_id in self.allowed_groups:
            return True

        # Check with -100 prefix (common Telegram channel format)
        try:
            if int(f"-100{chat_id}") in self.allowed_groups:
                return True
        except ValueError:
            pass

        # Check negated ID (useful if ID is positive but config has negative)
        try:
             if -chat_id in self.allowed_groups:
                 return True
        except Exception:
            pass
            
        # Check without -100 prefix (if incoming has it but config doesn't)
        s_id = str(chat_id)
        if s_id.startswith("-100"):
            try:
                if int(s_id[4:]) in self.allowed_groups:
                    return True
            except ValueError:
                pass
                
        return False

    def _generate_content_hash(self, url: str, price: float, title_part: str) -> str:
        """Generates a MD5 hash for deduplication."""
        # Mix key elements to avoid processing the exact same deal
        # If url is missing, use full text hash (less reliable but fallback)
        content_key = f"{url}-{price}-{title_part}" if url else f"{title_part}"
        return hashlib.md5(content_key.encode('utf-8')).hexdigest()

    async def _save_raw_message(self, chat_id: int, msg_id: int, content: str):
        async with AsyncSessionLocal() as session:
            try:
                raw = RawMessage(chat_id=chat_id, msg_id=msg_id, raw_content=content)
                session.add(raw)
                await session.commit()
            except Exception as e:
                logger.error(f"Failed to save raw message: {e}")
                await session.rollback()

    async def _process_event(self, event):
        # Extract metadata from generic event
        meta = event.source_metadata
        chat_id = meta.get('chat_id', 0)
        title = meta.get('chat_title', str(chat_id))
        msg_id = meta.get('msg_id', 0)
        text = event.content

        if not self._is_allowed_source(chat_id, title):
             logger.info(f"Skipping message from {title} ({chat_id}) - Not in allowed list.")
             return

        if not text:
            return

        logger.info(f"Received message from {title} ({chat_id}): {text[:50]}...")
        
        # 1. Audit Log
        if msg_id: # Only save if we have a message ID (Replay might not or dummy)
            await self._save_raw_message(chat_id, msg_id, text)

        # 2. Parse
        parsed_data = self.parser.parse(text)
        
        if not parsed_data['url'] and parsed_data['price_sale'] == 0:
            logger.info("Message ignored: No URL and No Price found.")
            return

        # 3. Deduplication
        content_hash = self._generate_content_hash(
            parsed_data['url'], 
            parsed_data['price_sale'], 
            parsed_data['title'][:20]
        )

        async with AsyncSessionLocal() as session:
            # Check if exists
            result = await session.execute(select(Deal).filter_by(content_hash=content_hash))
            existing_deal = result.scalar_one_or_none()

            if existing_deal:
                logger.info(f"Duplicate deal ignored (Hash: {content_hash})")
                return

            # 4. Save Deal
            new_deal = Deal(
                content_hash=content_hash,
                title=parsed_data['title'],
                description=parsed_data['description'],
                price_sale=parsed_data['price_sale'],
                url=parsed_data['url'] or "",
                category=parsed_data['category'],
                chollo_score=parsed_data.get('chollo_score', 50),
                shop=parsed_data.get('shop'),
                price_before=parsed_data.get('price_before'),
                source=parsed_data.get('source') or title,
                raw_text=text,
            )
            session.add(new_deal)
            await session.commit()
            logger.info(f"Deal Saved: {new_deal.title}")

    async def start(self):
        print("Ingestor Service Started...")
        async for event in self.strategy.stream():
            try:
                await self._process_event(event)
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)

