import re
import unicodedata
import logging
from decimal import Decimal
from typing import Optional, List

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from price_parser import Price
from src.domain.enums import CategoryEnum
from src.services.llm_services import LLMProvider, make_llm_provider

logger = logging.getLogger(__name__)


# Lines that announce a promotion, not the product
PROMO_LINE = re.compile(r"^(c[oó]digo|cup[oó]n|descuento|env[ií]o gratis|primer pedido)\b", re.IGNORECASE)
# Titles that say nothing about the product: "CHOLLITO BRICO", "CUPÓN 50%", "I9"
GENERIC_TITLE = re.compile(
    r"^(chollit?o|chollazo|chollo|cholo|cup[oó]n|oferta|ofert[oó]n|descuento|top \d+)\b", re.IGNORECASE
)
TRAILING_WORDS = re.compile(r"(?:\s+(?:solo|sólo|desde|por|a|al|en|con|de|y))+\s*$", re.IGNORECASE)
EMPTY_PARENS = re.compile(r"\(\s*[\w ]{0,12}:?\s*\)")


def clean_title(title: str) -> str:
    """Drops emojis, flags, invisible characters, empty "(PVP: )" and dangling words like "solo" or "desde"."""
    out = "".join(ch for ch in title if unicodedata.category(ch)[0] in "LNPZ" or ch in "+&%$€'\"/")
    out = EMPTY_PARENS.sub("", out)
    out = re.sub(r"\s*(?:[—–-]{2,}>?|-->|—|–)\s*", " ", out)  # "NEW ERA —-> 5€"
    out = re.sub(r"\s+", " ", out).strip(" -:|·,;")
    for _ in range(3):
        out = TRAILING_WORDS.sub("", out).strip(" -:|,;")
    return out


def is_generic_title(title: str) -> bool:
    t = clean_title(title)
    words = t.split()
    return bool(GENERIC_TITLE.match(t)) or (len(words) <= 2 and (t.isupper() or len(t) < 8))


