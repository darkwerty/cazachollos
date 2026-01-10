import unittest
from decimal import Decimal
from src.services.parser import DealParser
from src.domain.enums import CategoryEnum

class TestParserImprovements(unittest.TestCase):
    def setUp(self):
        self.parser = DealParser()

    def test_extract_title_complex(self):
        text = """
        ¡Mira esto!
        Pues mira este XIAOMI Watch S4 Smartwatch que está de oferta
        https://amzn.to/3XyZabc
        PVP: 150€
        Oferta: 99€
        """
        # The parser should identify the second line as the title because it contains a brand (Xiaomi) and reasonable length.
        # It should also try to strip "Pues mira este..."
        title = self.parser.extract_title_heuristic(text, "https://amzn.to/3XyZabc")
        self.assertIn("XIAOMI Watch S4 Smartwatch", title)
        self.assertNotIn("https", title)

    def test_extract_title_simple(self):
        text = "SAMSUNG Galaxy S24 Ultra 512GB"
        title = self.parser.extract_title_heuristic(text, "")
        self.assertEqual(title, "SAMSUNG Galaxy S24 Ultra 512GB")

    def test_extract_title_with_noise(self):
        text = """
        CHOLLAZO BOMBAZO
        Apple Macbook Air M2
        Solo 999€
        """
        title = self.parser.extract_title_heuristic(text, "")
        self.assertIn("Apple Macbook Air M2", title)
        self.assertNotIn("CHOLLAZO", title)

    def test_calculate_score_discount(self):
        # 50% discount
        score = self.parser.calculate_score(Decimal(50), Decimal(100), "text")
        # Base 50 + 50 (discount) = 100
        self.assertEqual(score, 100)
        
        # 20% discount
        score = self.parser.calculate_score(Decimal(80), Decimal(100), "text")
        # Base 50 + 20 = 70
        self.assertEqual(score, 70)

    def test_calculate_score_keywords(self):
        # No discount info, but "Error de precio"
        score = self.parser.calculate_score(Decimal(100), None, "Esto es un Error de precio brutal")
        # Base 50 + 30 (Error de precio) + 5 (brutal) = 85
        self.assertEqual(score, 85)

    def test_calculate_score_free(self):
        score = self.parser.calculate_score(Decimal(0), Decimal(10), "Gratis")
        self.assertEqual(score, 100)

if __name__ == '__main__':
    unittest.main()
