import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy import text
from src.infrastructure.db.session import AsyncSessionLocal

async def run_migration():
    print("Starting migration: raw_messages to BIGINT")
    async with AsyncSessionLocal() as session:
        try:
            # Execute ALTER TABLE statements
            await session.execute(text("ALTER TABLE raw_messages ALTER COLUMN chat_id TYPE BIGINT;"))
            await session.execute(text("ALTER TABLE raw_messages ALTER COLUMN msg_id TYPE BIGINT;"))
            await session.commit()
            print("Migration successful: chat_id and msg_id are now BIGINT.")
        except Exception as e:
            print(f"Migration failed: {e}")
            await session.rollback()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_migration())
