"""
Unit tests for article_processor_function/llm_processor.py

Tests the LLM processor batch request creation and response parsing logic.
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import sys

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

class TestCreateBatchRequestGenerationConfig:
    """Tests for create_batch_request generation config."""

    @pytest.fixture
    def processor(self):
        """Create processor with mocks."""
        return LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket",
            thinking_level="HIGH"
        )

    def test_thinking_level_included(self, processor):
        """Request should include thinking config."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "a1", "title": "Article 1"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test prompt"
        )

        config = requests[0]["request"]["generationConfig"]
        assert "thinkingConfig" in config
        assert config["thinkingConfig"]["thinkingLevel"] == "HIGH"

    def test_response_schema_included(self, processor):
        """Request should include response schema."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "a1", "title": "Article 1"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test prompt"
        )

        config = requests[0]["request"]["generationConfig"]
        assert "responseSchema" in config

    def test_max_output_tokens_value(self, processor):
        """Request should have max output tokens set."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "a1", "title": "Article 1"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test prompt"
        )

        config = requests[0]["request"]["generationConfig"]
        assert config["maxOutputTokens"] == 65535


class TestSingletonBatchSizes:
    """Tests for singleton batch size handling."""

    @pytest.fixture
    def processor(self):
        """Create processor with mocks."""
        return LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket"
        )

    def test_exact_batch_size(self, processor):
        """Should create exactly batch_size entries per request."""
        singleton_groups = [
            ArticleGroup(group_id=i, article_indices=[i])
            for i in range(10)
        ]
        articles = [{"article_id": f"a{i}"} for i in range(10)]

        requests = processor.create_batch_request_for_singletons(
            singleton_groups=singleton_groups,
            articles=articles,
            prompt_template="Test",
            batch_size=10
        )

        assert len(requests) == 1

    def test_batch_size_plus_one(self, processor):
        """Should create 2 batches for batch_size + 1 items."""
        singleton_groups = [
            ArticleGroup(group_id=i, article_indices=[i])
            for i in range(11)
        ]
        articles = [{"article_id": f"a{i}"} for i in range(11)]

        requests = processor.create_batch_request_for_singletons(
            singleton_groups=singleton_groups,
            articles=articles,
            prompt_template="Test",
            batch_size=10
        )

        assert len(requests) == 2

    def test_small_batch_size(self, processor):
        """Should handle small batch sizes."""
        singleton_groups = [
            ArticleGroup(group_id=i, article_indices=[i])
            for i in range(5)
        ]
        articles = [{"article_id": f"a{i}"} for i in range(5)]

        requests = processor.create_batch_request_for_singletons(
            singleton_groups=singleton_groups,
            articles=articles,
            prompt_template="Test",
            batch_size=2
        )

        assert len(requests) == 3  # 2 + 2 + 1


class TestBatchRequestContents:
    """Tests for batch request content structure."""

    @pytest.fixture
    def processor(self):
        """Create processor with mocks."""
        return LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket"
        )

    def test_request_has_user_role(self, processor):
        """Request should have user role in contents."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "a1"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test"
        )

        contents = requests[0]["request"]["contents"]
        assert len(contents) == 1
        assert contents[0]["role"] == "user"

    def test_request_has_two_parts(self, processor):
        """Request should have prompt and data parts."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "a1"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test"
        )

        parts = requests[0]["request"]["contents"][0]["parts"]
        assert len(parts) == 2
        assert "text" in parts[0]
        assert "text" in parts[1]

    def test_data_part_contains_json(self, processor):
        """Data part should contain valid JSON."""
        groups = [ArticleGroup(group_id=1, article_indices=[0])]
        articles = [{"article_id": "test123", "title": "Test"}]

        requests = processor.create_batch_request(
            groups=groups,
            articles=articles,
            prompt_template="Test"
        )

        data_text = requests[0]["request"]["contents"][0]["parts"][1]["text"]
        # Should contain JSON-formatted data
        assert "test123" in data_text
        assert "```json" in data_text


class TestSingletonBatchContents:
    """Tests for singleton batch request contents."""

    @pytest.fixture
    def processor(self):
        """Create processor with mocks."""
        return LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket"
        )

    def test_batch_processing_flag(self, processor):
        """Singleton batch should indicate batch processing."""
        singleton_groups = [ArticleGroup(group_id=0, article_indices=[0])]
        articles = [{"article_id": "a1"}]

        requests = processor.create_batch_request_for_singletons(
            singleton_groups=singleton_groups,
            articles=articles,
            prompt_template="Test",
            batch_size=10
        )

        data_text = requests[0]["request"]["contents"][0]["parts"][1]["text"]
        assert "batch_processing" in data_text or "BATCH OF SINGLETON" in data_text

    def test_multiple_groups_in_batch(self, processor):
        """Batch should contain multiple groups."""
        singleton_groups = [
            ArticleGroup(group_id=0, article_indices=[0]),
            ArticleGroup(group_id=1, article_indices=[1]),
        ]
        articles = [
            {"article_id": "a0"},
            {"article_id": "a1"},
        ]

        requests = processor.create_batch_request_for_singletons(
            singleton_groups=singleton_groups,
            articles=articles,
            prompt_template="Test",
            batch_size=10
        )

        data_text = requests[0]["request"]["contents"][0]["parts"][1]["text"]
        assert "a0" in data_text
        assert "a1" in data_text


class TestLLMProcessorThinkingLevels:
    """Tests for different thinking levels."""

    def test_low_thinking_level(self):
        """Should use LOW thinking level."""
        processor = LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket",
            thinking_level="LOW"
        )
        assert processor.thinking_level == "LOW"

    def test_medium_thinking_level(self):
        """Should use MEDIUM thinking level."""
        processor = LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket",
            thinking_level="MEDIUM"
        )
        assert processor.thinking_level == "MEDIUM"

    def test_high_thinking_level(self):
        """Should use HIGH thinking level."""
        processor = LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket",
            thinking_level="HIGH"
        )
        assert processor.thinking_level == "HIGH"


class TestLLMProcessorModelConfig:
    """Tests for model configuration."""

    def test_custom_model(self):
        """Should use custom model."""
        processor = LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket",
            model="gemini-2.0-flash"
        )
        assert processor.model == "gemini-2.0-flash"

    def test_default_model(self):
        """Should use default model when not specified."""
        processor = LLMProcessor(
            genai_client=Mock(),
            storage_client=Mock(),
            bucket_name="test-bucket"
        )
        assert "gemini" in processor.model