"""Telegram bot as a webhook: Telegram calls POST /telegram/webhook and the app answers right away.

Runs in a Container App that scales to zero: it wakes up when a message arrives. Anyone can use it in a private
chat (each person has their own alerts); TELEGRAM_ALLOWED_USERS limits it to some ids if set. Telegram must send
the secret header set with setWebhook (TELEGRAM_WEBHOOK_SECRET), so nobody else can post fake updates.

    uvicorn src.web.bot_webhook:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import hmac
import html
import logging
import os
import time
from collections import defaultdict, deque

from fastapi import APIRouter, FastAPI, Header, Request, Response

from src.infrastructure.telegram.bot_api import BotAPI
from src.services.alerts import MAX_ALERTS_PER_CHAT, AlertStore, deal_html, parse_alert

logger = logging.getLogger(__name__)

HELP = (
    "🛍️ <b>CazaChollos</b>\n\n"
    "Escríbeme lo que buscas, por ejemplo <code>auriculares sony</code>, y te enseño las mejores ofertas.\n\n"
    "<b>Alertas</b>: te aviso en cuanto salga una oferta que encaje.\n"
    "<code>/alerta auriculares sony hasta 250</code>: crea una (el precio es opcional)\n"
    "<code>/alertas</code>: las que tienes\n"
    "<code>/borrar 3</code>: borra la número 3\n\n"
    'Se busca como en Google: <code>"freidora de aire"</code> para una frase, <code>-reacondicionado</code> para '
    "quitar resultados."
)


def allowed_users(value: str) -> set[int]:
    out = set()
    for part in value.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


SEARCHES_PER_HOUR = 30


class BotCommands:
    def __init__(self, store, search, allowed: set[int], clock=time.monotonic) -> None:
        self.store = store
        self.search = search
        self.allowed = allowed  # empty: everyone
        self.clock = clock
        self._searches: dict[int, deque] = defaultdict(deque)

    def _search_allowed(self, user_id: int) -> bool:
        """At most SEARCHES_PER_HOUR searches per person (in memory: enough for a bot among friends)."""
        now = self.clock()
        recent = self._searches[user_id]
        while recent and now - recent[0] > 3600:
            recent.popleft()
        if len(recent) >= SEARCHES_PER_HOUR:
            return False
        recent.append(now)
        return True

    async def reply(self, message: dict) -> str | None:
        """Answer (HTML) for one incoming message, or None to stay silent."""
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        if chat.get("type") != "private" or (self.allowed and user.get("id") not in self.allowed):
            return None
        text = (message.get("text") or "").strip()
        if not text:
            return None
        chat_id = chat["id"]
        command, _, arg = text.partition(" ")
        command = command.split("@")[0].lower()

        if command in ("/start", "/ayuda", "/help"):
            return HELP
        if command == "/alerta":
            parsed = parse_alert(arg)
            if not parsed:
                return "Dime qué quieres que vigile, por ejemplo <code>/alerta freidora de aire hasta 60</code>."
            query, price = parsed
            new_id = await self.store.add(chat_id, query, price)
            if new_id is None:
                return f"Ya tienes {MAX_ALERTS_PER_CHAT} alertas. Borra alguna con <code>/borrar</code>."
            limit = f" por {price} € o menos" if price is not None else ""
            return f"✅ Alerta {new_id}: te aviso cuando salga <i>{html.escape(query)}</i>{limit}."
        if command == "/alertas":
            alerts = await self.store.list(chat_id)
            if not alerts:
                return "No tienes alertas. Crea una con <code>/alerta auriculares sony hasta 250</code>."
            lines = [
                f"{a['id']}. {html.escape(a['query'])}" + (f" (hasta {a['max_price']} €)" if a["max_price"] else "")
                for a in alerts
            ]
            return "🔔 Tus alertas:\n" + "\n".join(lines) + "\n\nPara borrar una: <code>/borrar número</code>"
        if command == "/borrar":
            if not arg.strip().isdigit():
                return "Dime el número de la alerta, por ejemplo <code>/borrar 3</code>. Las ves con /alertas."
            ok = await self.store.delete(chat_id, int(arg.strip()))
            return "🗑️ Alerta borrada." if ok else "No tienes ninguna alerta con ese número."

        query = arg if command == "/buscar" else text
        if command.startswith("/") and command != "/buscar":
            return "No conozco ese comando. Escribe /ayuda."
        query = " ".join(query.split())[:100]
        if not query:
            return "Dime qué buscas."
        if not self._search_allowed(user["id"]):
            return "Has hecho muchas búsquedas en la última hora. Prueba un poco más tarde."
        deals = await self.search.search_deals(query)
        if not deals:
            return f"No he encontrado ofertas para <i>{html.escape(query)}</i>. Puedes crear una alerta con /alerta."
        body = "\n\n".join(
            deal_html(d.title, d.url, d.price_sale, d.price_before or d.price_retail, d.shop, d.chollo_score)
            for d in deals
        )
        return f"🔍 <i>{html.escape(query)}</i>\n\n{body}"


def telegram_router(bot=None, commands: BotCommands | None = None, secret: str | None = None) -> APIRouter:
    """POST /telegram/webhook. Without BOT_TOKEN (and no bot given) the router is empty."""
    router = APIRouter()
    secret = secret if secret is not None else os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if bot is None and not os.getenv("BOT_TOKEN"):
        return router
    if bot is None:
        bot = BotAPI(os.environ["BOT_TOKEN"])
    if commands is None:
        from src.services.search import SearchService

        commands = BotCommands(AlertStore(), SearchService(), allowed_users(os.getenv("TELEGRAM_ALLOWED_USERS", "")))

    @router.post("/telegram/webhook")
    async def webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")) -> Response:
        if not secret or not hmac.compare_digest(x_telegram_bot_api_secret_token, secret):
            return Response(status_code=403)
        try:
            update = await request.json()
        except ValueError:
            return Response(status_code=200)
        message = update.get("message") if isinstance(update, dict) else None
        if message:
            try:
                answer = await commands.reply(message)
            except Exception:
                logger.exception("Bot command failed")
                answer = "Ups, algo ha fallado. Prueba otra vez en un momento."
            if answer:
                await bot.send(message["chat"]["id"], answer)
        return Response(status_code=200)  # always 200: otherwise Telegram keeps resending the same update

    return router


def create_app(bot=None, commands: BotCommands | None = None, secret: str | None = None) -> FastAPI:
    """Only the bot (the full site is src.web.site, which includes this router)."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(telegram_router(bot, commands, secret))

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    return app


def __getattr__(name: str):
    # `uvicorn src.web.bot_webhook:app`: the real app is only built when it is asked for (tests import the module)
    if name == "app":
        logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
        return create_app()
    raise AttributeError(name)
