import os
import logging
import json
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

import google.generativeai as genai
from src.domain.enums import CategoryEnum

logger = logging.getLogger(__name__)

class LLMProvider(ABC):
    @abstractmethod
    def parse_deal(self, text: str) -> Dict[str, Any]:
        """
        Parses deal text to extract structured information.
        Expected return dict keys: 'title', 'category', 'confidence', 'product_name'
        """
        pass

class GeminiLLMProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not found. LLM features will be disabled.")
            self.model = None
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro')

    def parse_deal(self, text: str) -> Dict[str, Any]:
        if not self.model:
            return {}

        prompt = f"""
        Analyze the following text which is a deal/offer from a Telegram channel.
        Extract the following information in JSON format:
        1. "title": A clean, descriptive title of the product (e.g. "Samsung Galaxy S24 Ultra 512GB"). Remove any "CHOLLO", "OFERTA", emojis, or prices.
        2. "category": The most fitting category from this list: [{', '.join([c.value for c in CategoryEnum])}]. If unsure, use "otros".
        3. "confidence": A score from 0.0 to 1.0 indicating how confident you are that this is a legit product deal and you identified it correctly.
        4. "product_name": A short name of the product (e.g. "Samsung S24 Ultra").

        Text:
        {text}

        JSON Output:
        """

        try:
            response = self.model.generate_content(prompt)
            # Cleanup Markdown code blocks if present
            content = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)
            
            # Validate category
            if 'category' in data:
                try:
                    # Normalize to ensure it matches enum values
                    cat_val = data['category'].lower()
                    # Check if valid
                    valid_cats = {c.value for c in CategoryEnum}
                    if cat_val not in valid_cats:
                         data['category'] = "otros"
                except:
                     data['category'] = "otros"
            
            return data
        except Exception as e:
            logger.error(f"Error calling Gemini LLM: {e}")
            return {}
