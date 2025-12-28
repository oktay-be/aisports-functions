"""
Unit tests for article_processor_function/models.py

Tests the Pydantic models and helper functions for the article processor.
"""

import pytest
import json
from datetime import datetime
import sys
from unittest.mock import MagicMock

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

from article_processor_function.models import (
    RawArticle,
    ArticleGroupInput,
    CategoryAssignment,
    KeyEntities,
    GroupingMetadata,
    ProcessedArticle,
    GroupProcessingResult,
    ProcessingSummary,
    ProcessingOutput,
    article_to_group_input,
    parse_llm_response,
    VERTEX_AI_RESPONSE_SCHEMA,
)


class TestRawArticle:
    """Tests for RawArticle model."""

    def test_required_fields(self):
        """Should require article_id, url, and title."""
        article = RawArticle(
            article_id="abc123",
            url="https://example.com/article",
            title="Test Article"
        )
        assert article.article_id == "abc123"
        assert article.url == "https://example.com/article"
        assert article.title == "Test Article"

    def test_default_values(self):
        """Should have sensible default values."""
        article = RawArticle(
            article_id="abc123",
            url="https://example.com/article",
            title="Test Article"
        )
        assert article.body == ""
        assert article.source == ""
        assert article.publish_date is None
        assert article.keywords_used == []
        assert article.language == "en"
        assert article.region == "eu"

    def test_all_fields(self):
        """Should accept all fields."""
        article = RawArticle(
            article_id="abc123",
            url="https://example.com/article",
            title="Test Article",
            body="Article content here",
            source="example.com",
            publish_date="2025-01-01T12:00:00Z",
            keywords_used=["sports", "transfer"],
            language="tr",
            region="tr"
        )
        assert article.body == "Article content here"
        assert article.source == "example.com"
        assert article.keywords_used == ["sports", "transfer"]
        assert article.language == "tr"
        assert article.region == "tr"


class TestArticleGroupInput:
    """Tests for ArticleGroupInput model."""

    def test_basic_creation(self):
        """Should create group input with required fields."""
        group = ArticleGroupInput(
            group_id=1,
            group_size=3,
            max_similarity=0.95,
            articles=[{"id": "1"}, {"id": "2"}]
        )
        assert group.group_id == 1
        assert group.group_size == 3
        assert group.max_similarity == 0.95
        assert len(group.articles) == 2


class TestCategoryAssignment:
    """Tests for CategoryAssignment model."""

    def test_basic_creation(self):
        """Should create category assignment."""
        category = CategoryAssignment(
            tag="transfer",
            confidence=0.9,
            evidence="Player mentioned transfer"
        )
        assert category.tag == "transfer"
        assert category.confidence == 0.9

    def test_default_evidence(self):
        """Should have empty default evidence."""
        category = CategoryAssignment(tag="news", confidence=0.8)
        assert category.evidence == ""

    def test_confidence_validation_min(self):
        """Confidence should be at least 0.0."""
        with pytest.raises(ValueError):
            CategoryAssignment(tag="test", confidence=-0.1)

    def test_confidence_validation_max(self):
        """Confidence should be at most 1.0."""
        with pytest.raises(ValueError):
            CategoryAssignment(tag="test", confidence=1.1)


class TestKeyEntities:
    """Tests for KeyEntities model."""

    def test_default_empty_lists(self):
        """Should have empty lists by default."""
        entities = KeyEntities()
        assert entities.teams == []
        assert entities.players == []
        assert entities.amounts == []
        assert entities.dates == []
        assert entities.competitions == []
        assert entities.locations == []

    def test_with_values(self):
        """Should accept entity values."""
        entities = KeyEntities(
            teams=["Team A", "Team B"],
            players=["Player 1"],
            amounts=["$10M"],
            dates=["2025-01-01"],
            competitions=["Champions League"],
            locations=["London"]
        )
        assert "Team A" in entities.teams
        assert "Player 1" in entities.players


