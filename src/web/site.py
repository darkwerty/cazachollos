"""CazaChollos web: the deals as a shop, with pictures, filters and sorting. Also receives the Telegram bot.

    uvicorn src.web.site:app --host 0.0.0.0 --port 8000

In Azure it sits behind the built-in login of Container Apps (Google), except /telegram/webhook and /health.
ALLOWED_EMAILS decides who may see it ("*": any signed-in Google account; empty: no check, for local use).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.domain.enums import CATEGORY_LABELS
from src.web.access import principal_email
from src.web.deals_query import SORT_LABELS, Filters, find_deals

logger = logging.getLogger(__name__)

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
ICONS = {
    "tecnologia": "📱",
    "videojuegos": "🎮",
    "hogar": "🏠",
    "cocina": "🍳",
    "bricolaje": "🛠️",
    "moda": "👕",
    "belleza": "💄",
    "deporte": "🏃",
    "juguetes": "🧸",
    "alimentacion": "🛒",
    "mascotas": "🐾",
    "libros": "📚",
    "oficina": "🖊️",
    "motor": "🚗",
    "otros": "🏷️",
}
# Query string names (Spanish, they show up in the address bar) -> Filters fields
PARAMS = {
    "q": "q",
    "cat": "category",
    "tienda": "shop",
    "canal": "channel",
    "dto": "min_discount",
    "max": "max_price",
    "orden": "sort",
    "page": "page",
}


def euros(value: Decimal | None) -> str:
    """12.5 -> '12,50 €', 1234 -> '1.234 €'."""
    if value is None:
        return ""
    value = Decimal(value)
    whole = value == value.to_integral_value()
    text = f"{value:,.0f}" if whole else f"{value:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def ago(when: datetime | None, now: datetime | None = None) -> str:
    if when is None:
        return ""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    s = max(0, int((now - when).total_seconds()))
    if s < 3600:
        return f"hace {max(1, s // 60)} min"
    if s < 86400:
        return f"hace {s // 3600} h"
    days = s // 86400
    return f"hace {days} {'día' if days == 1 else 'días'}"


def parse_filters(query: dict[str, str]) -> Filters:
    def as_int(v: str | None, default: int) -> int:
        try:
            return int(v) if v not in (None, "") else default
        except ValueError:
            return default

    try:
        max_price = Decimal(query["max"].replace(",", ".")) if query.get("max") else None
    except InvalidOperation:
        max_price = None
    return Filters(
        q=query.get("q", ""),
        category=query.get("cat", ""),
        shop=query.get("tienda", ""),
        channel=query.get("canal", ""),
        min_discount=as_int(query.get("dto"), 0),
        max_price=max_price,
        sort=query.get("orden", "relevancia" if query.get("q") else "recientes"),
        page=as_int(query.get("page"), 1),
    )


def can_see(headers, allowed: str) -> tuple[bool, str | None]:
    email = principal_email(headers)
    rule = allowed.strip()
    if not rule:
        return True, email  # local: no login in front
    if rule == "*":
        return email is not None, email
    return email in {e.strip().lower() for e in rule.split(",") if e.strip()}, email


def create_app(finder=find_deals, allowed_emails: str | None = None, with_bot: bool = True, api=None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    allowed = allowed_emails if allowed_emails is not None else os.getenv("ALLOWED_EMAILS", "")
    if with_bot:
        from src.web.bot_webhook import telegram_router

        app.include_router(telegram_router())
    # JSON API for danielalonso.dev/cazachollos (Google ID token). Only when GOOGLE_CLIENT_ID is set.
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if api is None and client_id:
        from src.services.accounts import AccountStore
        from src.services.alerts import AlertStore
        from src.web.api import api_router
        from src.web.google_auth import google_verifier, user_dependency

        api = api_router(user_dependency(google_verifier(client_id), client_id), AccountStore(), AlertStore())
    if api is not None:
        from fastapi.middleware.cors import CORSMiddleware

        from src.web.api import CORS_ORIGINS

        app.include_router(api)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=CORS_ORIGINS,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=3600,
        )

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        ok, email = can_see(request.headers, allowed)
        if not ok:
            return HTMLResponse(
                "<!doctype html><meta charset='utf-8'><title>CazaChollos</title>"
                "<p style='font:16px system-ui;margin:40px'>Esta cuenta no tiene acceso. "
                "<a href='/.auth/logout?post_logout_redirect_uri=/'>Entrar con otra cuenta</a></p>",
                status_code=403,
            )
        query = dict(request.query_params)
        filters = parse_filters(query)
        page = await finder(filters)
        f = page.filters
        current = {
            "q": f.q,
            "cat": f.category,
            "tienda": f.shop,
            "canal": f.channel,
            "dto": f.min_discount or "",
            "max": f.max_price if f.max_price is not None else "",
            "orden": f.sort if f.sort != ("relevancia" if f.q else "recientes") else "",
        }

        def link(**changes) -> str:
            values = {**current, **{("cat" if k == "category" else k): v for k, v in changes.items()}}
            if "page" not in changes:
                values.pop("page", None)
            return "/?" + urlencode({k: v for k, v in values.items() if v not in ("", None, 0)})

        context = {
            "page": page,
            "f": f,
            "email": email,
            "labels": CATEGORY_LABELS,
            "icons": ICONS,
            "sorts": SORT_LABELS,
            "link": link,
            "ago": ago,
            "euros": euros,
            "partial": bool(query.get("partial")),
            "filtered": any(current[k] for k in ("q", "cat", "tienda", "canal", "dto", "max")),
        }
        name = "_cards.html" if context["partial"] else "index.html"
        return TEMPLATES.TemplateResponse(request, name, context)

    return app


def __getattr__(name: str):
    if name == "app":  # uvicorn src.web.site:app
        logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
        for quiet in ("httpx", "httpcore"):  # their URLs can carry the bot token
            logging.getLogger(quiet).setLevel(logging.WARNING)
        return create_app()
    raise AttributeError(name)
