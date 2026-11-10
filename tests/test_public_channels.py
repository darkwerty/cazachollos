import asyncio
import base64
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.infrastructure.ingestion.public_channels import (
    PublicChannelsStrategy,
    channel_name,
    fallback_chat_id,
    parse_page,
)
from src.services.llm_services import AzureOpenAILLMProvider, NoLLMProvider, make_llm_provider
from src.services.parser import DealParser
from src.services.schedule import madrid_time, within_active_hours

CHAT = -2874860191


def post(n: int, text: str = "Oferta: 9,99€", chat: int = CHAT, media_only: bool = False) -> str:
    view = base64.urlsafe_b64encode(json.dumps({"c": chat, "p": n}).encode()).decode().rstrip("=")
    body = "" if media_only else f'<div class="tgme_widget_message_text js-message_text">{text}</div>'
    return (
        f'<div class="tgme_widget_message js-widget_message" data-post="canal/{n}" data-view="{view}">{body}'
        f'<a class="tgme_widget_message_date"><time datetime="2026-11-10T20:51:29+00:00">20:51</time></a></div>'
    )


def page(ids, **kw) -> str:
    return "<html><body>" + "".join(post(i, **kw) for i in ids) + "</body></html>"


def test_channel_names():
    assert channel_name("https://t.me/canalninja") == "canalninja"
    assert channel_name("http://t.me/s/canalninja/") == "canalninja"
    assert channel_name("@DonOFERTON_oficial") == "DonOFERTON_oficial"
    assert channel_name("https://evil.example/x") is None


def test_parse_page_text_links_and_ids():
    html = page(
        [5],
        text='<b>Cámara Blink</b><br/>Nuevo Precio: 0.98 €<br/><a href="?q=%23oficina">#oficina</a><br/>'
        '<a href="https://go.donoferton.club/p8nF3j0MXqG6">¡Lo QUIERO!</a>',
    )
    [p] = parse_page(html, "canal")
    assert p.chat_id == CHAT and p.msg_id == 5
    assert "Cámara Blink\nNuevo Precio: 0.98 €" in p.text
    assert "#oficina" in p.text and "https://go.donoferton.club/p8nF3j0MXqG6" in p.text
    assert p.date == datetime(2026, 11, 10, 20, 51, 29)


def test_media_only_posts_are_skipped():
    assert parse_page(page([1], media_only=True), "canal") == []


def test_fallback_chat_id_is_stable_and_out_of_range():
    assert fallback_chat_id("Canal") == fallback_chat_id("canal") < -(10**12)


def run(strategy):
    async def go():
        return [e async for e in strategy.stream()]

    return asyncio.run(go())


def fake_site(pages: dict[str, str]):
    calls = []

    async def fetch(url: str):
        calls.append(url)
        return pages.get(url)

    return fetch, calls


def test_first_pass_takes_only_the_latest_page():
    fetch, calls = fake_site({"https://t.me/s/canal": page(range(81, 101))})

    async def cursor(chat_id):
        return None

    events = run(PublicChannelsStrategy(["canal"], cursor, fetch=fetch, delay_s=0))
    assert [e.source_metadata["msg_id"] for e in events] == list(range(81, 101))
    assert calls == ["https://t.me/s/canal"]


def test_next_pass_goes_back_until_the_cursor():
    fetch, calls = fake_site(
        {
            "https://t.me/s/canal": page(range(81, 101)),
            "https://t.me/s/canal?before=81": page(range(61, 81)),
        }
    )

    async def cursor(chat_id):
        assert chat_id == CHAT
        return 70

    events = run(PublicChannelsStrategy(["https://t.me/canal"], cursor, fetch=fetch, delay_s=0))
    assert [e.source_metadata["msg_id"] for e in events] == list(range(71, 101))
    assert events[0].source_metadata == {"chat_id": CHAT, "chat_title": "canal", "msg_id": 71}


def test_nothing_new_means_one_request():
    fetch, calls = fake_site({"https://t.me/s/canal": page(range(81, 101))})

    async def cursor(chat_id):
        return 100

    assert run(PublicChannelsStrategy(["canal"], cursor, fetch=fetch, delay_s=0)) == []
    assert len(calls) == 1


def test_failing_channel_is_skipped():
    fetch, _ = fake_site({"https://t.me/s/bueno": page([1])})

    async def cursor(chat_id):
        return None

    events = run(PublicChannelsStrategy(["roto", "bueno"], cursor, fetch=fetch, delay_s=0))
    assert len(events) == 1


# ---------- active hours ----------
def test_madrid_time_summer_and_winter():
    assert madrid_time(datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)).hour == 12
    assert madrid_time(datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)).hour == 11


def test_active_hours_window():
    at = lambda h: datetime(2026, 12, 1, h - 1, 30, tzinfo=timezone.utc)  # noqa: E731 - winter: UTC+1
    assert within_active_hours("7-24", at(7)) and within_active_hours("7-24", at(23))
    assert not within_active_hours("7-24", at(6)) and not within_active_hours("7-24", at(1))
    assert within_active_hours("", at(3))


# ---------- when the LLM is worth it ----------
def test_needs_llm():
    assert DealParser.needs_llm({"price_sale": None, "category": "tecnologia", "title": "Sony WH-1000XM5"})
    assert DealParser.needs_llm({"price_sale": 9, "category": "otros", "title": "Sony WH-1000XM5"})
    assert DealParser.needs_llm({"price_sale": 9, "category": "tecnologia", "title": "x"})
    assert not DealParser.needs_llm({"price_sale": 9, "category": "tecnologia", "title": "Sony WH-1000XM5"})


def test_azure_provider_structured_output():
    payload = {
        "title": "Cartuchos Schneider",
        "product_name": "Cartuchos",
        "category": "otros",
        "confidence": 0.8,
        "price_sale": 0.98,
        "price_before": 4.22,
        "discount_percentage": 77,
        "one_line_summary": "Error de precio",
    }
    client = MagicMock()
    message = SimpleNamespace(content=json.dumps(payload))
    client.beta.chat.completions.parse.return_value = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    out = AzureOpenAILLMProvider(client=client, deployment="gpt-4.1-mini").parse_deal("texto")
    assert out["price_sale"] == 0.98 and out["category"] == "otros"
    assert client.beta.chat.completions.parse.call_args.kwargs["model"] == "gpt-4.1-mini"


def test_azure_provider_error_falls_back():
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = RuntimeError("429")
    assert AzureOpenAILLMProvider(client=client).parse_deal("texto") == {}


def test_provider_choice(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")
    assert isinstance(make_llm_provider(), NoLLMProvider)
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    assert not make_llm_provider().enabled