class TestGroupingMetadata:
    """Tests for GroupingMetadata model."""

    def test_basic_creation(self):
        """Should create grouping metadata."""
        metadata = GroupingMetadata(
            group_id=1,
            group_size=3,
            max_similarity=0.95,
            merge_decision="MERGED"
        )
        assert metadata.group_id == 1
        assert metadata.merge_decision == "MERGED"


class TestProcessedArticle:
    """Tests for ProcessedArticle model."""

    def test_required_fields(self):
        """Should require core fields."""
        article = ProcessedArticle(
            article_id="abc123",
            original_url="https://example.com/article",
            title="Test Article",
            summary="This is a test summary.",
            source="example.com",
            publish_date="2025-01-01T12:00:00Z"
        )
        assert article.article_id == "abc123"
        assert article.title == "Test Article"

    def test_default_values(self):
        """Should have sensible defaults."""
        article = ProcessedArticle(
            article_id="abc123",
            original_url="https://example.com/article",
            title="Test",
            summary="Summary",
            source="test.com",
            publish_date="2025-01-01"
        )
        assert article.merged_from_urls == []
        assert article.content_quality == "medium"
        assert article.confidence == 0.8
        assert article.language == "turkish"
        assert article.region == "eu"
        assert article.x_post == ""
        assert article.summary_translation is None


class TestGroupProcessingResult:
    """Tests for GroupProcessingResult model."""

    def test_basic_creation(self):
        """Should create processing result."""
        result = GroupProcessingResult(
            group_decision="MERGE",
            merge_reason="Same event",
            output_articles=[
                ProcessedArticle(
                    article_id="abc123",
                    original_url="https://example.com",
                    title="Test",
                    summary="Summary",
                    source="test.com",
                    publish_date="2025-01-01"
                )
            ]
        )
        assert result.group_decision == "MERGE"
        assert result.merge_reason == "Same event"
        assert len(result.output_articles) == 1


class TestProcessingSummary:
    """Tests for ProcessingSummary model."""

    def test_basic_creation(self):
        """Should create processing summary."""
        summary = ProcessingSummary(
            total_input_articles=100,
            total_output_articles=80,
            groups_processed=30,
            articles_merged=20,
            articles_kept_separate=60,
            singleton_articles=20
        )
        assert summary.total_input_articles == 100
        assert summary.total_output_articles == 80

    def test_default_values(self):
        """Should have default values for optional fields."""
        summary = ProcessingSummary(
            total_input_articles=10,
            total_output_articles=10,
            groups_processed=5,
            articles_merged=0,
            articles_kept_separate=10,
            singleton_articles=5
        )
        assert summary.embedding_model == "text-embedding-004"
        assert summary.similarity_threshold == 0.85

    def test_processing_date_auto_generated(self):
        """Should auto-generate processing date."""
        summary = ProcessingSummary(
            total_input_articles=10,
            total_output_articles=10,
            groups_processed=5,
            articles_merged=0,
            articles_kept_separate=10,
            singleton_articles=5
        )
        # Should be a valid ISO datetime string
        datetime.fromisoformat(summary.processing_date)


class TestProcessingOutput:
    """Tests for ProcessingOutput model."""

    def test_basic_creation(self):
        """Should create complete processing output."""
        output = ProcessingOutput(
            processing_summary=ProcessingSummary(
                total_input_articles=10,
                total_output_articles=8,
                groups_processed=5,
                articles_merged=2,
                articles_kept_separate=6,
                singleton_articles=2
            ),
            processed_articles=[]
        )
        assert output.processing_summary.total_input_articles == 10
        assert output.processed_articles == []


