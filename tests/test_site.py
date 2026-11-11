from datetime import datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from src.web.deals_query import DealCard, Filters, Page, where_clause
from src.web.site import ago, can_see, create_app, euros, parse_filters


def card(**kw):
    base = dict(
        id="1",
        title="Auriculares Sony WH-1000XM5",
        url="https://amazon.es/dp/X",
        price=Decimal("249"),
        before=Decimal("419"),
        discount=40,
        shop="Amazon",
        channel="canalninja",
        category="tecnologia",
        score=56,
        image_url="https://cdn4.telesco.pe/file/a.jpg",
        post_url="https://t.me/canalninja/1",
        created_at=datetime.utcnow() - timedelta(minutes=30),
    )
    return DealCard(**{**base, **kw})


def fake_finder(deals, total=None):
    async def finder(filters: Filters) -> Page:
        f = filters.normalised()
        return Page(
            deals, total if total is not None else len(deals), f, [("tecnologia", 1)], ["Amazon"], ["canalninja"]
        )

    return finder


def test_euros_and_ago():
    assert euros(Decimal("12.5")) == "12,50 €" and euros(Decimal("1234")) == "1.234 €"
    now = datetime(2026, 11, 11, 12, 0)
    assert ago(now - timedelta(minutes=5), now) == "hace 5 min"
    assert ago(now - timedelta(hours=3), now) == "hace 3 h"
    assert ago(now - timedelta(days=1, hours=2), now) == "hace 1 día"


def test_parse_filters_is_forgiving():
    f = parse_filters({"q": "sony", "dto": "abc", "max": "99,5", "orden": "x", "page": "-3"}).normalised()
    assert f.q == "sony" and f.min_discount == 0 and f.max_price == Decimal("99.5")
    assert f.sort == "recientes" and f.page == 1
    assert parse_filters({"q": "sony"}).sort == "relevancia"


def test_where_clause_uses_parameters_only():
    sql, params = where_clause(Filters(q="'; drop table deals; --", shop="Amazon", min_discount=40))
    assert "drop table" not in sql and params["q"].startswith("'; drop")


def test_access_rules():
    from base64 import b64encode
    import json

    h = {
        "X-Ms-Client-Principal": b64encode(
            json.dumps({"claims": [{"typ": "email", "val": "amigo@gmail.com"}]}).encode()
        ).decode()
    }
    assert can_see(h, "*")[0] and not can_see({}, "*")[0]
    assert not can_see(h, "dani.algar02@gmail.com")[0] and can_see(h, "dani.algar02@gmail.com,amigo@gmail.com")[0]
    assert can_see({}, "")[0]


def test_page_renders_cards():
    api = TestClient(
        create_app(
            finder=fake_finder([card(), card(id="2", price=Decimal("0"), before=None, discount=None, image_url=None)]),
            allowed_emails="",
            with_bot=False,
        )
    )
    html = api.get("/").text
    assert "Auriculares Sony WH-1000XM5" in html and "249 €" in html and "419 €" in html and "-40 %" in html
    assert "Gratis" in html and "hace 30 min" in html and 'href="https://t.me/canalninja/1"' in html
    assert "Mejor puntuación" in html and "Mayor descuento" in html and "Precio más bajo" in html


def test_more_button_and_partial():
    finder = fake_finder([card()], total=100)
    api = TestClient(create_app(finder=finder, allowed_emails="", with_bot=False))
    html = api.get("/?cat=tecnologia&orden=precio_asc").text
    assert 'data-next="/?cat=tecnologia&amp;orden=precio_asc&amp;page=2&amp;partial=1"' in html
    part = api.get("/?cat=tecnologia&page=2&partial=1").text
    assert "<html" not in part and 'class="card"' in part


def test_forbidden_without_allowed_email():
    api = TestClient(create_app(finder=fake_finder([]), allowed_emails="dani.algar02@gmail.com", with_bot=False))
    assert api.get("/").status_code == 403
