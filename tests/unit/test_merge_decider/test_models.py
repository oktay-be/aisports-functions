"""
Unit tests for merge_decider_function/models.py

Tests the Vertex AI response schema structure.
"""

import pytest
from merge_decider_function.models import VERTEX_AI_RESPONSE_SCHEMA


class TestVertexAiResponseSchema:
    """Tests for VERTEX_AI_RESPONSE_SCHEMA constant."""

    def test_schema_is_dict(self):
        """Schema should be a dictionary."""
        assert isinstance(VERTEX_AI_RESPONSE_SCHEMA, dict)

    def test_schema_type_is_object(self):
        """Schema type should be object."""
        assert VERTEX_AI_RESPONSE_SCHEMA["type"] == "object"

    def test_has_required_properties(self):
        """Schema should have required array with 'decisions'."""
        assert "required" in VERTEX_AI_RESPONSE_SCHEMA
        assert "decisions" in VERTEX_AI_RESPONSE_SCHEMA["required"]

    def test_decisions_is_array(self):
        """Decisions property should be an array type."""
        decisions = VERTEX_AI_RESPONSE_SCHEMA["properties"]["decisions"]
        assert decisions["type"] == "array"

    def test_decision_item_has_required_fields(self):
        """Decision items should have required fields."""
        items = VERTEX_AI_RESPONSE_SCHEMA["properties"]["decisions"]["items"]
        required = items["required"]
        
        assert "group_id" in required
        assert "decision" in required
        assert "reason" in required

    def test_decision_enum_values(self):
        """Decision field should have valid enum values."""
        items = VERTEX_AI_RESPONSE_SCHEMA["properties"]["decisions"]["items"]
        decision_enum = items["properties"]["decision"]["enum"]
        
        assert "MERGE" in decision_enum
        assert "PARTIAL_MERGE" in decision_enum
        assert "KEEP_ALL" in decision_enum

    def test_merged_article_ids_is_array(self):
        """merged_article_ids should be an array of strings."""
        items = VERTEX_AI_RESPONSE_SCHEMA["properties"]["decisions"]["items"]
        merged_ids = items["properties"]["merged_article_ids"]
        
        assert merged_ids["type"] == "array"
        assert merged_ids["items"]["type"] == "string"

    def test_primary_article_fields_nullable(self):
        """Primary article fields should be nullable."""
        items = VERTEX_AI_RESPONSE_SCHEMA["properties"]["decisions"]["items"]
        props = items["properties"]
        
        assert props["primary_article_id"]["nullable"] is True
        assert props["primary_article_url"]["nullable"] is True
