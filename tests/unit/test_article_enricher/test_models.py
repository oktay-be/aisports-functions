"""
Unit tests for article_enricher_function/models.py

Tests the Vertex AI response schema structure for article enrichment.
"""

import pytest
from article_enricher_function.models import VERTEX_AI_RESPONSE_SCHEMA


class TestVertexAiResponseSchema:
    """Tests for VERTEX_AI_RESPONSE_SCHEMA constant."""

    def test_schema_is_dict(self):
        """Schema should be a dictionary."""
        assert isinstance(VERTEX_AI_RESPONSE_SCHEMA, dict)

    def test_schema_type_is_object(self):
        """Schema type should be object."""
        assert VERTEX_AI_RESPONSE_SCHEMA["type"] == "object"

    def test_has_enriched_articles_property(self):
        """Schema should have enriched_articles property."""
        assert "enriched_articles" in VERTEX_AI_RESPONSE_SCHEMA["properties"]

    def test_enriched_articles_is_array(self):
        """enriched_articles should be an array."""
        articles = VERTEX_AI_RESPONSE_SCHEMA["properties"]["enriched_articles"]
        assert articles["type"] == "array"

    def test_article_has_required_fields(self):
        """Article items should have required fields."""
        items = VERTEX_AI_RESPONSE_SCHEMA["properties"]["enriched_articles"]["items"]
        required = items["required"]
        
        assert "article_id" in required
        assert "summary" in required

    def test_article_has_key_entities(self):
        """Article items should have key_entities object."""
        items = VERTEX_AI_RESPONSE_SCHEMA["properties"]["enriched_articles"]["items"]
        key_entities = items["properties"]["key_entities"]
        
        assert key_entities["type"] == "object"
        assert "teams" in key_entities["properties"]
        assert "players" in key_entities["properties"]

    def test_categories_is_array(self):
        """Categories should be an array."""
        items = VERTEX_AI_RESPONSE_SCHEMA["properties"]["enriched_articles"]["items"]
        categories = items["properties"]["categories"]
        
        assert categories["type"] == "array"

    def test_category_item_structure(self):
        """Category items should have tag and confidence."""
        items = VERTEX_AI_RESPONSE_SCHEMA["properties"]["enriched_articles"]["items"]
        cat_items = items["properties"]["categories"]["items"]
        
        assert "tag" in cat_items["properties"]
        assert "confidence" in cat_items["properties"]
        assert cat_items["required"] == ["tag", "confidence"]

    def test_content_quality_enum(self):
        """content_quality should have enum values."""
        items = VERTEX_AI_RESPONSE_SCHEMA["properties"]["enriched_articles"]["items"]
        content_quality = items["properties"]["content_quality"]
        
        assert content_quality["type"] == "string"
        assert "high" in content_quality["enum"]
        assert "medium" in content_quality["enum"]
        assert "low" in content_quality["enum"]
