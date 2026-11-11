import asyncio
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.services.alerts import AlertNotifier, deal_html, parse_alert
from src.web.bot_webhook import BotCommands, allowed_users, create_app

ME = 1267045133


class FakeStore:
    def __init__(self):
        self.alerts = []

    async def add(self, chat_id, query, price):
        self.alerts.append({"id": len(self.alerts) + 1, "chat_id": chat_id, "query": query, "max_price": price})
        return len(self.alerts)

    async def list(self, chat_id):
        return [a for a in self.alerts if a["chat_id"] == chat_id]

    async def delete(self, chat_id, alert_id):
        before = len(self.alerts)
        self.alerts = [a for a in self.alerts if not (a["chat_id"] == chat_id and a["id"] == alert_id)]
        return len(self.alerts) < before

    async def matching(self, deal_id, price):
        return [a for a in self.alerts if a["max_price"] is None or (price is not None and price <= a["max_price"])]


class FakeSearch:
    async def search_deals(self, q):
        if "sony" not in q:
            return []
        return [deal(title="Auriculares Sony <XM5>", price_sale=Decimal("249"), price_before=Decimal("419"))]


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send(self, chat_id, text):
        self.sent.append((chat_id, text))
        return True


def deal(**kw):
    base = dict(
        id="d1",
        title="Oferta",
        url="https://example.com/x",
        price_sale=Decimal("10"),
        price_before=None,
        price_retail=None,
        shop="Amazon",
        chollo_score=80,
    )
    return SimpleNamespace(**{**base, **kw})


def msg(text, user=ME, chat_type="private"):
    return {"chat": {"id": user, "type": chat_type}, "from": {"id": user}, "text": text}


def reply(commands, text, **kw):
    return asyncio.run(commands.reply(msg(text, **kw)))


def test_parse_alert_price():
    assert parse_alert("auriculares sony hasta 250") == ("auriculares sony", Decimal("250"))
    assert parse_alert("freidora de aire por menos de 59,90 €") == ("freidora de aire", Decimal("59.90"))
    assert parse_alert("ps5 <400") == ("ps5", Decimal("400"))
    assert parse_alert('"portátil gaming" -reacondicionado') == ('"portátil gaming" -reacondicionado', None)
    assert parse_alert("  ") is None


def test_deal_html_escapes():
    text = deal_html("A <b>&", "https://x.example/?a=1&b=2", Decimal("5"), Decimal("10"), "Tienda", 90)
    assert "A &lt;b&gt;&amp;" in text and 'href="https://x.example/?a=1&amp;b=2"' in text and "-50 %" in text


def test_only_allowed_private_chats():
    c = BotCommands(FakeStore(), FakeSearch(), {ME})
    assert reply(c, "/start").startswith("🛍️")
    assert reply(c, "/start", user=42) is None
    assert reply(c, "/start", chat_type="group") is None


def test_alert_commands():
    store = FakeStore()
    c = BotCommands(store, FakeSearch(), {ME})
    assert "Alerta 1" in reply(c, "/alerta auriculares sony hasta 250")
    assert "auriculares sony (hasta 250 €)" in reply(c, "/alertas")
    assert "borrada" in reply(c, "/borrar 1")
    assert "No tienes alertas" in reply(c, "/alertas")
    assert "número" in reply(c, "/borrar x")


def test_search_by_plain_text():
    c = BotCommands(FakeStore(), FakeSearch(), {ME})
    assert "Auriculares Sony &lt;XM5&gt;" in reply(c, "auriculares sony")
    assert "No he encontrado" in reply(c, "/buscar lavadora")
    assert "No conozco" in reply(c, "/raro")


def test_webhook_needs_the_secret():
    bot = FakeBot()
    app = create_app(bot=bot, commands=BotCommands(FakeStore(), FakeSearch(), {ME}), secret="s3cr3t")
    api = TestClient(app)
    update = {"update_id": 1, "message": msg("/start")}
    assert api.post("/telegram/webhook", json=update).status_code == 403
    assert (
        api.post("/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "otro"}).status_code
        == 403
    )
    assert bot.sent == []
    ok = api.post("/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"})
    assert ok.status_code == 200 and bot.sent[0][0] == ME


def test_alert_notifier_sends_once_per_chat():
    store = FakeStore()
    asyncio.run(store.add(ME, "sony", None))
    asyncio.run(store.add(ME, "auriculares", Decimal("300")))
    asyncio.run(store.add(ME, "caros", Decimal("5")))
    bot = FakeBot()
    sent = asyncio.run(AlertNotifier(bot, store).deal_saved(deal(price_sale=Decimal("249"))))
    assert sent == 1 and len(bot.sent) == 1
    assert "auriculares, sony" in bot.sent[0][1]


def test_allowed_users():
    assert allowed_users("1267045133, x, -5") == {1267045133, -5}


def test_open_to_everyone_with_a_search_limit():
    now = [0.0]
    c = BotCommands(FakeStore(), FakeSearch(), set(), clock=lambda: now[0])
    assert reply(c, "/start", user=42).startswith("🛍️")
    for _ in range(30):
        assert "Auriculares" in reply(c, "sony", user=42)
    assert "muchas búsquedas" in reply(c, "sony", user=42)
    assert "Auriculares" in reply(c, "sony", user=43)  # each person has their own limit
    now[0] = 3601
    assert "Auriculares" in reply(c, "sony", user=42)


def test_httpx_never_logs_request_urls():
    import logging

    import src.infrastructure.telegram.bot_api  # noqa: F401

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
