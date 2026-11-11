"""The tests need neither PostgreSQL nor Telegram nor Gemini: dummy settings before importing src."""

import os

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
# Never call the real LLM from the tests, even with a key in the environment
os.environ["GEMINI_API_KEY"] = ""
# Never message Telegram from the tests
os.environ.pop("BOT_TOKEN", None)
