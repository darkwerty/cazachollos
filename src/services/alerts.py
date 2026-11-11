"""Alerts from the Telegram bot: "tell me when <words> shows up [for at most <price>]".

An alert is a full-text query (same Spanish search as the bot and the dashboard) and an optional maximum price.
When the ingestor saves a new deal, every alert whose query matches it gets one Telegram message.
"""

from __future__ import annotations

import html
import logging
import re
from decimal import Decimal, InvalidOperation

from sqlalchemy import text

from src.infrastructure.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

MAX_ALERTS_PER_CHAT = 20
# "auriculares sony hasta 250", "... por menos de 250 €", "... <250", "... máx. 99,90€"
PRICE_RE = re.compile(
    r"\s*(?:hasta|por\s+menos\s+de|menos\s+de|max(?:imo)?\.?|máx(?:imo)?\.?|<=?)\s*"
    r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|eur(?:os)?)?\s*$",
    re.IGNORECASE,
)


def parse_alert(arg: str) -> tuple[str, Decimal | None] | None:
    """'/alerta' argument -> (query, max price). None if there is nothing to look for."""
    arg = " ".join(arg.split())
    price = None
    m = PRICE_RE.search(arg)
    if m:
        try:
            price = Decimal(m.group(1).replace(",", "."))
        except InvalidOperation:
            price = None
        arg = arg[: m.start()].strip()
    arg = arg[:200]
    return (arg, price) if len(arg) >= 2 else None


def deal_html(title, url, price, before=None, shop=None, score=None) -> str:
    """One deal for a Telegram message (HTML parse mode: everything escaped)."""
    name = html.escape(title or "Oferta")
    head = f'<b><a href="{html.escape(url, quote=True)}">{name}</a></b>' if url else f"<b>{name}</b>"
    if price is None:
        line = "Precio no indicado"
    else:
        line = f"{price} €"
        if before and before > price:
            line += f" (antes {before} €, -{round((1 - price / before) * 100)} %)"
    if shop:
        line += f" | {html.escape(shop)}"
    if score is not None:
        line += f" | {score}/100"
    return f"{head}\n{line}"


class AlertStore:
    async def add(self, chat_id: int, query: str, max_price: Decimal | None) -> int | None:
        """New alert id, or None if the chat already has MAX_ALERTS_PER_CHAT."""
        async with AsyncSessionLocal() as session:
            count = (
                await session.execute(text("SELECT COUNT(*) FROM alerts WHERE chat_id = :c"), {"c": chat_id})
            ).scalar()
            if count >= MAX_ALERTS_PER_CHAT:
                return None
            new_id = (
                await session.execute(
                    text("INSERT INTO alerts (chat_id, query, max_price) VALUES (:c, :q, :p) RETURNING id"),
                    {"c": chat_id, "q": query, "p": max_price},
                )
            ).scalar()
            await session.commit()
            return new_id

    async def list(self, chat_id: int) -> list[dict]:
        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                text("SELECT id, query, max_price FROM alerts WHERE chat_id = :c ORDER BY id"), {"c": chat_id}
            )
            return [dict(r._mapping) for r in rows]

    async def delete(self, chat_id: int, alert_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("DELETE FROM alerts WHERE chat_id = :c AND id = :i"), {"c": chat_id, "i": alert_id}
            )
            await session.commit()
            return result.rowcount > 0

    async def matching(self, deal_id, price) -> list[dict]:
        """Alerts whose query matches this stored deal (its search_vector) and whose price limit it meets."""
        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                text(
                    "SELECT a.id, a.chat_id, a.query FROM alerts a JOIN deals d ON d.id = :deal "
                    "WHERE d.search_vector @@ websearch_to_tsquery('spanish', a.query) "
                    "AND (a.max_price IS NULL OR d.price_sale <= a.max_price)"
                ),
                {"deal": deal_id},
            )
            return [dict(r._mapping) for r in rows]


class AlertNotifier:
    """Called by the ingestor after saving a deal. Never raises: an alert failing cannot stop the ingestion."""

    def __init__(self, bot, store: AlertStore | None = None) -> None:
        self.bot = bot
        self.store = store or AlertStore()

    async def deal_saved(self, deal) -> int:
        try:
            alerts = await self.store.matching(deal.id, deal.price_sale)
        except Exception:
            logger.exception("Could not check the alerts")
            return 0
        sent = 0
        for chat_id in sorted({a["chat_id"] for a in alerts}):
            queries = ", ".join(sorted({a["query"] for a in alerts if a["chat_id"] == chat_id}))
            body = deal_html(deal.title, deal.url, deal.price_sale, deal.price_before, deal.shop, deal.chollo_score)
            if await self.bot.send(chat_id, f"🔔 Alerta: <i>{html.escape(queries)}</i>\n\n{body}"):
                sent += 1
        return sent
