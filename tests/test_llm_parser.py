import unittest
from unittest.mock import MagicMock
from decimal import Decimal
from src.services.parser import DealParser
from src.services.llm_services import LLMProvider
from src.domain.enums import CategoryEnum

class MockLLMProvider(LLMProvider):
    def parse_deal(self, text: str):
        # Mimic a successful LLM response
        if "Pixel" in text:
            return {
                "title": "Google Pixel 8 Pro",
                "category": "tecnologia",
                "confidence": 0.9,
                "product_name": "Pixel 8 Pro"
            }
        return {}

class TestLLMParser(unittest.TestCase):
    def setUp(self):
        self.llm_provider = MockLLMProvider()
        self.parser = DealParser(llm_provider=self.llm_provider)

    def test_parse_with_llm_success(self):
        text = "¡Ofertaza! Google Pixel 8 Pro por 800 euros"
        result = self.parser.parse(text)
        
        # Should use LLM title instead of heuristic
        self.assertEqual(result["title"], "Google Pixel 8 Pro")
        self.assertEqual(result["category"], CategoryEnum.TECNOLOGIA)
        self.assertEqual(result["price_sale"], Decimal("800"))

    def test_llm_fallback_to_heuristic(self):
        # LLM returns empty/low confidence (Mock returns empty for non-Pixel)
        text = "Sartén Tefal 24cm por 20€"
        result = self.parser.parse(text)
        
        # Heuristic should pick it up
        self.assertIn("Sartén Tefal", result["title"])
        self.assertEqual(result["category"], CategoryEnum.COCINA)

if __name__ == '__main__':
    unittest.main()
