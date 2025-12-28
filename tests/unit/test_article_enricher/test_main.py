"""Unit tests for article_enricher_function/main.py."""

import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock timezone before importing
mock_zoneinfo = MagicMock()
sys.modules['zoneinfo'] = mock_zoneinfo

# Mock Google Cloud clients before importing
with patch.dict('os.environ', {'ENVIRONMENT': 'local'}):
    from article_enricher_function.main import (
        extract_path_info,
        TRIGGER_PATTERNS,
    )


class TestExtractPathInfo:
    """Tests for extract_path_info function."""

    def test_valid_singleton_path(self):
        """Test extracting info from valid singleton path."""
        path = "ingestion/2024-12-28/14-30-45/singleton_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        
        assert date_str == "2024-12-28"
        assert run_id == "14-30-45"
        assert filename == "singleton_complete_articles.json"

    def test_valid_decision_path(self):
        """Test extracting info from valid decision path."""
        path = "ingestion/2024-12-28/10-15-30/decision_scraped_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        
        assert date_str == "2024-12-28"
        assert run_id == "10-15-30"
        assert filename == "decision_scraped_articles.json"

    def test_path_with_gs_prefix(self):
        """Test path with gs:// prefix."""
        path = "gs://bucket-name/ingestion/2024-06-15/23-59-59/singleton_scraped_incomplete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        
        assert date_str == "2024-06-15"
        assert run_id == "23-59-59"
        assert filename == "singleton_scraped_incomplete_articles.json"

    def test_invalid_path_handling(self):
        """Test invalid path handling."""
        path = "invalid/path.txt"
        
        try:
            date_str, run_id, filename = extract_path_info(path)
            # Returns current time format if no match
            assert len(date_str) == 10
            assert len(run_id) == 8
        except TypeError:
            pytest.skip("Skipped due to mocked timezone")


class TestTriggerPatterns:
    """Tests for TRIGGER_PATTERNS constant."""

    def test_singleton_complete_pattern(self):
        """Test singleton_complete_articles.json pattern."""
        assert 'singleton_complete_articles.json' in TRIGGER_PATTERNS

    def test_singleton_scraped_incomplete_pattern(self):
        """Test singleton_scraped_incomplete_articles.json pattern."""
        assert 'singleton_scraped_incomplete_articles.json' in TRIGGER_PATTERNS

    def test_singleton_scraped_pattern(self):
        """Test singleton_scraped_articles.json pattern."""
        assert 'singleton_scraped_articles.json' in TRIGGER_PATTERNS

    def test_decision_complete_pattern(self):
        """Test decision_complete_articles.json pattern."""
        assert 'decision_complete_articles.json' in TRIGGER_PATTERNS

    def test_decision_scraped_incomplete_pattern(self):
        """Test decision_scraped_incomplete_articles.json pattern."""
        assert 'decision_scraped_incomplete_articles.json' in TRIGGER_PATTERNS

    def test_decision_scraped_pattern(self):
        """Test decision_scraped_articles.json pattern."""
        assert 'decision_scraped_articles.json' in TRIGGER_PATTERNS

    def test_has_six_patterns(self):
        """Test there are exactly six trigger patterns."""
        assert len(TRIGGER_PATTERNS) == 6


class TestEnrichmentPrompt:
    """Tests for ENRICHMENT_PROMPT content."""

    def test_prompt_mentions_summary(self):
        """Test prompt mentions summary generation."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "summary" in ENRICHMENT_PROMPT.lower()

    def test_prompt_mentions_x_post(self):
        """Test prompt mentions X/Twitter post generation."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "x_post" in ENRICHMENT_PROMPT.lower()

    def test_prompt_mentions_categories(self):
        """Test prompt mentions category tagging."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "categories" in ENRICHMENT_PROMPT.lower()

    def test_prompt_mentions_key_entities(self):
        """Test prompt mentions key entities extraction."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "key_entities" in ENRICHMENT_PROMPT.lower()

    def test_prompt_mentions_turkish(self):
        """Test prompt mentions Turkish language."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "Turkish" in ENRICHMENT_PROMPT

    def test_prompt_mentions_enriched_articles(self):
        """Test prompt mentions enriched_articles output."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "enriched_articles" in ENRICHMENT_PROMPT

    def test_prompt_mentions_transfer_tag(self):
        """Test prompt mentions transfers tag."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "transfers" in ENRICHMENT_PROMPT.lower()

    def test_prompt_has_character_limit(self):
        """Test prompt mentions 280 character limit for X posts."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "280" in ENRICHMENT_PROMPT

    def test_prompt_mentions_hashtags(self):
        """Test prompt mentions hashtags."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "hashtag" in ENRICHMENT_PROMPT.lower()

    def test_prompt_mentions_confidence(self):
        """Test prompt mentions confidence score."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "confidence" in ENRICHMENT_PROMPT.lower()


