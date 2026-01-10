import asyncio
import os
import logging
from src.infrastructure.telegram.client import TelegramService
from src.services.bot import BotService
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def main():
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    bot_token = os.getenv("BOT_TOKEN")
    
    # Session name for bot, can be different or handled internally by Telethon with bot_token
    # But Telethon needs api_id/hash even for bot
    
    if not api_id or not api_hash or not bot_token:
        print("Error: TELEGRAM_API_ID, TELEGRAM_API_HASH or BOT_TOKEN not set.")
        return

    # For bot, we initialize the client slightly differently if we want to start as bot immediately
    # But TelegramService wrapper abstracts this. We need to Ensure 'start' method handles bot token login if provided.
    
    # Let's adjust TelegramService usage or relying on .start(bot_token=...)
    # Since our Wrapper is generic, we might need to tweak it or just pass token to client.start()
    
    # We will instantiate the service, but connection happens in start()
    telegram_service = TelegramService("cazachollos_bot", int(api_id), api_hash)
    
    # We need to tell the client to start with a bot token
    await telegram_service.client.start(bot_token=bot_token)
    
    bot_service = BotService(telegram_service)
    
    # We override the bot_service.start because we already called telegram_service.client.start above
    # Actually, BotService.start calls telegram.start() which calls client.connect() -> client.start() (interactive)
    # Refactoring slightly: BotService.start logic expects to define handlers then run until disconnected.
    
    # Let's rely on BotService.start() calling telegram.run_until_disconnected()
    # But handlers must be added before running.
    
    # Redefine BotService logic in main slightly is messy.
    # Better: Update BotService to accept the already started client or handle the start logic better.
    # Current BotService.start calls telegram.start() then run_until_disconnected().
    
    # Let's just fix BotService.start to NOT call telegram.start() if we already did, OR
    # Pass token to telegram.start().
    
    # HACK: Modifying the client wrapper call in BotService is hard without changing code.
    # Let's just use the BotService as designed but we need to pass the bot token to the wrapper's start method?
    # The wrapper's start method currently: await self.client.connect() ...
    
    # The correct way with Telethon for bots is client.start(bot_token=token)
    # The wrapper start() does basic connect.
    
    # Let's manually set up here for clarity:
    
    # Define handlers (logic in BotService)
    # But BotService.start() registers them.
    
    # We will use a small adjustment:
    # We will subclass or just let BotService register handlers, then we run.
    
    # To avoid changing BotService too much, let's just do:
    # 1. Register handlers
    # 2. Start client with token
    # 3. Run
    
    # Accessing internal logic of BotService
    # @self.telegram.client.on(...) requires client instance.
    
    # Let's Re-Write run_bot.py to be clean
    
    # We need to register handlers BEFORE starting the loop? 
    # Yes.
    
    bot_service = BotService(telegram_service)
    
    # Manually register handlers by calling a setup method? 
    # BotService.start() does definition AND running. 
    # We need to inject the bot token into the start process.
    
    # Since we can't easily change the Wrapper signature now (it's in use by Ingestor), 
    # we will rely on `telegram_service.client.start(bot_token=...)` being idempotent-ish or 
    # just modify BotService to take an optional token.
    
    # Let's modify BotService.start to accept the token, or better, 
    # Modify TelegramService.start to accept optional strings? 
    # Start is async def start(self).
    
    # EASIEST FIX:
    # Just run client.start(bot_token=...) here.
    # Then call bot_service.start(). 
    # Inside bot_service.start(), telegram.start() is called.
    # client.connect() is fine to call multiple times.
    # But client.start() (interactive) might be an issue.
    
    # Telethon client.start() with bot token is what logs us in.
    await telegram_service.client.start(bot_token=bot_token)
    
    # Now that we are logged in, we call bot_service.start()
    # It will define handlers and run_until_disconnected.
    await bot_service.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
