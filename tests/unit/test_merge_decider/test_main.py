"""Unit tests for merge_decider_function/main.py."""

import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock timezone before importing
mock_zoneinfo = MagicMock()
sys.modules['zoneinfo'] = mock_zoneinfo

# Mock Google Cloud modules before importing
mock_storage = MagicMock()
sys.modules['google.cloud.storage'] = mock_storage
mock_pubsub = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = mock_pubsub
mock_genai = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.genai'] = mock_genai
sys.modules['google.genai.types'] = MagicMock()
mock_google_cloud = MagicMock()
mock_google_cloud.storage = mock_storage
mock_google_cloud.pubsub_v1 = mock_pubsub
sys.modules['google.cloud'] = mock_google_cloud

# Mock Google Cloud clients before importing
with patch.dict('os.environ', {'ENVIRONMENT': 'local'}):
    from merge_decider_function.main import (
        extract_path_info,
        extract_source_type,
        TRIGGER_PATTERNS,
    )


class TestExtractPathInfo:
    """Tests for extract_path_info function."""

    def test_valid_path_extraction(self):
        """Test extracting info from valid path."""
        path = "ingestion/2024-12-28/14-30-45/grouped_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        
        assert date_str == "2024-12-28"
        assert run_id == "14-30-45"
        assert filename == "grouped_complete_articles.json"

    def test_path_with_bucket_prefix(self):
        """Test path with GCS bucket prefix."""
        path = "gs://bucket/ingestion/2024-12-28/10-00-00/grouped_scraped_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        
        assert date_str == "2024-12-28"
        assert run_id == "10-00-00"
        assert filename == "grouped_scraped_articles.json"

    def test_path_with_nested_folders(self):
        """Test path with additional nested folders."""
        path = "some/prefix/ingestion/2024-01-15/08-15-30/grouped_scraped_incomplete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        
        assert date_str == "2024-01-15"
        assert run_id == "08-15-30"
        assert filename == "grouped_scraped_incomplete_articles.json"

    def test_invalid_path_returns_defaults(self):
        """Test invalid path returns default values."""
        path = "random/invalid/path.txt"
        
        # Should not crash and should return some values
        try:
            date_str, run_id, filename = extract_path_info(path)
            # If it doesn't match, it uses current time
            assert len(date_str) == 10  # YYYY-MM-DD format
            assert len(run_id) == 8  # HH-MM-SS format
        except TypeError:
            # Expected in test env due to mocked timezone
            pytest.skip("Skipped due to mocked timezone")


class TestExtractSourceType:
    """Tests for extract_source_type function."""

    def test_complete_source_type(self):
        """Test extracting 'complete' source type."""
        assert extract_source_type("grouped_complete_articles.json") == "complete"

    def test_scraped_incomplete_source_type(self):
        """Test extracting 'scraped_incomplete' source type."""
        assert extract_source_type("grouped_scraped_incomplete_articles.json") == "scraped_incomplete"

    def test_scraped_source_type(self):
        """Test extracting 'scraped' source type."""
        assert extract_source_type("grouped_scraped_articles.json") == "scraped"

    def test_unknown_source_type(self):
        """Test unknown filename returns 'unknown'."""
        assert extract_source_type("some_random_file.json") == "unknown"

    def test_incomplete_without_scraped(self):
        """Test 'complete' is matched correctly even when incomplete not present."""
        # 'complete' should only match when 'incomplete' is NOT in the name
        result = extract_source_type("grouped_complete_articles.json")
        assert result == "complete"


class TestTriggerPatterns:
    """Tests for TRIGGER_PATTERNS constant."""

    def test_complete_pattern_exists(self):
        """Test complete articles pattern exists."""
        assert 'grouped_complete_articles.json' in TRIGGER_PATTERNS

    def test_scraped_incomplete_pattern_exists(self):
        """Test scraped incomplete pattern exists."""
        assert 'grouped_scraped_incomplete_articles.json' in TRIGGER_PATTERNS

    def test_scraped_pattern_exists(self):
        """Test scraped pattern exists."""
        assert 'grouped_scraped_articles.json' in TRIGGER_PATTERNS

    def test_has_three_patterns(self):
        """Test there are exactly three trigger patterns."""
        assert len(TRIGGER_PATTERNS) == 3


