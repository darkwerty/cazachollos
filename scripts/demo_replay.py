import sys
import os
import asyncio

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.infrastructure.ingestion.replay_file import ReplayFileStrategy

async def run_demo():
    print("--- starting replay demo ---")
    
    # Ensure our dummy file exists
    if not os.path.exists("replay_data.jsonl"):
        print("replay_data.jsonl not found!")
        return

    # Use a faster speed factor so we don't wait too long for the demo, 
    # but still enough to see the delay.
    # Timestamps in file are 0s, 2s, 5s.
    # Speed factor 1.0 => Wait 2s, then 3s.
    strategy = ReplayFileStrategy("replay_data.jsonl", speed_factor=1.0)
    
    start_time = asyncio.get_running_loop().time()
    
    async for event in strategy.stream():
        now = asyncio.get_running_loop().time()
        elapsed = now - start_time
        print(f"[{elapsed:.2f}s] Received Event: {event.content[:30]}... | Time: {event.occurred_at}")
        
    print("--- demo finished ---")

if __name__ == "__main__":
    asyncio.run(run_demo())
