"""
Unit tests for article_processor_function/llm_processor.py

Tests the LLM processor batch request creation and response parsing logic.
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from article_processor_function.llm_processor import LLMProcessor
from article_processor_function.grouping_service import ArticleGroup


class TestLLMProcessorInit:
    """Tests for LLMProcessor initialization."""

    def test_initialization(self):
        """Should initialize with all required parameters."""
        mock_genai = Mock()
        mock_storage = Mock()

        processor = LLMProcessor(
            genai_client=mock_genai,
            storage_client=mock_storage,
            bucket_name="test-bucket",
            model="test-model",
            thinking_level="MEDIUM"
        )

        assert processor.genai_client == mock_genai
        assert processor.storage_client == mock_storage
        assert processor.bucket_name == "test-bucket"
        assert processor.model == "test-model"
        assert processor.thinking_level == "MEDIUM"

    def test_default_model_and_thinking(self):
        """Should use default model and thinking level."""
        processor = LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket"
        )

        assert processor.model == "gemini-3-pro-preview"
        assert processor.thinking_level == "LOW"


class TestLoadPromptTemplate:
    """Tests for load_prompt_template method."""

    @pytest.fixture
    def processor(self):
        """Create processor with mocks."""
        return LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket"
        )

    def test_loads_existing_prompt(self, processor):
        """Should load prompt from UNIFIED_PROMPT.md file."""
        # The actual file should exist in the package
        prompt = processor.load_prompt_template()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_contains_expected_content(self, processor):
        """Prompt should contain expected sections."""
        prompt = processor.load_prompt_template()
        # The prompt should contain key instructions
        assert "article" in prompt.lower() or "ARTICLE" in prompt


class TestCreateBatchRequest:
    """Tests for create_batch_request method."""

    @pytest.fixture
    def processor(self):
        """Create processor with mocks."""
        return LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket"
        )

    def test_creates_request_for_each_group(self, processor):
        """Should create one request per group."""
        groups = [
            ArticleGroup(group_id=1, article_indices=[0, 1]),
            ArticleGroup(group_id=2, article_indices=[2]),
        ]
        articles = [
            {"article_id": "a1", "title": "Article 1"},
            {"article_id": "a2", "title": "Article 2"},
            {"article_id": "a3", "title": "Article 3"},
        ]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test prompt"
        )

        assert len(requests) == 2

    def test_request_structure(self, processor):
        """Request should have correct structure."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "a1", "title": "Article 1"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test prompt"
        )

        request = requests[0]
        assert "request" in request
        assert "contents" in request["request"]
        assert "generationConfig" in request["request"]

    def test_includes_prompt_template(self, processor):
        """Request should include prompt template."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "a1", "title": "Article 1"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="My custom prompt"
        )

        content_text = requests[0]["request"]["contents"][0]["parts"][0]["text"]
        assert content_text == "My custom prompt"

    def test_includes_article_data_as_json(self, processor):
        """Request should include article data as JSON."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "a1", "title": "Article 1"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test prompt"
        )

        data_text = requests[0]["request"]["contents"][0]["parts"][1]["text"]
        assert "ARTICLE GROUP DATA" in data_text
        assert "a1" in data_text

    def test_generation_config_settings(self, processor):
        """Request should have correct generation config."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "a1", "title": "Article 1"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test prompt"
        )

        config = requests[0]["request"]["generationConfig"]
        assert config["temperature"] == 0.1
        assert config["topP"] == 0.95
        assert config["responseMimeType"] == "application/json"

    def test_empty_groups_returns_empty_list(self, processor):
        """Should return empty list for empty groups."""
        requests = processor.create_batch_request(
            groups=[],
            articles=[],
            prompt_template="Test"
        )
        assert requests == []


class TestCreateBatchRequestForSingletons:
    """Tests for create_batch_request_for_singletons method."""

    @pytest.fixture
    def processor(self):
        """Create processor with mocks."""
        return LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket"
        )

    def test_batches_singletons(self, processor):
        """Should batch multiple singletons into single requests."""
        # Create 25 singletons, with batch_size=10
        singleton_groups = [
            ArticleGroup(group_id=i, article_indices=[i])
            for i in range(25)
        ]
        articles = [
            {"article_id": f"a{i}", "title": f"Article {i}"}
            for i in range(25)
        ]

        requests = processor.create_batch_request_for_singletons(
            singleton_groups=singleton_groups,
            articles=articles,
            prompt_template="Test prompt",
            batch_size=10
        )

        # Should create 3 batches: 10 + 10 + 5
        assert len(requests) == 3

    def test_request_contains_batch_marker(self, processor):
        """Request should indicate batch processing."""
        singleton_groups = [ArticleGroup(group_id=0, article_indices=[0])]
        articles = [{"article_id": "a1", "title": "Article 1"}]

        requests = processor.create_batch_request_for_singletons(
            singleton_groups=singleton_groups,
            articles=articles,
            prompt_template="Test prompt",
            batch_size=10
        )

        data_text = requests[0]["request"]["contents"][0]["parts"][1]["text"]
        assert "BATCH OF SINGLETON ARTICLES" in data_text

    def test_empty_singletons_returns_empty(self, processor):
        """Should return empty list for no singletons."""
        requests = processor.create_batch_request_for_singletons(
            singleton_groups=[],
            articles=[],
            prompt_template="Test"
        )
        assert requests == []
