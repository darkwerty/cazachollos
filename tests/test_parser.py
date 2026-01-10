import unittest
from decimal import Decimal
from src.domain.enums import CategoryEnum
from src.services.parser import DealParser

class TestDealParser(unittest.TestCase):
    def setUp(self):
        self.parser = DealParser()

    def test_extract_clean_url(self):
        text = "Check this out https://www.amazon.es/dp/B08H93ZRK9?ref=foo&utm_source=bar"
        expected = "https://www.amazon.es/dp/B08H93ZRK9"
        self.assertEqual(self.parser.extract_clean_url(text), expected)

    def test_extract_prices(self):
        text = "Price is 19.99€ only!"
        # New API returns dict
        self.assertEqual(self.parser.extract_prices(text)['sale'], Decimal("19.99"))
        
        text2 = "Oferta: 1.200,50 EUR"
        self.assertEqual(self.parser.extract_prices(text2)['sale'], Decimal("1200.50"))

    def test_determine_category(self):
        # Now requires title arg
        self.assertEqual(self.parser.determine_category_heuristic("Nuevo iPhone 15", "iPhone 15"), CategoryEnum.TECNOLOGIA)
        self.assertEqual(self.parser.determine_category_heuristic("Sartén antiadherente", "Sarten"), CategoryEnum.COCINA)
        self.assertEqual(self.parser.determine_category_heuristic("Algo desconocido", "Nada"), CategoryEnum.OTROS)

    def test_parse_full(self):
        text = "¡Chollazo! Xiaomi TV P1 por 200€\nhttps://example.com/tv"
        result = self.parser.parse(text)
        # Title cleaner might strip "¡Chollazo!" and "por 200€"
        # "Xiaomi TV P1" is the expected clean title
        self.assertIn("Xiaomi TV P1", result["title"])
        self.assertEqual(result["price_sale"], Decimal("200"))
        self.assertEqual(result["category"], CategoryEnum.TECNOLOGIA)

if __name__ == '__main__':
    unittest.main()
