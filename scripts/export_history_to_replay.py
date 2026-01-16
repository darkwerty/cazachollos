import asyncio
import json
import sys
import os
from sqlalchemy.future import select

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.infrastructure.db.session import AsyncSessionLocal
from src.domain.models import RawMessage

async def export_history(output_file: str = "replay_data.jsonl", limit: int = 100):
    """
    Exports the last N RawMessages from the database to a JSONL file
    compatible with the ReplayFileStrategy.
    """
    print(f"Exporting last {limit} messages to {output_file}...")
    
    async with AsyncSessionLocal() as session:
        # Fetch last N messages ordered by time
        query = select(RawMessage).order_by(RawMessage.created_at.desc()).limit(limit)
        result = await session.execute(query)
        messages = result.scalars().all()
        
        # Reverse to have them in chronological order for replay
        messages = list(reversed(messages))
        
        count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            for msg in messages:
                event_data = {
                    "content": msg.raw_content,
                    "occurred_at": msg.created_at.isoformat(),
                    "source_metadata": {
                        "chat_id": msg.chat_id,
                        "msg_id": msg.msg_id
                    }
                }
                f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
                count += 1
                
        print(f"Successfully exported {count} events.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export DB history to Replay JSONL")
    parser.add_argument("--output", default="replay_data.jsonl", help="Output file path")
    parser.add_argument("--limit", type=int, default=100, help="Number of messages to export")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(export_history(args.output, args.limit))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error exporting data: {e}")
