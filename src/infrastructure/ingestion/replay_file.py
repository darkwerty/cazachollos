import asyncio
import json
import os
import logging
from datetime import datetime
from typing import AsyncIterator

from src.domain.ingestion.strategy import IngestionStrategy
from src.domain.ingestion.models import IngestionEvent, IngestionSourceType

logger = logging.getLogger(__name__)

class ReplayFileStrategy(IngestionStrategy):
    """
    Ingestion Strategy that replays events from a JSONL file.
    Simulates latency based on the timestamp difference between events.
    """
    def __init__(self, file_path: str, speed_factor: float = 1.0):
        self.file_path = file_path
        self.speed_factor = speed_factor
        self._running = True

    async def stream(self) -> AsyncIterator[IngestionEvent]:
        logging.info(f"Starting Replay Mode from: {self.file_path} (Speed: {self.speed_factor}x)")
        
        if not os.path.exists(self.file_path):
            logger.error(f"Replay file not found: {self.file_path}")
            return

        last_event_time = None

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not self._running:
                        break
                    
                    try:
                        data = json.loads(line)
                        event = IngestionEvent(
                            content=data['content'],
                            source_type=IngestionSourceType.REPLAY,
                            occurred_at=datetime.fromisoformat(data['occurred_at']),
                            source_metadata=data.get('source_metadata', {})
                        )
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Skipping invalid replay line: {e}")
                        continue

                    # Latency Simulation
                    if last_event_time:
                        time_diff = (event.occurred_at - last_event_time).total_seconds()
                        if time_diff > 0:
                            sleep_time = time_diff / self.speed_factor
                            # Cap max sleep to avoid extremely long pauses during testing unless intended
                            # For now we allow it as requested for "realistic stress test"
                            logger.debug(f"Replay sleeping for {sleep_time:.2f}s")
                            await asyncio.sleep(sleep_time)
                    
                    last_event_time = event.occurred_at
                    yield event
                    
        except Exception as e:
            logger.error(f"Error during replay: {e}")
        
        logger.info("Replay finished.")

    async def stop(self):
        self._running = False
