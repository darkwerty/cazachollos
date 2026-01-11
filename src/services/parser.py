import re
import logging
from decimal import Decimal
from typing import Optional, List, Dict

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from price_parser import Price
from src.domain.enums import CategoryEnum
from src.services.llm_services import GeminiLLMProvider, LLMProvider

logger = logging.getLogger(__name__)

class DealParser:
    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider or GeminiLLMProvider()
        
        # Category keywords (expanded)
        self.categories_keywords = {
            CategoryEnum.TECNOLOGIA: [
                "movil", "iphone", "xiaomi", "samsung", "tv", "portatil", "laptop", 
                "ram", "ssd", "pixel", "tablet", "auriculares", "sony", "lg", "apple",
                "monitor", "pc", "ordenador", "consola", "ps5", "xbox", "nintendo"
            ],
            CategoryEnum.HOGAR: [
                "silla", "mesa", "sofa", "cama", "taladro", "mueble", "bricolaje",
                "herramienta", "jardin", "salon", "baño", "aspirador", "rowenta", "cecotec"
            ],
            CategoryEnum.COCINA: [
                "sarten", "olla", "freidora", "airfryer", "batidora", "cafetera",
                "cocina", "horno", "microondas", "lavavajillas"
            ],
            CategoryEnum.MODA: [
                "camiseta", "pantalon", "zapatos", "botas", "nike", "adidas", 
                "ropa", "abrigo", "zapatillas", "puma", "vans"
            ],
            CategoryEnum.DEPORTE: [
                "pesa", "bici", "gym", "proteina", "suplemento", "deporte", 
                "fitness", "running", "futbol", "baloncesto"
            ],
            CategoryEnum.JUGUETES: [
                "lego", "playmobil", "muñeca", "juguete", "juego", "infantil"
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
            "carrefour": "Carrefour",
            "lidl": "Lidl",
            "ebay": "eBay",
            "nike": "Nike",
            "adidas": "Adidas",
            "zalando": "Zalando",
            "shein": "Shein",
            "temu": "Temu"
        }

        # Common Brands for heuristic title scoring
        self.brands = [
            "xiaomi", "samsung", "apple", "sony", "lg", "pixel", "oneplus", "realme", "oppo",
            "lenovo", "hp", "asus", "acer", "dell", "msi", "logitech", "razer", "corsair",
            "nintendo", "playstation", "xbox", "sega",
            "philips", "bosch", "balay", "teka", "rowenta", "cecotec", "dyson", "irobot",
            "nike", "adidas", "puma", "reebok", "vans", "converse", "levis",
            "lego", "playmobil", "barbie", "funko",
            "garmin", "polar", "suunto"
        ]

    def extract_urls(self, text: str) -> List[str]:
        """Extracts all URLs from text."""
        url_pattern = re.compile(r'(https?://[^\s)\]]+)')
        return url_pattern.findall(text)

    def extract_clean_url(self, text: str) -> Optional[str]:
        """
        Extracts the main deal URL.
        Prioritizes non-image URLs and known shops.
        Also prioritizes links marked with "Enlace" or similar.
        """
        # First, check for explicit link marker
        marker_pattern = re.compile(r'(?:Enlace|Link|Ir a|Ver chollo)[:\s\u2063]*(https?://[^\s)\]]+)', re.IGNORECASE)
        match = marker_pattern.search(text)
        if match:
             return self._clean_url(match.group(1))

        urls = self.extract_urls(text)
        candidates = []
        
        for url in urls:
            cleaned = self._clean_url(url)
            # Skip images
            path = urlparse(cleaned).path.lower()
            if path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
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
            
            blocklist = ['utm_source', 'utm_medium', 'utm_campaign', 'ref', 'tag', 'ref_']
            
            new_query = {k: v for k, v in query_params.items() if k not in blocklist}
            
            if "amazon" in parsed.netloc or "amzn" in parsed.netloc:
                 match = re.search(r'/dp/(\w+)', parsed.path)
                 if match:
                     new_path = f"/dp/{match.group(1)}"
                     return urlunparse((parsed.scheme, parsed.netloc, new_path, '', '', ''))
                 
                 match = re.search(r'/gp/product/(\w+)', parsed.path)
                 if match:
                     new_path = f"/dp/{match.group(1)}"
                     return urlunparse((parsed.scheme, parsed.netloc, new_path, '', '', ''))

            cleaned_query_str = urlencode(new_query, doseq=True)
            return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, cleaned_query_str, parsed.fragment))
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
            r'(?:Antes|PVP|Original|Previous|RRP|Valorado en|Was|Ojo)[:\s]*[~+]?([\d.,]+[\s]*(?:€|EUR|USD|\$))',
            r'(?:Antes|PVP|Original|Previous|RRP|Valorado en|Was|Ojo)[:\s]*[~+]?((?:€|EUR|USD|\$)[\s]*[\d.,]+)',
            r'PVtR[\s:*+]*([\d.,]+)', 
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
            r'(?:Oferta|Precio|Ahora|Solo|Bajada a)[\s:*]*([\d.,]+[\s]*(?:€|EUR|USD|\$))',
            r'(?:Oferta|Precio|Ahora|Solo|Bajada a)[\s:*]*((?:€|EUR|USD|\$)[\s]*[\d.,]+)',
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
            price_regex = re.compile(r'(?:\b[\d.,]+\s*(?:€|EUR|USD|\$))|(?:(?:€|EUR|USD|\$)\s*[\d.,]+)', re.IGNORECASE)
            matches = price_regex.findall(text)
            
            candidates = []
            for m in matches:
                p = Price.fromstring(m)
                if p.amount:
                    if p.amount > 10000 and "202" in m: continue # Year detection heuristic
                    candidates.append(p.amount)
            
            if price_before and candidates:
                # If we have a BEFORE price, the SALE price should be different and typically lower
                # Heuristic: Find candidate < price_before
                potential_sales = [c for c in candidates if c < price_before]
                if potential_sales:
                     price_sale = min(potential_sales) # Assume best deal
                else:
                     # Maybe the before price was misidentified or price increased?
                     # Try finding any price != before
                     diff_candidates = [c for c in candidates if abs(c - price_before) > Decimal('0.01')]
                     if diff_candidates:
                         price_sale = min(diff_candidates)

            elif candidates:
                # Use the lowest price found as sale price
                price_sale = min(candidates)

        return {
            "sale": price_sale,
            "before": price_before
        }

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
        pattern = re.compile(r'(?:Visto en|Fuente|Via|By)[:\s]+(@\w+)', re.IGNORECASE)
        match = pattern.search(text)
        if match:
            return match.group(1)
            
        # 2. Look for footer signatures
        # e.g. "♦️ @canaldescuentos / @canalninja"
        # We find lines that contain @mentions and seem to be signatures (end of msg)
        lines = text.strip().split('\n')
        if not lines:
            return None
            
        # Check last few lines
        for line in reversed(lines[-3:]):
            if '@' in line:
                # Extract all mentions
                mentions = re.findall(r'(@\w+)', line)
                if mentions:
                    return " / ".join(mentions)
                    
        return None

    def extract_title_heuristic(self, text: str, url: str) -> str:
        """
        Extracts a clean title using heuristics and brand detection.
        Scores each line to find the best candidate.
        """
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if not lines:
            if url: return url
            return "No Title"
            
        noise_words = [
            "CHOLLO", "OFERTA", "PRECIO", "MINIMO", "HISTORICO", "BOMBAZO", "ERROR", 
            "GRATIS", "MÁS", "PRECIAZO", "SUPER", "REBAJA", "DESCUENTO", "LIQUIDACION"
        ]
        
        best_candidate = ""
        best_score = -100
        
        # Limit to first 6 lines as titles are rarely below that
        for i, line in enumerate(lines[:6]):
            score = 0
            original_line = line
            
            # --- Clean candidate ---
            # Remove URLs
            candidate = re.sub(r'https?://\S+', '', line)
            # Remove [text] marks
            candidate = re.sub(r'\[.*?\]', '', candidate)
            # Remove hashtags
            candidate = re.sub(r'#\w+', '', candidate)
            # Remove leading non-word chars
            candidate = re.sub(r'^[^\w\d]+', '', candidate)
            
            # Clean noise words (case insensitive)
            for w in noise_words:
                 candidate = re.sub(f'(?i){w}', '', candidate)
            
            candidate = candidate.strip()
            if not candidate:
                continue

            # --- Scoring Logic ---
            
            # 1. Position Score (Earlier is better)
            score += (10 - i * 2) 
            
            # 2. Brand Detection (Huge Boost)
            line_lower = candidate.lower()
            found_brand = False
            for brand in self.brands:
                if brand in line_lower:
                    score += 20
                    found_brand = True
                    break
            
            # 3. Model Lookalike (Alphanumeric mixed)
            # e.g. "iPhone 15", "S24 Ultra", "RTX 4090"
            if re.search(r'[a-zA-Z]+.*?\d+|\d+.*?[a-zA-Z]+', candidate):
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
            if re.match(r'^(Mira|Pues|Ojo|Atencion|Increible|Vaya)', candidate, re.IGNORECASE):
                # Try to strip it
                candidate = re.sub(r'^(Mira|Pues|Ojo|Atencion|Increible|Vaya)\s+(este|esta|ese|esa)?\s*', '', candidate, flags=re.IGNORECASE)
                # If we stripped it and it still looks good, maybe it's okay, but usually penalty
                score -= 2

            # 6. Price in title (Bad or Good? Usually bad if it's ONLY price)
            if re.search(r'\d+\s*(?:€|eur)', candidate, re.IGNORECASE):
                # If it's just price, huge penalty
                if len(candidate) < 15:
                    score -= 20
                else:
                    # Strip price from title
                    candidate = re.sub(r'[\d.,]+\s*(?:€|EUR|USD|\$)', '', candidate, flags=re.IGNORECASE).strip()

            # Update Best
            if score > best_score:
                best_score = score
                best_candidate = candidate
        
        if best_candidate and len(best_candidate) > 3:
            return best_candidate
            
        # Fallback: Just return cleaned first line
        fallback = lines[0]
        fallback = re.sub(r'https?://\S+', '', fallback).strip()
        return fallback[:100]

    def determine_category_heuristic(self, text: str, title: str) -> CategoryEnum:
        combined = (text + " " + title).lower()
        
        replacements = (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"))
        for a, b in replacements:
            combined = combined.replace(a, b)
            
        for category, keywords in self.categories_keywords.items():
            for k in keywords:
                # If keyword is short (< 4 chars), require word boundary
                if len(k) < 4:
                    if re.search(r'\b' + re.escape(k) + r'\b', combined):
                        return category
                else:
                    if k in combined:
                        return category
        return CategoryEnum.OTROS

    def calculate_score(self, price_sale: Decimal, price_before: Optional[Decimal], text: str) -> int:
        """
        Calculates a 'chollo_score' from 0 to 100 based on discount and keywords.
        """
        score = 50 # Base score
        
        # 1. Discount Bonus
        if price_sale and price_before and price_before > price_sale:
            try:
                # Calculate percentage discount
                discount_pct = (price_before - price_sale) / price_before
                # Add points: e.g. 50% off -> +50 points
                score += int(discount_pct * 100)
            except:
                pass
        
        # 2. Implied Discount (if no before price found)
        elif not price_before:
             # Look for "50% descuento" in text
             match = re.search(r'(\d+)%\s*(?:dto|descuento|off)', text, re.IGNORECASE)
             if match:
                 try:
                     pct = int(match.group(1))
                     score += pct
                 except: pass

        # 3. Freebie Bonus
        if price_sale == 0:
            return 100
        
        # 4. Keyword Bonus
        text_lower = text.lower()
        keywords = {
            "mínimo histórico": 20,
            "minimo historico": 20,
            "error de precio": 30,
            "chollazo": 10,
            "brutal": 5,
            "chollo": 5,
            "liquidación": 10,
            "liquidacion": 10,
            "reacondicionado": -10,
            "usado": -10
        }
        
        for kw, bonus in keywords.items():
            if kw in text_lower:
                score += bonus
                
        # Cap score
        return max(0, min(100, score))

    def parse(self, text: str) -> dict:
        """
        Main parse method. 
        Attempts to use LLM first, merges with heuristics.
        """
        # Basic extraction
        url = self.extract_clean_url(text)
        prices_data = self.extract_prices(text)
        shop = self.extract_shop(text, url)
        source = self.extract_source(text)
        
        price_sale = prices_data['sale'] if prices_data['sale'] is not None else Decimal(0)
        price_before = prices_data['before']
        
        # Try LLM
        try:
            llm_data = self.llm_provider.parse_deal(text)
        except Exception as e:
            logger.error(f"LLM Provider failed unexpectedly: {e}")
            llm_data = {}
        
        # Decide Title
        if llm_data.get('title') and llm_data.get('confidence', 0) > 0.7:
             title = llm_data['title']
        else:
             title = self.extract_title_heuristic(text, url)
             
        # Decide Category
        if llm_data.get('category') and llm_data.get('category') != 'otros':
             category = llm_data['category']
        else:
             category = self.determine_category_heuristic(text, title)
            
        chollo_score = self.calculate_score(price_sale, price_before, text)
        
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
            "chollo_score": chollo_score
        }