class DealParser:
    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider or make_llm_provider()

        # Category keywords (expanded)
        # Category keywords, checked IN ORDER: the specific ones first (a "juego de PS5" is a video game before
        # electronics, a "freidora Cecotec" is kitchen before home). Short keywords (< 4) need word boundaries.
        self.categories_keywords = {
            CategoryEnum.VIDEOJUEGOS: [
                "videojuego",
                "ps5",
                "ps4",
                "playstation",
                "xbox",
                "nintendo",
                "switch",
                "steam",
                "juego de pc",
                "juego para",
                "mando",
                "dualsense",
                "gaming headset",
            ],
            CategoryEnum.LIBROS: [
                "libro",
                "audiolibro",
                "ebook",
                "kindle unlimited",
                "audible",
                "novela",
                "comic",
                "manga",
                "vinilo",
                "blu-ray",
                "bluray",
                "dvd",
                "pelicula",
            ],
            CategoryEnum.MASCOTAS: [
                "gato",
                "gatos",
                "perro",
                "perros",
                "mascota",
                "pienso",
                "rascador",
                "arenero",
                "acuario",
                "comedero",
            ],
            CategoryEnum.ALIMENTACION: [
                "lomo",
                "jamon",
                "chorizo",
                "queso",
                "aceite de oliva",
                "cafe en grano",
                "capsulas",
                "chocolate",
                "galletas",
                "frutos secos",
                "pasas",
                "kinder",
                "lacasitos",
                "cerveza",
                "vino",
                "tinto",
                "ribera",
                "rioja",
                "whisky",
                "ginebra",
                "refresco",
                "agua mineral",
                "conservas",
                "atun",
                "pasta",
                "arroz",
                "cereales",
                "turron",
                "calendario de adviento",
                "snack",
                "proteina",
            ],
            CategoryEnum.BELLEZA: [
                "desodorante",
                "champu",
                "gel de ducha",
                "crema",
                "serum",
                "perfume",
                "colonia",
                "maquillaje",
                "esmalte",
                "pintalabios",
                "rimel",
                "protector solar",
                "spf",
                "cepillo de dientes",
                "dientes",
                "colgate",
                "oral-b",
                "afeitadora",
                "depiladora",
                "maquinilla",
                "secador",
                "plancha de pelo",
                "vitamina",
                "suplemento",
                "colageno",
                "preservativos",
                "spray nasal",
                "dove",
                "nivea",
                "rexona",
                "loreal",
                "l'oreal",
                "garnier",
                "isdin",
                "neutrogena",
                "olay",
            ],
            CategoryEnum.COCINA: [
                "sarten",
                "olla",
                "freidora",
                "airfryer",
                "batidora",
                "cafetera",
                "cocina",
                "horno",
                "microondas",
                "lavavajillas",
                "cuchillo",
                "vajilla",
                "tupper",
                "robot de cocina",
                "thermomix",
                "tostadora",
                "parrilla",
                "sandwichera",
                "hervidor",
                "exprimidor",
            ],
            CategoryEnum.BRICOLAJE: [
                "taladro",
                "atornillador",
                "herramienta",
                "bricolaje",
                "llave",
                "destornillador",
                "sierra",
                "lijadora",
                "jardin",
                "manguera",
                "cortacesped",
                "barbacoa",
                "pintura",
                "escalera",
                "bosch professional",
                "makita",
                "dewalt",
                "black+decker",
                "einhell",
                "ryobi",
            ],
            CategoryEnum.MOTOR: [
                "coche",
                "moto",
                "neumatico",
                "casco",
                "candado moto",
                "aceite motor",
                "dashcam",
                "patinete",
                "bicicleta electrica",
            ],
            CategoryEnum.OFICINA: [
                "cartucho",
                "tinta",
                "toner",
                "impresora",
                "papel",
                "boligrafo",
                "pluma estilografica",
                "cuaderno",
                "agenda",
                "mochila escolar",
                "estuche",
                "calculadora",
            ],
            CategoryEnum.TECNOLOGIA: [
                "movil",
                "smartphone",
                "iphone",
                "xiaomi",
                "samsung",
                "redmi",
                "tv",
                "televisor",
                "portatil",
                "laptop",
                "ram",
                "ssd",
                "disco duro",
                "pixel",
                "tablet",
                "ipad",
                "auriculares",
                "altavoz",
                "sony",
                "lg",
                "apple",
                "monitor",
                "pc",
                "ordenador",
                "router",
                "repetidor",
                "wifi",
                "smartwatch",
                "reloj",
                "camara",
                "bateria externa",
                "powerbank",
                "cargador",
                "cable usb",
                "usb",
                "teclado",
                "raton",
                "echo dot",
                "alexa",
                "fire tv",
                "chromecast",
                "proyector",
                "barra de sonido",
                "videotimbre",
            ],
            CategoryEnum.JUGUETES: [
                "lego",
                "playmobil",
                "muñeca",
                "juguete",
                "juego de mesa",
                "puzzle",
                "infantil",
                "bebe",
                "pañales",
                "carrito",
                "peluche",
                "funko",
                "hot wheels",
                "barbie",
            ],
            CategoryEnum.DEPORTE: [
                "pesa",
                "mancuerna",
                "bici",
                "bicicleta",
                "gym",
                "deporte",
                "fitness",
                "running",
                "futbol",
                "baloncesto",
                "padel",
                "raqueta",
                "esterilla",
                "yoga",
                "garmin",
                "chandal",
                "decathlon",
                "under armour",
                "asics",
            ],
            CategoryEnum.MODA: [
                "camiseta",
                "pantalon",
                "vaquero",
                "jeans",
                "zapatos",
                "zapatillas",
                "botas",
                "sandalias",
                "nike",
                "adidas",
                "ropa",
                "abrigo",
                "chaqueta",
                "sudadera",
                "jersey",
                "sueter",
                "puma",
                "vans",
                "converse",
                "vestido",
                "falda",
                "bolso",
                "mochila",
                "cartera",
                "gafas de sol",
                "calcetines",
                "bañador",
                "tommy hilfiger",
                "levis",
                "ralph lauren",
                "lacoste",
                "the north face",
                "quiksilver",
                "desigual",
                "ugg",
                "golden goose",
                "stone island",
                "corteiz",
                "nude project",
                "moncler",
                "gucci",
                "prada",
                "zara",
                "shein",
            ],
            CategoryEnum.HOGAR: [
                "silla",
                "mesa",
                "sofa",
                "cama",
                "colchon",
                "almohada",
                "sabanas",
                "edredon",
                "mueble",
                "estanteria",
                "lampara",
                "bombilla",
                "salon",
                "baño",
                "toalla",
                "aspirador",
                "aspiradora",
                "robot aspirador",
                "rowenta",
                "cecotec",
                "dyson",
                "roomba",
                "conga",
                "fregona",
                "detergente",
                "suavizante",
                "lavadora",
                "secadora",
                "frigorifico",
                "calefactor",
                "ventilador",
                "humidificador",
                "purificador",
                "cortina",
                "alfombra",
                "decoracion",
                "navidad",
                "arbol de navidad",
                "maleta",
                "maletas",
                "candado",
            ],
        }

        # Mapping domain/keywords to Shop names
        self.shop_map = {
            "amazon": "Amazon",
            "amzn": "Amazon",
            "amz.tf": "Amazon",
            "aliexpress": "Aliexpress",
            "miravia": "Miravia",
            "pccomponentes": "PcComponentes",
            "media markt": "MediaMarkt",
            "mediamarkt": "MediaMarkt",
            "el corte ingles": "El Corte Inglés",
            "elcorteingles": "El Corte Inglés",
            "carrefour": "Carrefour",
            "lidl": "Lidl",
            "ebay": "eBay",
            "nike": "Nike",
            "adidas": "Adidas",
            "zalando": "Zalando",
            "shein": "Shein",
            "temu": "Temu",
        }

        # Common Brands for heuristic title scoring
        self.brands = [
            "xiaomi",
            "samsung",
            "apple",
            "sony",
            "lg",
            "pixel",
            "oneplus",
            "realme",
            "oppo",
            "lenovo",
            "hp",
            "asus",
            "acer",
            "dell",
            "msi",
            "logitech",
            "razer",
            "corsair",
            "nintendo",
            "playstation",
            "xbox",
            "sega",
            "philips",
            "bosch",
            "balay",
            "teka",
            "rowenta",
            "cecotec",
            "dyson",
            "irobot",
            "nike",
            "adidas",
            "puma",
            "reebok",
            "vans",
            "converse",
            "levis",
            "lego",
            "playmobil",
            "barbie",
            "funko",
            "garmin",
            "polar",
            "suunto",
        ]

    def extract_urls(self, text: str) -> List[str]:
        """Extracts all URLs from text."""
        url_pattern = re.compile(r"(https?://[^\s)\]]+)")
        return url_pattern.findall(text)

    def extract_clean_url(self, text: str) -> Optional[str]:
        """
        Extracts the main deal URL.
        Prioritizes non-image URLs and known shops.
        Also prioritizes links marked with "Enlace" or similar.
        """
        # First, check for explicit link marker
        marker_pattern = re.compile(r"(?:Enlace|Link|Ir a|Ver chollo)[:\s\u2063]*(https?://[^\s)\]]+)", re.IGNORECASE)
        match = marker_pattern.search(text)
        if match:
            return self._clean_url(match.group(1))

        urls = self.extract_urls(text)
        candidates = []

        for url in urls:
            cleaned = self._clean_url(url)
            # Skip images
            path = urlparse(cleaned).path.lower()
            if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                continue
            candidates.append(cleaned)

        if not candidates:
            return None

        # Prioritize known shops
        for url in candidates:
            domain = urlparse(url).netloc.lower()
            if any(key in domain for key in self.shop_map.keys()):
                return url

        # Return first candidate if no known shop found
        return candidates[0]

    def _clean_url(self, url: str) -> str:
        """Removes common tracking parameters and shortens Amazon links."""
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            blocklist = ["utm_source", "utm_medium", "utm_campaign", "ref", "tag", "ref_"]

            new_query = {k: v for k, v in query_params.items() if k not in blocklist and not k.startswith("utm_")}

            if "amazon" in parsed.netloc or "amzn" in parsed.netloc:
                match = re.search(r"/dp/(\w+)", parsed.path)
                if match:
                    new_path = f"/dp/{match.group(1)}"
                    return urlunparse((parsed.scheme, parsed.netloc, new_path, "", "", ""))

                match = re.search(r"/gp/product/(\w+)", parsed.path)
                if match:
                    new_path = f"/dp/{match.group(1)}"
                    return urlunparse((parsed.scheme, parsed.netloc, new_path, "", "", ""))

            cleaned_query_str = urlencode(new_query, doseq=True)
            return urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.params, cleaned_query_str, parsed.fragment)
            )
        except Exception:
            return url

    def extract_prices(self, text: str) -> dict:
        """
        Extracts sale price and 'before' price.
        """
        price_before = None

        # Improved regex for Price Before (handling + sign, etc)
        # Matches: "PVP: +649€", "Antes: 100", "Original: $50", "Was: 200", "Previous: 200"
        before_patterns = [
            r"(?:Antes|PVP(?!\s*ahora)|Original|Previous|RRP|Valorado en|Was|Precio anterior|Precio habitual)[:\s]*[~+]?([\d.,]+[\s]*(?:€|EUR|USD|\$))",
            r"(?:Antes|PVP(?!\s*ahora)|Original|Previous|RRP|Valorado en|Was|Precio anterior|Precio habitual)[:\s]*[~+]?((?:€|EUR|USD|\$)[\s]*[\d.,]+)",
            r"PVtR[\s:*+]*([\d.,]+)",
            # Pattern for struck-through prices could be hard in plain text, but sometimes explicit
        ]

        for pat in before_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                p = Price.fromstring(match.group(1))
                if p.amount:
                    price_before = p.amount
                    break

        # Sale Price
        sale_patterns = [
            r"(?:PVP ahora|Nuevo precio|Oferta|Precio|Ahora|Solo|Bajada a|Por)[\s:*]*([\d.,]+[\s]*(?:€|EUR|USD|\$))",
            r"(?:Oferta|Precio|Ahora|Solo|Bajada a)[\s:*]*((?:€|EUR|USD|\$)[\s]*[\d.,]+)",
        ]

        price_sale = None

        for pat in sale_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                p = Price.fromstring(match.group(1))
                if p.amount:
                    price_sale = p.amount
                    break

        if not price_sale:
            # Enhanced fallback: Find all prices
            price_regex = re.compile(r"(?:\b[\d.,]+\s*(?:€|EUR|USD|\$))|(?:(?:€|EUR|USD|\$)\s*[\d.,]+)", re.IGNORECASE)
            matches = price_regex.findall(text)

            candidates = []
            for m in matches:
                p = Price.fromstring(m)
                if p.amount:
                    if p.amount > 10000 and "202" in m:  # Year detection heuristic
                        continue
                    candidates.append(p.amount)

            if price_before and candidates:
                # If we have a BEFORE price, the SALE price should be different and typically lower
                # Heuristic: Find candidate < price_before
                potential_sales = [c for c in candidates if c < price_before]
                if potential_sales:
                    price_sale = min(potential_sales)  # Assume best deal
                else:
                    # Maybe the before price was misidentified or price increased?
                    # Try finding any price != before
                    diff_candidates = [c for c in candidates if abs(c - price_before) > Decimal("0.01")]
                    if diff_candidates:
                        price_sale = min(diff_candidates)

            elif candidates:
                # Use the lowest price found as sale price
                price_sale = min(candidates)

        return {"sale": price_sale, "before": price_before}

    def extract_shop(self, text: str, url: str) -> Optional[str]:
        """Determines the shop from hashtags or URL domain."""
        text_lower = text.lower()

        for keyword, shop_name in self.shop_map.items():
            if f"#{keyword}" in text_lower:
                return shop_name

        if url:
            domain = urlparse(url).netloc.lower()
            for keyword, shop_name in self.shop_map.items():
                if keyword in domain:
                    return shop_name

        return None

    def extract_source(self, text: str) -> Optional[str]:
        """Extracts source from text."""
        # 1. Look for explicit Visto en
        pattern = re.compile(r"(?:Visto en|Fuente|Via|By)[:\s]+(@\w+)", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            return match.group(1)

        # 2. Look for footer signatures
        # e.g. "♦️ @canaldescuentos / @canalninja"
        # We find lines that contain @mentions and seem to be signatures (end of msg)
        lines = text.strip().split("\n")
        if not lines:
            return None

        # Check last few lines
        for line in reversed(lines[-3:]):
            if "@" in line:
                # Extract all mentions
                mentions = re.findall(r"(@\w+)", line)
                if mentions:
                    return " / ".join(mentions)

        return None

    def extract_title_heuristic(self, text: str, url: str) -> str:
        """
        Extracts a clean title using heuristics and brand detection.
        Scores each line to find the best candidate.
        """
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            if url:
                return url
            return "No Title"

        noise_words = [
            "CHOLLAZO",
            "CHOLLO",
            "OFERTA",
            "PRECIO",
            "MINIMO",
            "HISTORICO",
            "BOMBAZO",
            "ERROR",
            "GRATIS",
            "MÁS",
            "PRECIAZO",
            "SUPER",
            "REBAJA",
            "DESCUENTO",
            "LIQUIDACION",
        ]

        best_candidate = ""
        best_score = -100

        # Limit to first 6 lines as titles are rarely below that
        for i, line in enumerate(lines[:6]):
            score = 0

            # --- Clean candidate ---
            # Remove URLs
            candidate = re.sub(r"https?://\S+", "", line)
            # Remove [text] marks
            candidate = re.sub(r"\[.*?\]", "", candidate)
            # Remove Telegram markdown (**bold**, __italic__, `code`)
            candidate = re.sub(r"[*_`]{1,3}", "", candidate)
            # Remove hashtags
            candidate = re.sub(r"#\w+", "", candidate)
            # Remove leading non-word chars
            candidate = re.sub(r"^[^\w\d]+", "", candidate)

            # Clean noise words (case insensitive)
            for w in noise_words:
                candidate = re.sub(rf"(?i)\b{w}\b", "", candidate)  # whole words: "superautomática" keeps its "super"

            candidate = re.sub(r"^[^\w\d]+", "", candidate)
            candidate = candidate.strip()
            if not candidate:
                continue

            # --- Scoring Logic ---

            # 1. Position Score (Earlier is better)
            score += 10 - i * 2

            # Promo lines are not the product ("Código 14% en tu primer pedido", "Cupón: ...")
            if PROMO_LINE.match(candidate):
                score -= 25

            # 2. Brand Detection (Huge Boost)
            line_lower = candidate.lower()
            for brand in self.brands:
                if brand in line_lower:
                    score += 20
                    break

            # 3. Model Lookalike (Alphanumeric mixed)
            # e.g. "iPhone 15", "S24 Ultra", "RTX 4090"
            if re.search(r"[a-zA-Z]+.*?\d+|\d+.*?[a-zA-Z]+", candidate):
                score += 5

            # 4. Length Heuristics
            # Too short (< 5) is bad. Too long (> 100) is usually description.
            if len(candidate) < 5:
                score -= 10
            elif 10 <= len(candidate) <= 60:
                score += 5
            elif len(candidate) > 100:
                score -= 5

            # 5. Sentence Structure (Bad for title)
            # If it has "?", or starts with verb-ish things "Mira", "Pues", "Tiene"
            if "?" in candidate or "!" in candidate:
                score -= 5

            # "Mira este...", "Pues..."
            if re.match(r"^(Mira|Pues|Ojo|Atencion|Increible|Vaya)", candidate, re.IGNORECASE):
                # Try to strip it
                candidate = re.sub(
                    r"^(Mira|Pues|Ojo|Atencion|Increible|Vaya)\s+(este|esta|ese|esa)?\s*",
                    "",
                    candidate,
                    flags=re.IGNORECASE,
                )
                # If we stripped it and it still looks good, maybe it's okay, but usually penalty
                score -= 2

            # 6. Price in title (Bad or Good? Usually bad if it's ONLY price)
            if re.search(r"\d+\s*(?:€|eur)", candidate, re.IGNORECASE):
                # If it's just price, huge penalty
                if len(candidate) < 15:
                    score -= 20
                else:
                    # Strip price from title
                    candidate = re.sub(r"[\d.,]+\s*(?:€|EUR|USD|\$)", "", candidate, flags=re.IGNORECASE).strip()

            # Update Best
            if score > best_score:
                best_score = score
                best_candidate = candidate

        if best_candidate and len(clean_title(best_candidate)) > 3:
            return clean_title(best_candidate)

        # Fallback: Just return cleaned first line
        fallback = lines[0]
        fallback = re.sub(r"https?://\S+", "", fallback).strip()
        return clean_title(fallback)[:100] or fallback[:100]

    # Hashtags that some channels put on every post (#moda, #electronica...): the most reliable signal
    HASHTAG_CATEGORIES = {
        "electronica": CategoryEnum.TECNOLOGIA,
        "tecnologia": CategoryEnum.TECNOLOGIA,
        "informatica": CategoryEnum.TECNOLOGIA,
        "moviles": CategoryEnum.TECNOLOGIA,
        "videojuegos": CategoryEnum.VIDEOJUEGOS,
        "gaming": CategoryEnum.VIDEOJUEGOS,
        "hogar": CategoryEnum.HOGAR,
        "casa": CategoryEnum.HOGAR,
        "cocina": CategoryEnum.COCINA,
        "bricolaje": CategoryEnum.BRICOLAJE,
        "jardin": CategoryEnum.BRICOLAJE,
        "herramientas": CategoryEnum.BRICOLAJE,
        "moda": CategoryEnum.MODA,
        "ropa": CategoryEnum.MODA,
        "calzado": CategoryEnum.MODA,
        "belleza": CategoryEnum.BELLEZA,
        "salud": CategoryEnum.BELLEZA,
        "cuidadopersonal": CategoryEnum.BELLEZA,
        "deporte": CategoryEnum.DEPORTE,
        "deportes": CategoryEnum.DEPORTE,
        "juguetes": CategoryEnum.JUGUETES,
        "bebe": CategoryEnum.JUGUETES,
        "alimentacion": CategoryEnum.ALIMENTACION,
        "supermercado": CategoryEnum.ALIMENTACION,
        "mascotas": CategoryEnum.MASCOTAS,
        "libros": CategoryEnum.LIBROS,
        "oficina": CategoryEnum.OFICINA,
        "papeleria": CategoryEnum.OFICINA,
        "motor": CategoryEnum.MOTOR,
        "coche": CategoryEnum.MOTOR,
    }

    @staticmethod
    def _plain(text: str) -> str:
        text = text.lower()
        for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u")):
            text = text.replace(a, b)
        return text

    def _keyword_category(self, text: str) -> CategoryEnum | None:
        for category, keywords in self.categories_keywords.items():
            for k in keywords:
                # Whole words (plural allowed): "crema" must not match "cremallera", nor "tinto" "distinto"
                if re.search(r"(?<!\w)" + re.escape(self._plain(k)) + r"(?:s|es)?(?!\w)", text):
                    return category
        return None

    def determine_category_heuristic(self, text: str, title: str) -> CategoryEnum:
        plain_text = self._plain(text)
        for tag in re.findall(r"#(\w+)", plain_text):
            if tag in self.HASHTAG_CATEGORIES:
                return self.HASHTAG_CATEGORIES[tag]
        # The title says what the product is; the rest of the message has slogans and footers
        return self._keyword_category(self._plain(title)) or self._keyword_category(plain_text) or CategoryEnum.OTROS

    # Words that move the score a little (the discount is what matters)
    SCORE_KEYWORDS = {
        "minimo historico": 10,
        "error de precio": 15,
        "chollazo": 3,
        "liquidacion": 5,
        "reacondicionado": -10,
        "usado": -10,
        "segunda mano": -10,
    }

    def calculate_score(
        self,
        price_sale: Optional[Decimal],
        price_before: Optional[Decimal],
        text: str,
        discount_percentage: Optional[int] = None,
    ) -> int:
        """
        'chollo_score' from 0 to 100. With a known discount, mostly the discount (50 % -> 65, 70 % -> 83);
        without one, 35. Keywords add or subtract a little. A freebie (explicit 0 €) gets 60, not 100: "free with
        a trial" is common and not the best deal of the day.
        """
        if discount_percentage is None and price_sale and price_before and price_before > price_sale:
            discount_percentage = int((price_before - price_sale) / price_before * 100)
        if discount_percentage is None:
            match = re.search(r"(\d{1,2})\s*%\s*(?:dto|descuento|off|menos)", text, re.IGNORECASE)
            discount_percentage = int(match.group(1)) if match else None

        if price_sale is not None and price_sale == 0:
            score = 60.0
        elif discount_percentage:
            score = 20 + 0.9 * min(discount_percentage, 95)
        else:
            score = 35.0

        plain = self._plain(text)
        score += sum(bonus for kw, bonus in self.SCORE_KEYWORDS.items() if kw in plain)
        return max(0, min(100, round(score)))

    @property
    def llm_enabled(self) -> bool:
        return bool(getattr(self.llm_provider, "enabled", True))

    @staticmethod
    def needs_llm(result: dict) -> bool:
        """Whether the rules alone left doubts worth paying an LLM call for."""
        title = result.get("title") or ""
        return (
            result.get("price_sale") is None
            or result.get("category") in (CategoryEnum.OTROS, CategoryEnum.OTROS.value)
            or not 8 <= len(title) <= 120
            or is_generic_title(title)
        )

    def parse(self, text: str, use_llm: bool = True) -> dict:
        """
        Main parse method.
        With use_llm, asks the LLM too and merges with the rules; without it, only the rules (free).
        """
        # Basic extraction
        url = self.extract_clean_url(text)
        heuristic_prices_data = self.extract_prices(text)
        shop = self.extract_shop(text, url)
        source = self.extract_source(text)

        # Try LLM
        try:
            llm_data = self.llm_provider.parse_deal(text) if use_llm else {}
        except Exception as e:
            logger.error(f"LLM Provider failed unexpectedly: {e}")
            llm_data = {}

        # Merge Price Logic
        # Heuristics
        h_price_sale = heuristic_prices_data.get("sale")
        h_price_before = heuristic_prices_data.get("before")

        # LLM
        l_price_sale = llm_data.get("price_sale")
        l_price_before = llm_data.get("price_before")
        l_discount = llm_data.get("discount_percentage")

        # Decision (Prioritize LLM if valid number). None means "no price found", not free.
        price_sale = h_price_sale
        if isinstance(l_price_sale, (int, float)) and not isinstance(l_price_sale, bool):
            price_sale = Decimal(str(l_price_sale))
        if price_sale is None and re.search(r"\bgratis\b", text, re.IGNORECASE):
            price_sale = Decimal(0)

        price_before = h_price_before
        if isinstance(l_price_before, (int, float)) and not isinstance(l_price_before, bool):
            price_before = Decimal(str(l_price_before))

        # Discount logic
        discount_percentage = l_discount if isinstance(l_discount, int) else None
        if discount_percentage is None:
            # Calculate if we have both prices
            if price_sale and price_before and price_before > price_sale:
                discount_percentage = int(((price_before - price_sale) / price_before) * 100)

        # Decide Title
        if llm_data.get("title") and llm_data.get("confidence", 0) > 0.7:
            title = clean_title(llm_data["title"]) or llm_data["title"]
        else:
            title = self.extract_title_heuristic(text, url)

        # Decide Category
        if llm_data.get("category") and llm_data.get("category") != "otros":
            category = llm_data["category"]
        else:
            category = self.determine_category_heuristic(text, title)

        chollo_score = self.calculate_score(price_sale, price_before, text, discount_percentage)

        return {
            "title": title,
            "description": text,
            "url": url,
            "price_sale": price_sale,
            "price_before": price_before,
            "category": category,
            "shop": shop,
            "source": source,
            "raw_text": text,
            "chollo_score": chollo_score,
            "discount_percentage": discount_percentage,
        }
