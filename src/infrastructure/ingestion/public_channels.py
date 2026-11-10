"""Public Telegram channels read from their web preview (https://t.me/s/<channel>), with no account at all.

Every public channel has that page with its latest ~20 posts, and `?before=<id>` gives the previous ones. Each
pass reads the new posts since the last one stored for the channel and ends: it is meant to run on a schedule
(every 15 minutes), not to stay connected. No login means no Telegram account at risk.

Only public channels: groups and private channels have no web preview.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import zlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from src.domain.ingestion.models import IngestionEvent, IngestionSourceType
from src.domain.ingestion.strategy import IngestionStrategy

logger = logging.getLogger(__name__)

BASE_URL = "https://t.me/s/"
USER_AGENT = "CazaChollos/0.2 (+https://github.com/darkwerty/cazachollos)"
CHANNEL_RE = re.compile(r"^[A-Za-z0-9_]{4,64}$")


@dataclass
class ChannelPost:
    channel: str
    chat_id: int
    msg_id: int
    text: str
    date: datetime | None
    image_url: str | None = None


def channel_name(value: str) -> str | None:
    """'https://t.me/canalninja', 't.me/s/canalninja', '@canalninja' or 'canalninja' -> 'canalninja'."""
    v = value.strip().rstrip("/")
    v = re.sub(r"^(https?://)?(www\.)?t\.me/(s/)?", "", v).lstrip("@")
    return v if CHANNEL_RE.match(v) else None


def fallback_chat_id(channel: str) -> int:
    """Stable negative id when the page does not carry the real one (never clashes with real ids, all < -1e12)."""
    return -(10**13 + zlib.crc32(channel.lower().encode()))


def _view_chat_id(data_view: str | None) -> int | None:
    """The real channel id travels base64-encoded in data-view: {"c": -2874860191, "p": 147205, ...}."""
    if not data_view:
        return None
    try:
        raw = base64.urlsafe_b64decode(data_view + "=" * (-len(data_view) % 4))
        value = json.loads(raw).get("c")
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def message_text(node) -> str:
    """Post text with line breaks and the real link of every anchor (the visible text is often shortened)."""
    for br in node.find_all("br"):
        br.replace_with("\n")
    for a in node.find_all("a"):
        href = a.get("href", "")
        label = a.get_text()
        a.replace_with(label if not href.startswith("http") or href in label else f"{label} {href}")
    return node.get_text().strip()


IMAGE_SELECTORS = (
    "a.tgme_widget_message_photo_wrap",
    ".link_preview_image",
    ".link_preview_right_image",
    "i.tgme_widget_message_video_thumb",
)
STYLE_URL = re.compile(r"background-image:\s*url\('([^']+)'\)")


def post_image(node) -> str | None:
    """The photo of the post, or the image of its link preview (the same picture the channel shows)."""
    for selector in IMAGE_SELECTORS:
        el = node.select_one(selector)
        m = STYLE_URL.search(el.get("style", "")) if el is not None else None
        if m and m.group(1).startswith("https://"):
            return m.group(1)
    return None


def parse_page(html: str, channel: str) -> list[ChannelPost]:
    """Posts of one page of https://t.me/s/<channel>, oldest first. Posts without text (only media) are skipped."""
    soup = BeautifulSoup(html, "html.parser")
    posts: list[ChannelPost] = []
    for node in soup.select("div.tgme_widget_message[data-post]"):
        _name, _, num = node["data-post"].rpartition("/")
        if not num.isdigit():
            continue
        text_node = node.select_one(".tgme_widget_message_text")
        if text_node is None:
            continue
        text = message_text(text_node)
        if not text:
            continue
        stamp = node.select_one(".tgme_widget_message_date time[datetime]")
        date = None
        if stamp is not None:
            try:
                date = datetime.fromisoformat(stamp["datetime"]).replace(tzinfo=None)  # UTC, like the rest of the DB
            except ValueError:
                date = None
        chat_id = _view_chat_id(node.get("data-view")) or fallback_chat_id(channel)
        posts.append(ChannelPost(channel, chat_id, int(num), text, date, post_image(node)))
    return sorted(posts, key=lambda p: p.msg_id)


Fetch = Callable[[str], Awaitable[str | None]]
Cursor = Callable[[int], Awaitable[int | None]]


class PublicChannelsStrategy(IngestionStrategy):
    """One pass over the channels: new posts since the stored cursor of each one, then the stream ends.

    - First time a channel is seen, only its latest page (about 20 posts): no flood of old messages.
    - If more than a page was published since the last pass, it goes back with ?before= up to `max_pages`.
    - One request per second at most, and a channel that fails is skipped until the next pass.
    """

    def __init__(
        self,
        channels: list[str],
        cursor: Cursor,
        fetch: Fetch | None = None,
        max_pages: int = 10,
        delay_s: float = 1.0,
    ) -> None:
        self.channels = [c for c in (channel_name(x) for x in channels) if c]
        self.cursor = cursor
        self.fetch = fetch or self._http_fetch
        self.max_pages = max_pages
        self.delay_s = delay_s
        self._client: httpx.AsyncClient | None = None
        self._running = True

    async def _http_fetch(self, url: str) -> str | None:
        if self._client is None:
            self._client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20.0, follow_redirects=True)
        try:
            resp = await self._client.get(url)
        except httpx.HTTPError as e:
            logger.warning("Could not read %s: %s", url, e)
            return None
        if resp.status_code != 200:
            logger.warning("Could not read %s: HTTP %s", url, resp.status_code)
            return None
        return resp.text

    async def _channel_posts(self, channel: str) -> list[ChannelPost]:
        html = await self.fetch(BASE_URL + channel)
        if html is None:
            return []
        page = parse_page(html, channel)
        if not page:
            logger.info("%s: no posts with text (is it a public channel?)", channel)
            return []
        last = await self.cursor(page[0].chat_id)
        if last is None:
            return page  # first time: only the latest page
        collected = [p for p in page if p.msg_id > last]
        oldest = page[0].msg_id
        pages = 1
        while oldest > last + 1 and pages < self.max_pages and self._running:
            await asyncio.sleep(self.delay_s)
            html = await self.fetch(f"{BASE_URL}{channel}?before={oldest}")
            older = parse_page(html, channel) if html else []
            older = [p for p in older if p.msg_id < oldest]
            if not older:
                break
            collected = [p for p in older if p.msg_id > last] + collected
            oldest = older[0].msg_id
            pages += 1
        if oldest > last + 1 and pages >= self.max_pages:
            logger.warning("%s: more than %d pages since the last pass, the oldest ones are skipped", channel, pages)
        return collected

    async def stream(self) -> AsyncIterator[IngestionEvent]:
        logger.info("Reading %d public channels", len(self.channels))
        try:
            for i, channel in enumerate(self.channels):
                if not self._running:
                    break
                if i:
                    await asyncio.sleep(self.delay_s)
                posts = await self._channel_posts(channel)
                logger.info("%s: %d new posts", channel, len(posts))
                for p in posts:
                    yield IngestionEvent(
                        content=p.text,
                        source_type=IngestionSourceType.WEB,
                        occurred_at=p.date or datetime.utcnow(),
                        source_metadata={
                            "chat_id": p.chat_id,
                            "chat_title": p.channel,
                            "msg_id": p.msg_id,
                            "image_url": p.image_url,
                            "post_url": f"https://t.me/{p.channel}/{p.msg_id}",
                        },
                    )
        finally:
            await self.stop()

    async def stop(self) -> None:
        self._running = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None
