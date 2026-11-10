import asyncio
import hashlib
import logging
import os

from sqlalchemy.future import select

from src.domain.models import Deal, RawMessage
from src.infrastructure.db.session import AsyncSessionLocal
from src.services.parser import DealParser
from src.domain.ingestion.strategy import IngestionStrategy

logger = logging.getLogger(__name__)


class IngestorService:
    def __init__(self, strategy: IngestionStrategy, parser: DealParser | None = None, budget=None):
        self.strategy = strategy
        self.parser = parser or DealParser()
        self._budget = budget  # LLMBudget; created on first use so the tests need no database
        self.allowed_groups = self._load_allowed_groups()

    async def _llm_allowed(self) -> bool:
        if self._budget is None:
            from src.infrastructure.db.usage import LLMBudget

            self._budget = LLMBudget()
        return await self._budget.allow()

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
            return True  # Allow all if config is empty

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
        if -chat_id in self.allowed_groups:
            return True

        # Check without -100 prefix (if incoming has it but config doesn't)
        s_id = str(chat_id)
        if s_id.startswith("-100"):
            try:
                if int(s_id[4:]) in self.allowed_groups:
                    return True
            except ValueError:
                pass

        return False

    def _generate_content_hash(self, url: str | None, price, title_part: str) -> str:
        """MD5 of the clean URL, the price and the start of the title, for deduplication (not for security)."""
        # Mix key elements to avoid processing the exact same deal
        # If url is missing, use the title only (less reliable but fallback)
        content_key = f"{url}-{price}-{title_part}" if url else f"{title_part}"
        return hashlib.md5(content_key.encode("utf-8"), usedforsecurity=False).hexdigest()

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
        chat_id = meta.get("chat_id", 0)
        title = meta.get("chat_title", str(chat_id))
        msg_id = meta.get("msg_id", 0)
        text = event.content

        if not self._is_allowed_source(chat_id, title):
            logger.info(f"Skipping message from {title} ({chat_id}) - Not in allowed list.")
            return

        if not text:
            return

        logger.info(f"Received message from {title} ({chat_id}): {text[:50]}...")

        # 1. Audit Log
        if msg_id:  # Only save if we have a message ID (Replay might not or dummy)
            await self._save_raw_message(chat_id, msg_id, text)

        # 2. Parse with the rules only (free): enough to discard non-deals and duplicates before any LLM call
        rules = self.parser.parse(text, use_llm=False)

        if not rules["url"] and rules["price_sale"] is None:
            logger.info("Message ignored: No URL and No Price found.")
            return

        # 3. Deduplication (on the rules' fields, so the hash does not depend on what the LLM says)
        content_hash = self._generate_content_hash(rules["url"], rules["price_sale"], rules["title"][:20])

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Deal).filter_by(content_hash=content_hash))
            if result.scalar_one_or_none():
                logger.info(f"Duplicate deal ignored (Hash: {content_hash})")
                return

        # 4. LLM only when the rules left doubts and today's budget allows it. The call is blocking: in a thread.
        parsed_data = rules
        if self.parser.llm_enabled and self.parser.needs_llm(rules) and await self._llm_allowed():
            parsed_data = await asyncio.to_thread(self.parser.parse, text)

        async with AsyncSessionLocal() as session:
            # 5. Save Deal
            new_deal = Deal(
                content_hash=content_hash,
                title=parsed_data["title"][:255],
                description=parsed_data["description"],
                price_sale=parsed_data["price_sale"],
                url=parsed_data["url"] or "",
                category=parsed_data["category"],
                chollo_score=parsed_data.get("chollo_score", 50),
                shop=parsed_data.get("shop"),
                price_before=parsed_data.get("price_before"),
                discount_percentage=parsed_data.get("discount_percentage"),
                source=(parsed_data.get("source") or title)[:100],
                raw_text=text,
            )
            session.add(new_deal)
            await session.commit()
            logger.info(f"Deal Saved: {new_deal.title}")

    async def start(self):
        logger.info("Ingestor Service Started...")
        async for event in self.strategy.stream():
            try:
                await self._process_event(event)
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)
