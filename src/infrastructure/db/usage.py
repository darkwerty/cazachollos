"""Small DB helpers for the scheduled passes: where each channel was left and how many LLM calls were made today."""

import os
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from src.domain.models import RawMessage
from src.infrastructure.db.session import AsyncSessionLocal


async def last_msg_id(chat_id: int) -> int | None:
    """Highest message id stored for this chat (raw_messages keeps every message), or None if never seen."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.max(RawMessage.msg_id)).where(RawMessage.chat_id == chat_id))
        return result.scalar()


class LLMBudget:
    """Daily cap of LLM calls (LLM_MAX_CALLS_PER_DAY, 200 by default), counted in the DB across passes."""

    def __init__(self, max_calls: int | None = None) -> None:
        self.max_calls = max_calls if max_calls is not None else int(os.getenv("LLM_MAX_CALLS_PER_DAY", "200"))

    async def allow(self) -> bool:
        """Takes one call from today's budget. False when it is used up (the rules are used instead)."""
        if self.max_calls <= 0:
            return False
        today = datetime.now(timezone.utc).date()
        async with AsyncSessionLocal() as session:
            # Atomic: insert the day or add one, only while under the cap
            result = await session.execute(
                text(
                    "INSERT INTO llm_usage (day, calls) VALUES (:day, 1) "
                    "ON CONFLICT (day) DO UPDATE SET calls = llm_usage.calls + 1 "
                    "WHERE llm_usage.calls < :cap RETURNING calls"
                ),
                {"day": today, "cap": self.max_calls},
            )
            allowed = result.scalar() is not None
            await session.commit()
            return allowed
