from telethon import events
from src.infrastructure.telegram.client import TelegramService
from src.services.search import SearchService

class BotService:
    def __init__(self, telegram_service: TelegramService):
        self.telegram = telegram_service
        self.search_service = SearchService()

    def _format_deal(self, deal) -> str:
        price = f"{deal.price_sale}€"
        original_price = deal.price_before or deal.price_retail
        
        if original_price and original_price > deal.price_sale:
            discount = round((1 - (deal.price_sale / original_price)) * 100)
            price += f" (Antes: {original_price}€ | -{discount}%)"
        
        shop_info = f" | 🛒 {deal.shop}" if deal.shop else ""
            
        return f"🔥 **[{deal.title}]({deal.url})**\n💰 {price}{shop_info}\n📊 Score: {deal.chollo_score}/100\n"

    async def start(self):
        # /start command
        @self.telegram.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.respond(
                "¡Hola! Soy CazaChollos Bot 🤖.\n"
                "Escribe `/buscar <producto>` o simplemente envíame el nombre de lo que buscas.\n"
                "Ejemplo: `auriculares sony`"
            )

        # /buscar command or plain text
        @self.telegram.client.on(events.NewMessage())
        async def message_handler(event):
            # Ignore commands handled by other patterns if any (simplistic check)
            text = event.message.text
            if not text or text.startswith('/start'):
                return

            query = text.replace('/buscar', '').strip()
            if not query:
                await event.respond("Por favor, dime qué quieres buscar.")
                return

            await event.respond(f"🔍 Buscando '{query}'...")
            
            try:
                results = await self.search_service.search_deals(query)
                if not results:
                    await event.respond("No he encontrado chollos recientes para esa búsqueda. 🥺")
                    return

                response_text = f"He encontrado {len(results)} ofertas para '{query}':\n\n"
                for deal in results:
                    response_text += self._format_deal(deal) + "\n"
                
                await event.respond(response_text, link_preview=False)
            except Exception as e:
                print(f"Error searching: {e}")
                await event.respond("Ups, ha ocurrido un error al buscar. Inténtalo más tarde.")

        await self.telegram.start()
        print("Bot Service Started...")
        await self.telegram.run_until_disconnected()
