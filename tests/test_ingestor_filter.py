import os
import pytest
from unittest.mock import Mock
from src.services.ingestor import IngestorService

# Mock TelegramService since we don't need real connection for this test
class MockTelegramService:
    def __init__(self):
        self.client = Mock()

@pytest.fixture
def mock_telegram():
    return MockTelegramService()

def test_load_allowed_groups_empty(mock_telegram):
    """Test loading empty allowed groups returns empty set."""
    os.environ["TELEGRAM_ALLOWED_GROUPS"] = ""
    ingestor = IngestorService(mock_telegram)
    assert ingestor.allowed_groups == set()
    assert ingestor._is_allowed_source(123, "test") == True

def test_load_allowed_groups_with_ids(mock_telegram):
    """Test loading allowed groups with IDs."""
    os.environ["TELEGRAM_ALLOWED_GROUPS"] = "123, 456"
    ingestor = IngestorService(mock_telegram)
    assert 123 in ingestor.allowed_groups
    assert 456 in ingestor.allowed_groups
    assert ingestor._is_allowed_source(123, "any") == True
    assert ingestor._is_allowed_source(789, "any") == False

def test_load_allowed_groups_with_titles(mock_telegram):
    """Test loading allowed groups with titles."""
    os.environ["TELEGRAM_ALLOWED_GROUPS"] = "MyGroup, AnotherGroup"
    ingestor = IngestorService(mock_telegram)
    assert "MyGroup" in ingestor.allowed_groups
    assert "AnotherGroup" in ingestor.allowed_groups
    assert ingestor._is_allowed_source(999, "MyGroup") == True
    assert ingestor._is_allowed_source(999, "Unknown") == False

def test_load_allowed_groups_mixed(mock_telegram):
    """Test loading mixed IDs and titles."""
    os.environ["TELEGRAM_ALLOWED_GROUPS"] = "123, MyGroup"
    ingestor = IngestorService(mock_telegram)
    assert 123 in ingestor.allowed_groups
    assert "MyGroup" in ingestor.allowed_groups
    assert ingestor._is_allowed_source(123, "Unknown") == True
    assert ingestor._is_allowed_source(999, "MyGroup") == True
    assert ingestor._is_allowed_source(999, "Unknown") == False
