from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field

class IngestionSourceType(str, Enum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"

class IngestionEvent(BaseModel):
    """
    Standardized event for data ingestion, decoupled from specific sources (e.g. Telethon).
    """
    content: str
    source_type: IngestionSourceType
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Context specific to the source, e.g. chat_id, message_id for Telegram
    # We use a dict to be flexible but structured enough for the Ingestor to read
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    
    @property
    def telegram_metadata(self) -> dict:
        """Helper to safely access telegram-specific metadata if available."""
        return self.source_metadata
