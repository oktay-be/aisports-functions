"""
Unit tests for article_processor_function/embedding_service.py

Tests the embedding service text preparation logic.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
import sys

# Mock pydantic before importing (needed by models.py)
mock_pydantic = MagicMock()
mock_pydantic.BaseModel = MagicMock
mock_pydantic.Field = MagicMock(return_value=None)
sys.modules['pydantic'] = mock_pydantic

# Mock Google Cloud modules before importing
mock_storage = MagicMock()
sys.modules['google.cloud.storage'] = mock_storage
mock_genai = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.genai'] = mock_genai
sys.modules['google.genai.types'] = MagicMock()
mock_google_cloud = MagicMock()
mock_google_cloud.storage = mock_storage
sys.modules['google.cloud'] = mock_google_cloud

from article_processor_function.embedding_service import EmbeddingService


class TestEmbeddingServiceInit:
    """Tests for EmbeddingService initialization."""

    def test_class_constants(self):
        """Should have expected class constants."""
        assert EmbeddingService.BATCH_SIZE == 40
        assert EmbeddingService.MODEL == "text-embedding-004"
        assert EmbeddingService.MAX_BODY_LENGTH == 500

    def test_initialization(self):
        """Should initialize with client."""
        mock_client = Mock()
        service = EmbeddingService(client=mock_client)
        assert service.client == mock_client


class TestPrepareText:
    """Tests for _prepare_text method."""

    @pytest.fixture
    def service(self):
        """Create a service with mock client."""
        return EmbeddingService(client=Mock())

    def test_combines_title_and_body(self, service):
        """Should combine title and body."""
        article = {
            "title": "Test Title",
            "body": "Test body content"
        }
        result = service._prepare_text(article)
        assert result == "Test Title Test body content"

    def test_truncates_body_to_500_chars(self, service):
        """Should truncate body to 500 characters."""
        long_body = "A" * 1000
        article = {
            "title": "Title",
            "body": long_body
        }
        result = service._prepare_text(article)
        # Title + space + 500 chars = "Title " + "A"*500
        assert len(result) == 6 + 500

    def test_handles_missing_title(self, service):
        """Should handle missing title."""
        article = {"body": "Body only"}
        result = service._prepare_text(article)
        assert result == "Body only"

    def test_handles_missing_body(self, service):
        """Should handle missing body."""
        article = {"title": "Title only"}
        result = service._prepare_text(article)
        assert result == "Title only"

    def test_handles_empty_article(self, service):
        """Should handle empty article."""
        article = {}
        result = service._prepare_text(article)
        assert result == ""

    def test_handles_none_values(self, service):
        """Should handle None values."""
        article = {"title": None, "body": None}
        result = service._prepare_text(article)
        assert result == ""

    def test_strips_whitespace(self, service):
        """Should strip leading/trailing whitespace."""
        article = {"title": "  Title  ", "body": "  Body  "}
        result = service._prepare_text(article)
        # Result will be "  Title   " + "  Body" (truncated), then stripped
        assert not result.startswith(" ")
        assert not result.endswith(" ")


class TestGenerateEmbeddings:
    """Tests for generate_embeddings method."""

    @pytest.fixture
    def service(self):
        """Create a service with mock client."""
        return EmbeddingService(client=Mock())

    def test_returns_empty_array_for_empty_input(self, service):
        """Should return empty array for empty input."""
        result = service.generate_embeddings([])
        assert isinstance(result, np.ndarray)
        assert len(result) == 0

    def test_calls_client_for_articles(self, service):
        """Should call client to generate embeddings."""
        # Setup mock response
        mock_embedding = Mock()
        mock_embedding.values = [0.1, 0.2, 0.3]
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        service.client.models.embed_content = Mock(return_value=mock_response)

        articles = [{"title": "Test", "body": "Content"}]
        result = service.generate_embeddings(articles)

        service.client.models.embed_content.assert_called_once()
        assert isinstance(result, np.ndarray)
        assert result.shape == (1, 3)

    def test_processes_in_batches(self, service):
        """Should process articles in batches of BATCH_SIZE."""
        # Create more articles than batch size
        articles = [{"title": f"Article {i}"} for i in range(50)]

        mock_embedding = Mock()
        mock_embedding.values = [0.1, 0.2, 0.3]
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding] * service.BATCH_SIZE
        service.client.models.embed_content = Mock(return_value=mock_response)

        # Should make 2 calls (40 + 10)
        result = service.generate_embeddings(articles)
        
        assert service.client.models.embed_content.call_count == 2

    def test_raises_on_client_error(self, service):
        """Should raise exception on client error."""
        service.client.models.embed_content = Mock(side_effect=Exception("API Error"))

        articles = [{"title": "Test"}]
        with pytest.raises(Exception, match="API Error"):
            service.generate_embeddings(articles)


class TestGenerateSingleEmbedding:
    """Tests for generate_single_embedding method."""

    @pytest.fixture
    def service(self):
        """Create a service with mock client."""
        return EmbeddingService(client=Mock())

    def test_returns_embedding_array(self, service):
        """Should return embedding as numpy array."""
        mock_embedding = Mock()
        mock_embedding.values = [0.1, 0.2, 0.3]
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        service.client.models.embed_content = Mock(return_value=mock_response)

        result = service.generate_single_embedding("test text")

        assert isinstance(result, np.ndarray)
        assert list(result) == [0.1, 0.2, 0.3]

    def test_returns_none_on_error(self, service):
        """Should return None on error."""
        service.client.models.embed_content = Mock(side_effect=Exception("Error"))

        result = service.generate_single_embedding("test text")

        assert result is None