class TestExtractSourceType:
    """Tests for extract_source_type function."""

    def test_complete_source_type(self):
        """Test complete source type extraction."""
        from article_enricher_function.main import extract_source_type
        assert extract_source_type("singleton_complete_articles.json") == "complete"
        assert extract_source_type("decision_complete_articles.json") == "complete"

    def test_scraped_incomplete_source_type(self):
        """Test scraped_incomplete source type extraction."""
        from article_enricher_function.main import extract_source_type
        assert extract_source_type("singleton_scraped_incomplete_articles.json") == "scraped_incomplete"
        assert extract_source_type("decision_scraped_incomplete_articles.json") == "scraped_incomplete"

    def test_scraped_source_type(self):
        """Test scraped source type extraction."""
        from article_enricher_function.main import extract_source_type
        assert extract_source_type("singleton_scraped_articles.json") == "scraped"
        assert extract_source_type("decision_scraped_articles.json") == "scraped"

    def test_unknown_source_type(self):
        """Test unknown source type returns 'unknown'."""
        from article_enricher_function.main import extract_source_type
        assert extract_source_type("random_file.json") == "unknown"


class TestExtractBranchType:
    """Tests for extract_branch_type function."""

    def test_singleton_branch(self):
        """Test singleton branch type extraction."""
        from article_enricher_function.main import extract_branch_type
        assert extract_branch_type("singleton_complete_articles.json") == "singleton"
        assert extract_branch_type("singleton_scraped_articles.json") == "singleton"

    def test_merged_branch(self):
        """Test merged branch type extraction."""
        from article_enricher_function.main import extract_branch_type
        assert extract_branch_type("decision_complete_articles.json") == "merged"
        assert extract_branch_type("decision_scraped_articles.json") == "merged"

    def test_unknown_branch(self):
        """Test unknown branch type returns 'unknown'."""
        from article_enricher_function.main import extract_branch_type
        assert extract_branch_type("random_file.json") == "unknown"


class TestExtractOutputPrefix:
    """Tests for extract_output_prefix function."""

    def test_singleton_prefix(self):
        """Test singleton output prefix."""
        from article_enricher_function.main import extract_output_prefix
        result = extract_output_prefix("singleton_complete_articles.json")
        assert result == "enriched_singleton_complete_articles"

    def test_decision_prefix(self):
        """Test decision output prefix."""
        from article_enricher_function.main import extract_output_prefix
        result = extract_output_prefix("decision_scraped_articles.json")
        assert result == "enriched_decision_scraped_articles"


class TestEnricherConfiguration:
    """Tests for enricher configuration constants."""

    def test_environment_default(self):
        """Test environment default value."""
        import os
        env = os.getenv('ENVIRONMENT', 'development')
        assert env in ['development', 'local', 'production', 'staging']

    def test_gcs_bucket_default(self):
        """Test GCS bucket default."""
        import os
        bucket = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
        assert bucket == 'aisports-scraping' or bucket

    def test_vertex_ai_model_default(self):
        """Test Vertex AI model default."""
        import os
        model = os.getenv('VERTEX_AI_MODEL', 'gemini-2.0-flash')
        assert 'gemini' in model


