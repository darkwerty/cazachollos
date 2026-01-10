from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from src.domain.enums import CategoryEnum

# --- Deal Schemas ---

class DealBase(BaseModel):
    title: str
    description: str
    price_sale: Decimal
    price_retail: Optional[Decimal] = None
    currency: str = "EUR"
    category: CategoryEnum = CategoryEnum.OTROS
    url: str # kept as str for simplicity, could be HttpUrl
    chollo_score: int = Field(default=0, ge=0, le=100)
    shop: Optional[str] = None
    price_before: Optional[Decimal] = None
    source: Optional[str] = None
    raw_text: Optional[str] = None

class DealCreate(DealBase):
    content_hash: str

class DealRead(DealBase):
    id: UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# --- RawMessage Schemas ---

class RawMessageCreate(BaseModel):
    chat_id: int
    msg_id: int
    raw_content: str
