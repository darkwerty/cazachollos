import os
from typing import Optional

from src.domain.ingestion.strategy import IngestionStrategy
from src.domain.ingestion.models import IngestionSourceType
from src.infrastructure.ingestion.live_telegram import LiveTelegramStrategy
from src.infrastructure.ingestion.replay_file import ReplayFileStrategy
from src.infrastructure.telegram.client import TelegramService

class IngestionFactory:
    """
    Factory to create the appropriate IngestionStrategy based on configuration.
    """
    
    @staticmethod
    def get_strategy(telegram_service: Optional[TelegramService] = None) -> IngestionStrategy:
        mode = os.getenv("INGESTION_MODE", "LIVE").upper()
        
        if mode == IngestionSourceType.REPLAY.value:
            file_path = os.getenv("REPLAY_SOURCE_FILE", "replay_data.jsonl")
            speed_factor = float(os.getenv("REPLAY_SPEED_FACTOR", "1.0"))
            return ReplayFileStrategy(file_path, speed_factor)
            
        elif mode == IngestionSourceType.LIVE.value:
            if not telegram_service:
                raise ValueError("TelegramService is required for LIVE ingestion mode.")
            return LiveTelegramStrategy(telegram_service)
            
        else:
            raise ValueError(f"Unknown INGESTION_MODE: {mode}")
