"""Minimal Telegram Bot API client (HTTPS): only what the bot and the alerts need. No account login involved."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# httpx logs every request URL at INFO, and Bot API URLs carry the token: never below WARNING
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)


class BotAPI:
    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._base = f"https://api.telegram.org/bot{token}/"
        self._client = client

    async def call(self, method: str, **params) -> dict | list | bool | None:
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            resp = await client.post(self._base + method, json=params)
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Telegram %s failed: %s", method, type(e).__name__)  # never log the URL: it has the token
            return None
        finally:
            if self._client is None:
                await client.aclose()
        if not data.get("ok"):
            logger.warning("Telegram %s: %s", method, data.get("description"))
            return None
        return data.get("result")

    async def send(self, chat_id: int, html_text: str) -> bool:
        result = await self.call(
            "sendMessage",
            chat_id=chat_id,
            text=html_text[:4096],
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
        )
        return result is not None
