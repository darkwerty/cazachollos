import asyncio
import time
from decimal import Decimal

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from src.web.api import api_router
from src.web.bot_webhook import BotCommands
from src.web.google_auth import GoogleUser, user_dependency, validate_claims
from src.web.site import create_app
from tests.test_bot import FakeSearch, FakeStore, msg
from tests.test_site import card, fake_finder

CLIENT = "client-id.apps.googleusercontent.com"


def fake_user(request: Request) -> GoogleUser:
    if request.headers.get("authorization") != "Bearer ok":
        raise HTTPException(401, "Inicia sesión con Google")
    return GoogleUser(id="u1", email="ana@example.com", name="Ana")


class FakeAccounts:
    def __init__(self):
        self.users, self.codes = {}, {}

    async def upsert(self, user_id, email, name):
        u = self.users.setdefault(user_id, {"id": user_id, "telegram_chat_id": None})
        u.update(email=email, name=name)
        return dict(u)

    async def new_link_code(self, user_id):
        code = f"code{len(self.codes)}"
        self.codes[code] = user_id
        return code

    async def link(self, code, chat_id):
        user_id = self.codes.pop(code, None)
        if user_id is None:
            return None
        self.users[user_id]["telegram_chat_id"] = chat_id
        return self.users[user_id]["email"]

    async def unlink(self, user_id):
        self.users[user_id]["telegram_chat_id"] = None


def client():
    accounts, alerts = FakeAccounts(), FakeStore()
    api = api_router(fake_user, accounts, alerts, finder=fake_finder([card()]), bot_username="qwertychollos_bot")
    app = create_app(finder=fake_finder([card()]), allowed_emails="", with_bot=False, api=api)
    return TestClient(app), accounts, alerts


H = {"Authorization": "Bearer ok"}


def test_everything_needs_login():
    api, _, _ = client()
    for path in ("/api/ofertas", "/api/yo", "/api/alertas"):
        assert api.get(path).status_code == 401
    assert api.post("/api/telegram/vincular").status_code == 401


def test_deals_json():
    api, _, _ = client()
    data = api.get("/api/ofertas?cat=tecnologia", headers=H).json()
    d = data["ofertas"][0]
    assert d["titulo"].startswith("Auriculares") and d["precio"] == 249.0 and d["antes"] == 419.0
    assert d["descuento"] == 40 and d["imagen"].startswith("https://") and d["categoria_nombre"] == "Tecnología"
    assert data["categorias"][0]["nombre"] == "Tecnología"


def test_link_telegram_and_alerts():
    api, accounts, alerts = client()
    assert api.get("/api/yo", headers=H).json()["telegram"] is False
    assert api.post("/api/alertas", json={"texto": "sony"}, headers=H).status_code == 409  # Telegram first
    url = api.post("/api/telegram/vincular", headers=H).json()["url"]
    assert url == "https://t.me/qwertychollos_bot?start=code0"

    bot = BotCommands(alerts, FakeSearch(), set(), accounts=accounts)
    answer = asyncio.run(bot.reply(msg("/start code0", user=555)))
    assert "ana@example.com" in answer
    assert "caducado" in asyncio.run(bot.reply(msg("/start code0", user=555)))  # one use only

    assert api.get("/api/yo", headers=H).json()["telegram"] is True
    new = api.post("/api/alertas", json={"texto": "auriculares sony hasta 250"}, headers=H).json()
    assert new["texto"] == "auriculares sony" and new["precio_max"] == 250.0
    listed = api.get("/api/alertas", headers=H).json()["alertas"]
    assert listed == [{"id": new["id"], "texto": "auriculares sony", "precio_max": 250.0}]
    assert alerts.alerts[0]["chat_id"] == 555  # the alert goes to the linked chat
    assert api.post("/api/alertas/borrar", json={"id": new["id"]}, headers=H).status_code == 200
    assert api.post("/api/alertas/borrar", json={"id": new["id"]}, headers=H).status_code == 404
    api.post("/api/telegram/desvincular", headers=H)
    assert api.get("/api/yo", headers=H).json()["telegram"] is False


def test_cors_only_for_the_portfolio():
    api, _, _ = client()
    pre = {
        "Origin": "https://danielalonso.dev",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }
    ok = api.options("/api/ofertas", headers=pre)
    assert ok.headers.get("access-control-allow-origin") == "https://danielalonso.dev"
    bad = api.options("/api/ofertas", headers={**pre, "Origin": "https://evil.example"})
    assert bad.headers.get("access-control-allow-origin") is None


def test_google_claims():
    good = {
        "aud": CLIENT,
        "iss": "https://accounts.google.com",
        "exp": time.time() + 60,
        "email_verified": True,
        "sub": "123",
        "email": "Ana@Example.com",
        "given_name": "Ana",
    }
    u = validate_claims(good, CLIENT)
    assert u.email == "ana@example.com" and u.id != "123" and len(u.id) == 64
    for bad in ({"aud": "otro"}, {"email_verified": False}, {"exp": time.time() - 3600}, {"iss": "evil"}):
        try:
            validate_claims({**good, **bad}, CLIENT)
            raise AssertionError(bad)
        except ValueError:
            pass


def test_user_dependency_rejects_bad_tokens():
    def verifier(token):
        raise ValueError("firma")

    dep = user_dependency(verifier, CLIENT)
    scope = {"type": "http", "headers": [(b"authorization", b"Bearer x")]}
    try:
        dep(Request(scope))
        raise AssertionError("debería fallar")
    except HTTPException as e:
        assert e.status_code == 401


def test_alert_price_parsing_in_api():
    api, accounts, _ = client()
    accounts.users["u1"] = {"id": "u1", "telegram_chat_id": 1, "email": "ana@example.com", "name": "Ana"}
    assert api.post("/api/alertas", json={"texto": " "}, headers=H).status_code == 422
    r = api.post("/api/alertas", json={"texto": "freidora por menos de 59,90 €"}, headers=H).json()
    assert r["precio_max"] == float(Decimal("59.90"))