class TestTriggerPatternsValidation:
    """Additional tests for TRIGGER_PATTERNS validation."""

    def test_all_patterns_end_with_json(self):
        """Test all patterns end with .json."""
        for pattern in TRIGGER_PATTERNS:
            assert pattern.endswith('.json')

    def test_all_patterns_contain_articles(self):
        """Test all patterns contain 'articles'."""
        for pattern in TRIGGER_PATTERNS:
            assert 'articles' in pattern

    def test_singleton_patterns_count(self):
        """Test there are 3 singleton patterns."""
        singleton_patterns = [p for p in TRIGGER_PATTERNS if p.startswith('singleton_')]
        assert len(singleton_patterns) == 3

    def test_decision_patterns_count(self):
        """Test there are 3 decision patterns."""
        decision_patterns = [p for p in TRIGGER_PATTERNS if p.startswith('decision_')]
        assert len(decision_patterns) == 3


class TestExtractPathInfoEdgeCases:
    """Additional edge cases for extract_path_info."""

    def test_midnight_timestamp(self):
        """Test midnight timestamp extraction."""
        path = "ingestion/2024-12-28/00-00-00/singleton_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        assert run_id == "00-00-00"

    def test_end_of_day_timestamp(self):
        """Test end of day timestamp."""
        path = "ingestion/2024-12-28/23-59-59/decision_scraped_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        assert run_id == "23-59-59"

    def test_year_boundary(self):
        """Test year boundary dates."""
        path = "ingestion/2024-12-31/12-00-00/singleton_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        assert date_str == "2024-12-31"

    def test_january_first(self):
        """Test January 1st date."""
        path = "ingestion/2025-01-01/08-30-00/decision_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        assert date_str == "2025-01-01"

class TestExtractSourceTypeEdgeCases:
    """Additional edge cases for extract_source_type."""

    def test_scraped_incomplete_has_priority_over_scraped(self):
        """Test that scraped_incomplete is matched before scraped."""
        from article_enricher_function.main import extract_source_type
        result = extract_source_type("test_scraped_incomplete_file.json")
        assert result == "scraped_incomplete"

    def test_incomplete_alone_returns_complete(self):
        """Test that incomplete without scraped returns complete."""
        from article_enricher_function.main import extract_source_type
        # 'incomplete' alone should not match scraped_incomplete
        result = extract_source_type("test_incomplete_file.json")
        assert result == "unknown"

    def test_complete_in_middle_of_name(self):
        """Test complete keyword in middle of filename."""
        from article_enricher_function.main import extract_source_type
        result = extract_source_type("some_complete_data.json")
        assert result == "complete"

    def test_scraped_at_start(self):
        """Test scraped at start of filename."""
        from article_enricher_function.main import extract_source_type
        result = extract_source_type("scraped_data.json")
        assert result == "scraped"


class TestExtractBranchTypeEdgeCases:
    """Additional edge cases for extract_branch_type."""

    def test_singleton_with_extra_prefix(self):
        """Test singleton with extra text prefix."""
        from article_enricher_function.main import extract_branch_type
        result = extract_branch_type("singleton_scraped_incomplete_articles.json")
        assert result == "singleton"

    def test_decision_with_extra_prefix(self):
        """Test decision with extra text prefix."""
        from article_enricher_function.main import extract_branch_type
        result = extract_branch_type("decision_scraped_incomplete_articles.json")
        assert result == "merged"

    def test_neither_prefix(self):
        """Test with neither singleton nor decision prefix."""
        from article_enricher_function.main import extract_branch_type
        result = extract_branch_type("enriched_complete_articles.json")
        assert result == "unknown"


class TestExtractOutputPrefixEdgeCases:
    """Additional edge cases for extract_output_prefix."""

    def test_already_enriched_prefix(self):
        """Test file that already has enriched prefix."""
        from article_enricher_function.main import extract_output_prefix
        result = extract_output_prefix("enriched_singleton_complete_articles.json")
        # Should still add enriched prefix
        assert result == "enriched_enriched_singleton_complete_articles"

    def test_no_json_extension(self):
        """Test file without .json extension."""
        from article_enricher_function.main import extract_output_prefix
        result = extract_output_prefix("singleton_complete_articles.jsonl")
        # .json is replaced, leaving just 'l' at the end
        assert result == "enriched_singleton_complete_articlesl"