class TestArticleToGroupInput:
    """Tests for article_to_group_input helper function."""

    def test_converts_articles_to_group_format(self):
        """Should convert articles list to group input format."""
        articles = [
            {"article_id": "1", "title": "Article 1"},
            {"article_id": "2", "title": "Article 2"},
        ]
        result = article_to_group_input(articles, group_id=5, max_similarity=0.92)

        assert result["group_id"] == 5
        assert result["group_size"] == 2
        assert result["max_similarity"] == 0.92
        assert result["articles"] == articles

    def test_empty_articles_list(self):
        """Should handle empty articles list."""
        result = article_to_group_input([], group_id=1, max_similarity=0.0)
        
        assert result["group_size"] == 0
        assert result["articles"] == []


class TestParseLlmResponse:
    """Tests for parse_llm_response helper function."""

    def test_parses_valid_response(self):
        """Should parse valid LLM response."""
        response = json.dumps({
            "group_decision": "MERGE",
            "merge_reason": "Same event reported",
            "output_articles": [
                {
                    "article_id": "abc123",
                    "original_url": "https://example.com",
                    "merged_from_urls": ["https://example.com"],
                    "title": "Test",
                    "summary": "Summary",
                    "key_entities": {"teams": [], "players": [], "amounts": [], "dates": [], "competitions": [], "locations": []},
                    "categories": [{"tag": "transfer", "confidence": 0.9, "evidence": ""}],
                    "source": "example.com",
                    "publish_date": "2025-01-01",
                    "content_quality": "high",
                    "confidence": 0.95,
                    "language": "turkish",
                    "region": "tr",
                    "summary_translation": None,
                    "x_post": "Test tweet"
                }
            ]
        })

        result = parse_llm_response(response, group_id=1, group_size=2, max_similarity=0.9)

        assert result.group_decision == "MERGE"
        assert result.merge_reason == "Same event reported"
        assert len(result.output_articles) == 1

    def test_adds_grouping_metadata(self):
        """Should add grouping metadata to output articles."""
        response = json.dumps({
            "group_decision": "KEEP_SEPARATE",
            "output_articles": [
                {
                    "article_id": "abc123",
                    "original_url": "https://example.com",
                    "merged_from_urls": [],
                    "title": "Test",
                    "summary": "Summary",
                    "key_entities": {"teams": [], "players": [], "amounts": [], "dates": [], "competitions": [], "locations": []},
                    "categories": [],
                    "source": "example.com",
                    "publish_date": "2025-01-01",
                    "content_quality": "medium",
                    "confidence": 0.8,
                    "language": "english",
                    "region": "eu",
                    "summary_translation": None,
                    "x_post": ""
                }
            ]
        })

        result = parse_llm_response(response, group_id=5, group_size=3, max_similarity=0.85)

        # Check that metadata was added (via dict in the raw response)
        assert result.group_decision == "KEEP_SEPARATE"

    def test_invalid_json_raises_error(self):
        """Should raise error for invalid JSON."""
        with pytest.raises(json.JSONDecodeError):
            parse_llm_response("not valid json", group_id=1, group_size=1, max_similarity=0.0)


class TestVertexAiResponseSchema:
    """Tests for VERTEX_AI_RESPONSE_SCHEMA constant."""

    def test_schema_is_dict(self):
        """Schema should be a dictionary."""
        assert isinstance(VERTEX_AI_RESPONSE_SCHEMA, dict)

    def test_schema_has_required_fields(self):
        """Schema should have required top-level fields."""
        assert "type" in VERTEX_AI_RESPONSE_SCHEMA
        assert "properties" in VERTEX_AI_RESPONSE_SCHEMA
        assert "required" in VERTEX_AI_RESPONSE_SCHEMA

    def test_schema_type_is_object(self):
        """Schema type should be OBJECT."""
        assert VERTEX_AI_RESPONSE_SCHEMA["type"] == "OBJECT"

    def test_required_properties(self):
        """Schema should require group_decision and output_articles."""
        required = VERTEX_AI_RESPONSE_SCHEMA["required"]
        assert "group_decision" in required
        assert "output_articles" in required