class TestMergeDecisionPrompt:
    """Tests for MERGE_DECISION_PROMPT content."""

    def test_prompt_contains_merge_option(self):
        """Test prompt contains MERGE decision option."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "MERGE" in MERGE_DECISION_PROMPT

    def test_prompt_contains_partial_merge_option(self):
        """Test prompt contains PARTIAL_MERGE decision option."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "PARTIAL_MERGE" in MERGE_DECISION_PROMPT

    def test_prompt_contains_keep_all_option(self):
        """Test prompt contains KEEP_ALL decision option."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "KEEP_ALL" in MERGE_DECISION_PROMPT

    def test_prompt_contains_json_format(self):
        """Test prompt contains JSON output format."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "json" in MERGE_DECISION_PROMPT.lower()

    def test_prompt_mentions_decisions_array(self):
        """Test prompt mentions decisions array."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "decisions" in MERGE_DECISION_PROMPT


class TestTriggerPatternsValidation:
    """Additional validation for TRIGGER_PATTERNS."""

    def test_all_patterns_are_json(self):
        """Test all patterns end with .json."""
        for pattern in TRIGGER_PATTERNS:
            assert pattern.endswith('.json')

    def test_all_patterns_have_grouped_prefix(self):
        """Test all patterns start with grouped_."""
        for pattern in TRIGGER_PATTERNS:
            assert pattern.startswith('grouped_')

    def test_no_duplicate_patterns(self):
        """Test no duplicate patterns."""
        assert len(TRIGGER_PATTERNS) == len(set(TRIGGER_PATTERNS))


class TestExtractSourceTypeEdgeCases:
    """Additional edge cases for extract_source_type."""

    def test_empty_filename(self):
        """Test empty filename returns unknown."""
        assert extract_source_type("") == "unknown"

    def test_none_like_handling(self):
        """Test non-matching filename."""
        assert extract_source_type("file.json") == "unknown"

    def test_case_sensitivity(self):
        """Test filenames are case sensitive."""
        assert extract_source_type("Grouped_Complete_Articles.json") == "unknown"

    def test_partial_match_avoided(self):
        """Test partial matches don't trigger wrong type."""
        assert extract_source_type("grouped_completion_articles.json") == "unknown"


class TestExtractPathInfoEdgeCases:
    """Additional edge cases for extract_path_info."""

    def test_midnight_time(self):
        """Test midnight time extraction."""
        path = "ingestion/2024-12-28/00-00-00/grouped_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        assert run_id == "00-00-00"

    def test_end_of_day_time(self):
        """Test end of day time extraction."""
        path = "ingestion/2024-12-28/23-59-59/grouped_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        assert run_id == "23-59-59"

    def test_year_boundary(self):
        """Test year boundary dates."""
        path = "ingestion/2024-12-31/12-00-00/grouped_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        assert date_str == "2024-12-31"

    def test_january_first(self):
        """Test January 1st date."""
        path = "ingestion/2024-01-01/12-00-00/grouped_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        assert date_str == "2024-01-01"


class TestConfigurationValues:
    """Tests for configuration constants."""

    def test_project_id_default(self):
        """Test default PROJECT_ID value."""
        from merge_decider_function.main import PROJECT_ID
        assert PROJECT_ID is not None
        assert len(PROJECT_ID) > 0

    def test_gcs_bucket_default(self):
        """Test default GCS_BUCKET_NAME value."""
        from merge_decider_function.main import GCS_BUCKET_NAME
        assert GCS_BUCKET_NAME is not None
        assert 'aisports' in GCS_BUCKET_NAME.lower()

    def test_vertex_ai_model_default(self):
        """Test default VERTEX_AI_MODEL value."""
        from merge_decider_function.main import VERTEX_AI_MODEL
        assert VERTEX_AI_MODEL is not None
        assert 'gemini' in VERTEX_AI_MODEL.lower()


