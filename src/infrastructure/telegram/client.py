import logging
import os

from telethon import TelegramClient
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self, session_name: str, api_id: int, api_hash: str):
        # The session file is a login to the Telegram account: it lives in session/ (git and Docker ignore it)
        os.makedirs("session", exist_ok=True)
        self.session_path = os.path.join("session", session_name)
        self.client = TelegramClient(self.session_path, api_id, api_hash, connection=ConnectionTcpAbridged)

    async def start(self, bot_token: str | None = None):
        """Connects and logs in: as a bot with `bot_token`, or as a user with the saved session.

        The first user login is interactive (phone number and code): run the ingestor once with a terminal
        (see the README). After that the session file is reused.
        """
        logger.info("Connecting to Telegram with session %s...", self.session_path)
        if bot_token:
            await self.client.start(bot_token=bot_token)
        else:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                logger.warning("Client not authorized: starting the interactive login.")
                await self.client.start()
        logger.info("Telegram client connected.")

    async def stop(self):
        await self.client.disconnect()
        logger.info("Telegram client disconnected.")

    def add_event_handler(self, callback, event):
        self.client.add_event_handler(callback, event)

    async def run_until_disconnected(self):
        await self.client.run_until_disconnected()
