"""JSON API for danielalonso.dev/cazachollos: deals, the account and its Telegram alerts.

Every route needs a Google ID token (Bearer). The browser calls it from danielalonso.dev, so CORS allows only that
origin (and localhost for development).
"""

from __future__ import annotations

import os
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.domain.enums import CATEGORY_LABELS
from src.services.alerts import MAX_ALERTS_PER_CHAT, parse_alert
from src.web.deals_query import find_deals
from src.web.google_auth import GoogleUser
from src.web.site import ICONS, parse_filters

CORS_ORIGINS = ["https://danielalonso.dev", "https://www.danielalonso.dev", "http://localhost:3000"]


class AlertIn(BaseModel):
    texto: str = Field(..., max_length=240)


class AlertDelete(BaseModel):
    id: int


def money(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def api_router(current_user, accounts, alerts, finder=find_deals, bot_username: str | None = None) -> APIRouter:
    router = APIRouter(prefix="/api")
    bot_username = bot_username if bot_username is not None else os.getenv("TELEGRAM_BOT_USERNAME", "")

    async def account(user: GoogleUser = Depends(current_user)) -> dict:
        return await accounts.upsert(user.id, user.email, user.name)

    def chat_of(acc: dict) -> int:
        if not acc.get("telegram_chat_id"):
            raise HTTPException(409, "Conecta primero tu Telegram para recibir las alertas.")
        return int(acc["telegram_chat_id"])

    @router.get("/ofertas")
    async def deals(request: Request, user: GoogleUser = Depends(current_user)) -> dict:
        page = await finder(parse_filters(dict(request.query_params)))
        f = page.filters
        return {
            "total": page.total,
            "pagina": f.page,
            "hay_mas": page.has_more,
            "orden": f.sort,
            "categorias": [
                {"id": c, "nombre": CATEGORY_LABELS.get(c, c), "icono": ICONS.get(c, "🏷️"), "n": n}
                for c, n in page.categories
            ],
            "tiendas": page.shops,
            "canales": page.channels,
            "ofertas": [
                {
                    "id": d.id,
                    "titulo": d.title,
                    "url": d.url or d.post_url,
                    "precio": money(d.price),
                    "antes": money(d.before) if d.before and d.price is not None and d.before > d.price else None,
                    "descuento": d.discount,
                    "tienda": d.shop,
                    "canal": d.channel,
                    "categoria": d.category,
                    "categoria_nombre": CATEGORY_LABELS.get(d.category, d.category),
                    "icono": ICONS.get(d.category, "🏷️"),
                    "puntuacion": d.score,
                    "imagen": d.image_url,
                    "mensaje": d.post_url,
                    "fecha": d.created_at.isoformat() + "Z",
                }
                for d in page.deals
            ],
        }

    @router.get("/yo")
    async def me(acc: dict = Depends(account)) -> dict:
        return {
            "email": acc["email"],
            "nombre": acc["name"],
            "telegram": bool(acc["telegram_chat_id"]),
            "bot": bot_username,
        }

    @router.post("/telegram/vincular")
    async def link(acc: dict = Depends(account)) -> dict:
        if not bot_username:
            raise HTTPException(503, "El bot no está configurado.")
        code = await accounts.new_link_code(acc["id"])
        return {"url": f"https://t.me/{bot_username}?start={code}", "caduca_en_minutos": 15}

    @router.post("/telegram/desvincular")
    async def unlink(acc: dict = Depends(account)) -> dict:
        await accounts.unlink(acc["id"])
        return {"telegram": False}

    @router.get("/alertas")
    async def list_alerts(acc: dict = Depends(account)) -> dict:
        if not acc.get("telegram_chat_id"):
            return {"telegram": False, "alertas": [], "maximo": MAX_ALERTS_PER_CHAT}
        rows = await alerts.list(int(acc["telegram_chat_id"]))
        return {
            "telegram": True,
            "maximo": MAX_ALERTS_PER_CHAT,
            "alertas": [{"id": a["id"], "texto": a["query"], "precio_max": money(a["max_price"])} for a in rows],
        }

    @router.post("/alertas")
    async def add_alert(body: AlertIn, acc: dict = Depends(account)) -> dict:
        chat = chat_of(acc)
        parsed = parse_alert(body.texto)
        if not parsed:
            raise HTTPException(422, "Escribe qué quieres que vigile, por ejemplo: freidora de aire hasta 60")
        query, price = parsed
        new_id = await alerts.add(chat, query, price)
        if new_id is None:
            raise HTTPException(409, f"Ya tienes {MAX_ALERTS_PER_CHAT} alertas. Borra alguna.")
        return {"id": new_id, "texto": query, "precio_max": money(price)}

    @router.post("/alertas/borrar")
    async def delete_alert(body: AlertDelete, acc: dict = Depends(account)) -> dict:
        if not await alerts.delete(chat_of(acc), body.id):
            raise HTTPException(404, "No tienes esa alerta.")
        return {"borrada": body.id}

    return router