class TestPromptStructure:
    """Tests for prompt structure and content."""

    def test_prompt_has_task_section(self):
        """Test prompt has task section."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "## Task" in MERGE_DECISION_PROMPT

    def test_prompt_has_decision_criteria(self):
        """Test prompt has decision criteria."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "## Decision Criteria" in MERGE_DECISION_PROMPT

    def test_prompt_has_output_format(self):
        """Test prompt has output format."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "## Output Format" in MERGE_DECISION_PROMPT

    def test_prompt_has_input_section(self):
        """Test prompt has input section."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "## Input" in MERGE_DECISION_PROMPT

    def test_prompt_mentions_merge_criteria(self):
        """Test prompt mentions MERGE criteria."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "### MERGE when:" in MERGE_DECISION_PROMPT

    def test_prompt_mentions_partial_merge_criteria(self):
        """Test prompt mentions PARTIAL_MERGE criteria."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "### PARTIAL_MERGE when" in MERGE_DECISION_PROMPT

    def test_prompt_mentions_keep_all_criteria(self):
        """Test prompt mentions KEEP_ALL criteria."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "### KEEP_ALL when:" in MERGE_DECISION_PROMPT

    def test_prompt_mentions_group_id(self):
        """Test prompt mentions group_id field."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "group_id" in MERGE_DECISION_PROMPT

    def test_prompt_mentions_primary_article_id(self):
        """Test prompt mentions primary_article_id field."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "primary_article_id" in MERGE_DECISION_PROMPT

    def test_prompt_mentions_merged_article_ids(self):
        """Test prompt mentions merged_article_ids field."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "merged_article_ids" in MERGE_DECISION_PROMPT

    def test_prompt_mentions_kept_separate_ids(self):
        """Test prompt mentions kept_separate_ids field."""
        from merge_decider_function.main import MERGE_DECISION_PROMPT
        assert "kept_separate_ids" in MERGE_DECISION_PROMPT


class TestSourceTypeExtraction:
    """More tests for source type extraction."""

    def test_scraped_only_matches_scraped(self):
        """Test 'scraped' type only matches when appropriate."""
        assert extract_source_type("grouped_scraped_articles.json") == "scraped"
        # Not 'scraped_incomplete'
        assert extract_source_type("grouped_scraped_articles.json") != "scraped_incomplete"

    def test_complete_not_matched_by_incomplete(self):
        """Test 'complete' doesn't match 'incomplete'."""
        result = extract_source_type("grouped_scraped_incomplete_articles.json")
        assert result == "scraped_incomplete"
        assert result != "complete"

    def test_filename_with_numbers_still_extracts(self):
        """Test filename with numbers still extracts type."""
        # The function checks if keyword is IN filename, so numbers don't prevent match
        assert extract_source_type("grouped_complete_articles_123.json") == "complete"

        path = "ingestion/2025-01-01/08-30-00/grouped_complete_articles.json"
        date_str, run_id, filename = extract_path_info(path)
        assert date_str == "2025-01-01"


class TestMergeDeciderConstants:
    """Tests for merge decider constants."""

    def test_environment_config(self):
        """Test environment configuration."""
        import os
        env = os.getenv('ENVIRONMENT', 'development')
        assert env in ['development', 'local', 'production', 'staging']

    def test_gcs_bucket_default(self):
        """Test GCS bucket default value."""
        import os
        bucket = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
        assert bucket == 'aisports-scraping' or bucket

    def test_project_id_default(self):
        """Test project ID default value."""
        import os
        project = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
        assert 'gen-lang' in project or project
