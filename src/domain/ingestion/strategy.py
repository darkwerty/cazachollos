from abc import ABC, abstractmethod
from typing import AsyncIterator
from src.domain.ingestion.models import IngestionEvent

class IngestionStrategy(ABC):
    """
    Abstract Base Class for Data Ingestion Strategies.
    Allows switching between Live (Real-time) and Replay (Historical/Simulated) modes.
    """
    
    @abstractmethod
    async def stream(self) -> AsyncIterator[IngestionEvent]:
        """
        Yields IngestionEvents as they arrive or are replayed.
        """
        pass

    @abstractmethod
    async def stop(self):
        """
        Clean up resources, close connections, etc.
        """
        pass
