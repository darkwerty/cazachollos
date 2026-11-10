import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.infrastructure.ingestion.replay_file import ReplayFileStrategy
from src.services.bot import format_deal
from src.services.llm_services import GeminiLLMProvider
from src.services.parser import DealParser


def parser_without_llm() -> DealParser:
    llm = MagicMock()
    llm.parse_deal.return_value = {}
    return DealParser(llm_provider=llm)


# ---------- price and score ----------
def test_missing_price_is_none_not_a_freebie():
    result = parser_without_llm().parse("Monitor LG UltraGear 27\nhttps://www.amazon.es/dp/B0EJEMPLO03")
    assert result["price_sale"] is None
    assert result["chollo_score"] < 100


def test_explicit_gratis_is_a_freebie():
    result = parser_without_llm().parse("GRATIS: juego de PC esta semana\nhttps://store.epicgames.com/es-ES/p/x")
    assert result["price_sale"] == Decimal(0)
    assert result["chollo_score"] == 100


def test_discount_from_both_prices():
    result = parser_without_llm().parse("Freidora\nAhora: 29,99€ (Antes: 89,99€)\nhttps://www.pccomponentes.com/x")
    assert result["price_sale"] == Decimal("29.99")
    assert result["price_before"] == Decimal("89.99")
    assert result["discount_percentage"] == 66


# ---------- Gemini provider ----------
def fake_client(text: str):
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    return client


def test_gemini_valid_structured_output():
    payload = {
        "title": "Sony WH-1000XM5",
        "product_name": "WH-1000XM5",
        "category": "tecnologia",
        "confidence": 0.92,
        "price_sale": 249,
        "price_before": 419,
        "discount_percentage": 41,
        "one_line_summary": "Mínimo histórico",
    }
    provider = GeminiLLMProvider(client=fake_client(json.dumps(payload)), model="m")
    out = provider.parse_deal("texto")
    assert out["title"] == "Sony WH-1000XM5"
    assert out["category"] == "tecnologia"
    assert out["price_sale"] == 249


def test_gemini_out_of_range_answer_is_discarded():
    payload = {"title": "X", "product_name": "X", "category": "tecnologia", "confidence": 7}
    provider = GeminiLLMProvider(client=fake_client(json.dumps(payload)), model="m")
    assert provider.parse_deal("texto") == {}


def test_gemini_unknown_category_is_discarded():
    payload = {"title": "X", "product_name": "X", "category": "coches", "confidence": 0.9}
    provider = GeminiLLMProvider(client=fake_client(json.dumps(payload)), model="m")
    assert provider.parse_deal("texto") == {}


def test_gemini_error_falls_back_to_rules():
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("503")
    parser = DealParser(llm_provider=GeminiLLMProvider(client=client, model="m"))
    result = parser.parse("Sartén Tefal 24cm\nOferta: 20€\nhttps://www.amazon.es/dp/B0EJEMPLO02")
    assert result["price_sale"] == Decimal("20")
    assert "Tefal" in result["title"]


def test_gemini_without_key_is_disabled():
    provider = GeminiLLMProvider(api_key=None)
    assert not provider.enabled
    assert provider.parse_deal("texto") == {}


# ---------- bot ----------
def deal(**kw):
    base = dict(
        title="Auriculares [Sony] *XM5*",
        url="https://www.amazon.es/dp/B0EJEMPLO01",
        price_sale=Decimal("249"),
        price_before=Decimal("419"),
        price_retail=None,
        shop="Amazon",
        chollo_score=90,
    )
    return SimpleNamespace(**{**base, **kw})


def test_format_deal_escapes_markdown_and_shows_discount():
    text = format_deal(deal())
    assert "[Auriculares (Sony) XM5](https://www.amazon.es/dp/B0EJEMPLO01)" in text
    assert "-41%" in text


def test_format_deal_without_price():
    assert "Precio no indicado" in format_deal(deal(price_sale=None))


# ---------- sample replay file ----------
def test_sample_replay_file_is_valid():
    async def read():
        return [e async for e in ReplayFileStrategy("replay_data.jsonl", speed_factor=10_000).stream()]

    events = asyncio.run(read())
    assert len(events) >= 10
    assert all(e.source_metadata.get("msg_id") for e in events)


# ---------- titles and categories from the sample messages ----------
def test_title_without_markdown_or_noise():
    text = "🔥 **CHOLLAZO** Auriculares Sony WH-1000XM5\n\n✅ Precio: 249€\nhttps://www.amazon.es/dp/B0EJEMPLO01"
    title = parser_without_llm().parse(text)["title"]
    assert "*" not in title and "CHOLLAZO" not in title
    assert "Sony WH-1000XM5" in title


def test_air_fryer_is_kitchen():
    text = "Freidora de aire Cecotec Cecofry 5,5 L\nAhora: 29,99€\nhttps://www.pccomponentes.com/x"
    assert parser_without_llm().parse(text)["category"] == "cocina"


def test_noise_words_only_as_whole_words():
    text = "Cafetera superautomática Philips Serie 2200\nBajada a 299€\nhttps://www.elcorteingles.es/cafetera"
    result = parser_without_llm().parse(text)
    assert "superautomática" in result["title"]
    assert result["shop"] == "El Corte Inglés"


def test_title_has_no_leading_punctuation():
    text = "GRATIS: juego de PC para reclamar esta semana\nhttps://store.epicgames.com/es-ES/p/x"
    assert parser_without_llm().parse(text)["title"].startswith("juego de PC")
