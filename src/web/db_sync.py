"""Sync queries for the Streamlit dashboard (Streamlit runs outside asyncio)."""

from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

COLUMNS = (
    "title, price_sale, price_before, discount_percentage, shop, source, chollo_score, category, url, " "created_at"
)


@lru_cache(maxsize=1)
def get_sync_engine() -> Engine:
    # One engine (and its connection pool) for the whole process, not one per query
    from src.infrastructure.db.config import settings

    return create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)


def get_total_deals() -> int:
    with get_sync_engine().connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM deals")).scalar() or 0


def get_deals_today() -> int:
    with get_sync_engine().connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM deals WHERE created_at >= current_date")).scalar() or 0


def get_recent_deals(limit: int = 50) -> pd.DataFrame:
    query = text(f"SELECT {COLUMNS} FROM deals ORDER BY created_at DESC LIMIT :limit")
    return pd.read_sql(query, get_sync_engine(), params={"limit": int(limit)})


def search_deals(q: str, limit: int = 50) -> pd.DataFrame:
    """Same full-text search as the bot: Spanish stemming, websearch syntax ("frase", -palabra, or)."""
    query = text(
        f"SELECT {COLUMNS}, ts_rank(search_vector, websearch_to_tsquery('spanish', :q)) AS relevancia "
        "FROM deals WHERE search_vector @@ websearch_to_tsquery('spanish', :q) "
        "ORDER BY relevancia DESC, chollo_score DESC LIMIT :limit"
    )
    return pd.read_sql(query, get_sync_engine(), params={"q": q, "limit": int(limit)})