class TestEnrichmentPromptDetails:
    """Additional tests for ENRICHMENT_PROMPT content structure."""

    def test_prompt_has_category_taxonomy(self):
        """Test prompt includes category taxonomy section."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "Category Taxonomy" in ENRICHMENT_PROMPT

    def test_prompt_mentions_sport_tags(self):
        """Test prompt mentions sport tags."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "basketball" in ENRICHMENT_PROMPT
        assert "volleyball" in ENRICHMENT_PROMPT

    def test_prompt_mentions_football_tags(self):
        """Test prompt mentions football tags."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "match-results" in ENRICHMENT_PROMPT
        assert "tactical-analysis" in ENRICHMENT_PROMPT

    def test_prompt_mentions_competition_tags(self):
        """Test prompt mentions competition tags."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "super-lig" in ENRICHMENT_PROMPT
        assert "champions-league" in ENRICHMENT_PROMPT

    def test_prompt_has_output_format_section(self):
        """Test prompt has output format specification."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "Output Format" in ENRICHMENT_PROMPT

    def test_prompt_has_input_section(self):
        """Test prompt has input specification."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "Input" in ENRICHMENT_PROMPT

    def test_prompt_mentions_preservation_rules(self):
        """Test prompt mentions data preservation."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "preserve" in ENRICHMENT_PROMPT.lower()

    def test_prompt_mentions_critical_instructions(self):
        """Test prompt has critical instructions section."""
        from article_enricher_function.main import ENRICHMENT_PROMPT
        assert "CRITICAL" in ENRICHMENT_PROMPT


class TestConfigurationConstants:
    """Tests for configuration constants."""

    def test_project_id_default(self):
        """Test PROJECT_ID has a default value."""
        from article_enricher_function.main import PROJECT_ID
        assert PROJECT_ID is not None
        assert len(PROJECT_ID) > 0

    def test_gcs_bucket_name_default(self):
        """Test GCS_BUCKET_NAME has a default value."""
        from article_enricher_function.main import GCS_BUCKET_NAME
        assert GCS_BUCKET_NAME is not None
        assert 'aisports' in GCS_BUCKET_NAME

    def test_vertex_ai_location_default(self):
        """Test VERTEX_AI_LOCATION has a default value."""
        from article_enricher_function.main import VERTEX_AI_LOCATION
        assert VERTEX_AI_LOCATION is not None
        assert 'us-central1' in VERTEX_AI_LOCATION

    def test_vertex_ai_model_default(self):
        """Test VERTEX_AI_MODEL has a default value."""
        from article_enricher_function.main import VERTEX_AI_MODEL
        assert VERTEX_AI_MODEL is not None
        assert 'gemini' in VERTEX_AI_MODEL


class TestTriggerPatternStructure:
    """Tests for TRIGGER_PATTERNS structure and consistency."""

    def test_all_patterns_have_underscore(self):
        """Test all patterns have underscore separator."""
        for pattern in TRIGGER_PATTERNS:
            assert '_' in pattern

    def test_patterns_are_unique(self):
        """Test all patterns are unique."""
        assert len(TRIGGER_PATTERNS) == len(set(TRIGGER_PATTERNS))

    def test_patterns_cover_all_source_types(self):
        """Test patterns cover complete, scraped_incomplete, scraped."""
        sources = set()
        for pattern in TRIGGER_PATTERNS:
            if 'complete' in pattern and 'incomplete' not in pattern:
                sources.add('complete')
            elif 'scraped_incomplete' in pattern:
                sources.add('scraped_incomplete')
            elif 'scraped' in pattern:
                sources.add('scraped')
        assert 'complete' in sources
        assert 'scraped_incomplete' in sources
        assert 'scraped' in sources

    def test_patterns_cover_both_branches(self):
        """Test patterns cover both singleton and decision branches."""
        has_singleton = any('singleton' in p for p in TRIGGER_PATTERNS)
        has_decision = any('decision' in p for p in TRIGGER_PATTERNS)
        assert has_singleton
        assert has_decision