import os
import asyncio
from telethon import TelegramClient
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged

class TelegramService:
    def __init__(self, session_name: str, api_id: int, api_hash: str):
        self.session_path = os.path.join("session", session_name)
        # Ensure session directory exists
        os.makedirs("session", exist_ok=True)
        
        self.client = TelegramClient(
            self.session_path,
            api_id,
            api_hash,
            connection=ConnectionTcpAbridged
        )

    async def start(self):
        """Connects to Telegram. Requires interactive auth if no session exists."""
        print(f"Connecting to Telegram with session: {self.session_path}...")
        await self.client.connect()
        
        # This part usually requires interaction primarily for the first login
        # In a headless container, we expect the session file to function
        if not await self.client.is_user_authorized():
             print("Warning: Client is not authorized. Interactive login might be required.")
             # Start interactive login if not authorized
             await self.client.start() 

        print("Telegram Client Connected.")

    async def stop(self):
        await self.client.disconnect()
        print("Telegram Client Disconnected.")

    def add_event_handler(self, callback, event):
        self.client.add_event_handler(callback, event)

    async def run_until_disconnected(self):
        await self.client.run_until_disconnected()
