import logging

from telethon import events

from src.infrastructure.telegram.client import TelegramService
from src.services.search import SearchService

logger = logging.getLogger(__name__)

HELP = (
    "¡Hola! Soy CazaChollos Bot 🤖.\n"
    "Escribe `/buscar <producto>` o simplemente envíame el nombre de lo que buscas.\n"
    "Ejemplo: `auriculares sony`"
)


def _md(text: str) -> str:
    """Telegram markdown: brackets and asterisks in a title would break the link or the bold."""
    return text.replace("[", "(").replace("]", ")").replace("*", "").replace("_", " ").replace("`", "'")


def format_deal(deal) -> str:
    if deal.price_sale is None:
        price = "Precio no indicado"
    else:
        price = f"{deal.price_sale}€"
        original_price = deal.price_before or deal.price_retail
        if original_price and original_price > deal.price_sale:
            discount = round((1 - (deal.price_sale / original_price)) * 100)
            price += f" (Antes: {original_price}€ | -{discount}%)"
    shop_info = f" | 🛒 {_md(deal.shop)}" if deal.shop else ""
    title = f"[{_md(deal.title)}]({deal.url})" if deal.url else _md(deal.title)
    return f"🔥 **{title}**\n💰 {price}{shop_info}\n📊 Score: {deal.chollo_score}/100\n"


class BotService:
    def __init__(self, telegram_service: TelegramService, search_service: SearchService | None = None):
        self.telegram = telegram_service
        self.search_service = search_service or SearchService()

    def register_handlers(self) -> None:
        # Only private chats and incoming messages: in a group it would answer everyone, and it must never
        # react to its own replies.
        private = {"incoming": True, "func": lambda e: e.is_private}

        @self.telegram.client.on(events.NewMessage(pattern=r"^/(start|help|ayuda)\b", **private))
        async def start_handler(event):
            await event.respond(HELP)

        @self.telegram.client.on(events.NewMessage(**private))
        async def message_handler(event):
            text = (event.message.text or "").strip()
            if not text or text.startswith(("/start", "/help", "/ayuda")):
                return
            query = text.removeprefix("/buscar").strip()
            if not query:
                await event.respond("Por favor, dime qué quieres buscar.")
                return
            await event.respond(f"🔍 Buscando '{query[:100]}'...")
            try:
                results = await self.search_service.search_deals(query)
            except Exception:
                logger.exception("Search failed")
                await event.respond("Ups, ha ocurrido un error al buscar. Inténtalo más tarde.")
                return
            if not results:
                await event.respond("No he encontrado chollos recientes para esa búsqueda. 🥺")
                return
            response = f"He encontrado {len(results)} ofertas para '{query[:100]}':\n\n"
            response += "\n".join(format_deal(d) for d in results)
            await event.respond(response, link_preview=False)
