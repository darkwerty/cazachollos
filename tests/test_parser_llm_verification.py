
import unittest
from unittest.mock import MagicMock
from decimal import Decimal
from src.services.parser import DealParser
from src.services.llm_services import LLMProvider

class TestLLMProvider(LLMProvider):
    def parse_deal(self, text: str):
        # Mock response
        if "CHOLLAZO" in text:
             return {
                 "title": "Mock Title",
                 "category": "tecnologia",
                 "confidence": 0.9,
                 "product_name": "Mock Product",
                 "price_sale": 99.99,
                 "price_before": 200.00,
                 "discount_percentage": 50,
                 "one_line_summary": "Great deal"
             }
        return {}

class TestParserVerification(unittest.TestCase):
    def setUp(self):
        self.mock_llm = TestLLMProvider()
        self.parser = DealParser(llm_provider=self.mock_llm)

    def test_llm_price_extraction(self):
        text = "CHOLLAZO: Samsung TV a solo 99.99€ (Antes 200€)!"
        result = self.parser.parse(text)
        
        self.assertEqual(result['price_sale'], Decimal('99.99'))
        self.assertEqual(result['price_before'], Decimal('200.00'))
        self.assertEqual(result['discount_percentage'], 50)
        self.assertTrue(result['chollo_score'] > 50) # Should be boosted by discount

    def test_heuristic_fallback(self):
        # Text without "CHOLLAZO" returns empty dict from mock LLM
        text = "Oferta: 50€ (PVP: 100€)" 
        
        # We need a new parser instance that uses real regex logic but empty LLM
        # Default DealParser uses GeminiLLMProvider which we don't want to call for real here without key
        # So we use a Mock that returns empty
        mock_empty = MagicMock()
        mock_empty.parse_deal.return_value = {}
        
        parser = DealParser(llm_provider=mock_empty)
        result = parser.parse(text)
        
        self.assertEqual(result['price_sale'], Decimal('50'))
        self.assertEqual(result['price_before'], Decimal('100')) 
        # Discount should be calculated heuristically: (100-50)/100 = 50%
        self.assertEqual(result['discount_percentage'], 50)

if __name__ == '__main__':
    unittest.main()
