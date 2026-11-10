import uuid
from datetime import date, datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import BigInteger, Computed, Date, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.session import Base
from src.domain.enums import CategoryEnum


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_hash: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    # None when the message has no price (0 is a real freebie)
    price_sale: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    price_retail: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    category: Mapped[CategoryEnum] = mapped_column(String, default=CategoryEnum.OTROS)
    shop: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    price_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    discount_percentage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    url: Mapped[str] = mapped_column(Text)
    chollo_score: Mapped[int] = mapped_column(Integer, default=0)

    # Full Text Search Vector
    # We use 'spanish' config for stemming
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('spanish', title || ' ' || coalesce(description, ''))", persisted=True)
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_deals_search_vector", "search_vector", postgresql_using="gin"),)


class LLMUsage(Base):
    """LLM calls per day (UTC), for the daily cap: each pass is a new process, so it lives in the DB."""

    __tablename__ = "llm_usage"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class RawMessage(Base):
    __tablename__ = "raw_messages"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    msg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
