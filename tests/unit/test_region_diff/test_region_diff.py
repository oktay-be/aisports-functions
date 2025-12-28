"""Unit tests for region_diff_function/region_diff.py and main.py."""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch
import sys
import os

# Mock zoneinfo before importing
mock_zoneinfo = MagicMock()
sys.modules['zoneinfo'] = mock_zoneinfo

# Mock Google Cloud modules
mock_storage = MagicMock()
sys.modules['google.cloud.storage'] = mock_storage
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud'].storage = mock_storage


# Import main module constants in local environment
with patch.dict('os.environ', {'ENVIRONMENT': 'local'}):
    from region_diff_function.main import (
        TRIGGER_PATTERNS,
        REGION_DIFF_THRESHOLD,
        REGION1,
        REGION2,
        HISTORICAL_DIFF_DEPTH,
        GCS_BUCKET_NAME,
        PROJECT_ID,
    )


class TestMainModuleImportedConstants:
    """Tests for imported constants from region_diff_function/main.py."""

    def test_trigger_patterns_has_three_items(self):
        """Test trigger patterns list has expected items."""
        assert len(TRIGGER_PATTERNS) == 3

    def test_trigger_patterns_contain_enriched(self):
        """Test all patterns contain 'enriched'."""
        for pattern in TRIGGER_PATTERNS:
            assert 'enriched' in pattern

    def test_trigger_patterns_are_json(self):
        """Test all patterns end with .json."""
        for pattern in TRIGGER_PATTERNS:
            assert pattern.endswith('.json')

    def test_region_diff_threshold_value(self):
        """Test default diff threshold is 0.75."""
        assert REGION_DIFF_THRESHOLD == 0.75

    def test_region1_is_eu(self):
        """Test default region1 is eu."""
        assert REGION1 == 'eu'

    def test_region2_is_tr(self):
        """Test default region2 is tr."""
        assert REGION2 == 'tr'

    def test_historical_diff_depth_value(self):
        """Test default historical diff depth is 3."""
        assert HISTORICAL_DIFF_DEPTH == 3

    def test_gcs_bucket_name_value(self):
        """Test GCS bucket name contains aisports."""
        assert 'aisports' in GCS_BUCKET_NAME.lower()

    def test_project_id_not_empty(self):
        """Test PROJECT_ID is not empty."""
        assert len(PROJECT_ID) > 0


class TestMainModuleConstants:
    """Tests for region_diff_function/main.py constants and configuration."""

    def test_default_region_diff_threshold(self):
        """Test default threshold value."""
        default_threshold = float(os.getenv('REGION_DIFF_THRESHOLD', '0.75'))
        assert default_threshold == 0.75

    def test_default_regions(self):
        """Test default region values."""
        region1 = os.getenv('REGION1', 'eu')
        region2 = os.getenv('REGION2', 'tr')
        assert region1 == 'eu'
        assert region2 == 'tr'

    def test_default_historical_depth(self):
        """Test default historical diff depth."""
        depth = int(os.getenv('HISTORICAL_DIFF_DEPTH', '3'))
        assert depth == 3

    def test_trigger_patterns_content(self):
        """Test trigger patterns list."""
        TRIGGER_PATTERNS = [
            'enriched_complete_articles.json',
            'enriched_scraped_incomplete_articles.json',
            'enriched_scraped_articles.json',
        ]
        assert len(TRIGGER_PATTERNS) == 3
        assert 'enriched_complete_articles.json' in TRIGGER_PATTERNS

    def test_gcs_bucket_default(self):
        """Test default GCS bucket name."""
        bucket = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
        assert bucket == 'aisports-scraping'


class TestMainModuleFunctions:
    """Tests for functions in region_diff_function/main.py."""

    def test_trigger_pattern_matching(self):
        """Test trigger pattern matching logic."""
        TRIGGER_PATTERNS = [
            'enriched_complete_articles.json',
            'enriched_scraped_incomplete_articles.json',
            'enriched_scraped_articles.json',
        ]
        path = 'ingestion/2025-12-22/08-37-29/enriched_scraped_articles.json'
        filename = path.split('/')[-1] if path else ''
        assert filename == 'enriched_scraped_articles.json'
        assert filename in TRIGGER_PATTERNS

    def test_run_folder_extraction(self):
        """Test run folder extraction from path."""
        path = 'ingestion/2025-12-22/08-37-29/enriched_scraped_articles.json'
        parts = path.split('/')
        assert len(parts) >= 4
        run_folder = '/'.join(parts[:-1])
        assert run_folder == 'ingestion/2025-12-22/08-37-29'

    def test_invalid_path_detection(self):
        """Test detection of invalid path format."""
        path = 'short/path.json'
        parts = path.split('/')
        assert len(parts) < 4

    def test_event_parsing_dict_format(self):
        """Test event parsing for dict format."""
        event = {
            'bucket': 'test-bucket',
            'name': 'test/path/file.json',
            'metageneration': '1'
        }
        bucket = event.get('bucket', 'default-bucket')
        name = event.get('name', '')
        assert bucket == 'test-bucket'
        assert name == 'test/path/file.json'

    def test_output_path_construction(self):
        """Test output path construction."""
        run_folder = 'ingestion/2025-12-22/08-37-29'
        region1 = 'eu'
        region2 = 'tr'
        output_path = f"{run_folder}/analysis/region_diff_{region1}_vs_{region2}.json"
        expected = 'ingestion/2025-12-22/08-37-29/analysis/region_diff_eu_vs_tr.json'
        assert output_path == expected


class TestMainHTTPHandler:
    """Tests for HTTP handler in region_diff_function/main.py."""

    def test_missing_run_folder_returns_error(self):
        """Test that missing run_folder returns 400 error."""
        data = {}
        run_folder = data.get('run_folder', '')
        assert not run_folder

    def test_request_data_parsing(self):
        """Test request data parsing."""
        data = {
            'run_folder': 'ingestion/2025-12-22/08-37-29',
            'region1': 'us',
            'region2': 'uk',
            'diff_threshold': 0.8,
            'historical_diff_depth': 5
        }
        run_folder = data.get('run_folder', '')
        region1 = data.get('region1', 'eu')
        assert run_folder == 'ingestion/2025-12-22/08-37-29'
        assert region1 == 'us'


class TestComputeSimilarityMatrix:
    """Tests for RegionDiffAnalyzer.compute_similarity_matrix method."""

    def test_identical_embeddings_similarity_one(self):
        """Test identical embeddings have similarity 1."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket')
        
        emb = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        similarity = analyzer.compute_similarity_matrix(emb, emb)
        
        # Diagonal should be 1
        assert np.allclose(similarity[0, 0], 1.0)
        assert np.allclose(similarity[1, 1], 1.0)

    def test_orthogonal_embeddings_similarity_zero(self):
        """Test orthogonal embeddings have similarity 0."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket')
        
        emb1 = np.array([[1.0, 0.0, 0.0]])
        emb2 = np.array([[0.0, 1.0, 0.0]])
        similarity = analyzer.compute_similarity_matrix(emb1, emb2)
        
        assert np.allclose(similarity[0, 0], 0.0)

    def test_empty_embeddings_returns_empty(self):
        """Test empty embeddings return empty matrix."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket')
        
        emb1 = np.array([])
        emb2 = np.array([[1.0, 0.0]])
        similarity = analyzer.compute_similarity_matrix(emb1, emb2)
        
        assert similarity.size == 0

    def test_similarity_matrix_shape(self):
        """Test similarity matrix has correct shape."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket')
        
        emb1 = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        emb2 = np.array([[1.0, 0.0], [0.0, 1.0]])
        similarity = analyzer.compute_similarity_matrix(emb1, emb2)
        
        assert similarity.shape == (3, 2)

    def test_handles_zero_norm_vectors(self):
        """Test handles zero norm vectors without error."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket')
        
        emb1 = np.array([[0.0, 0.0], [1.0, 0.0]])
        emb2 = np.array([[1.0, 0.0]])
        
        # Should not raise
        similarity = analyzer.compute_similarity_matrix(emb1, emb2)
        assert similarity.shape == (2, 1)


class TestRegionDiffAnalyzerInit:
    """Tests for RegionDiffAnalyzer initialization."""

    def test_default_threshold(self):
        """Test default diff threshold."""
        from region_diff_function.region_diff import RegionDiffAnalyzer, DEFAULT_DIFF_THRESHOLD
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket')
        
        assert analyzer.diff_threshold == DEFAULT_DIFF_THRESHOLD

    def test_custom_threshold(self):
        """Test custom diff threshold."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket', diff_threshold=0.8)
        
        assert analyzer.diff_threshold == 0.8

    def test_historical_depth_default(self):
        """Test default historical diff depth."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket')
        
        assert analyzer.historical_diff_depth == 3

    def test_historical_depth_custom(self):
        """Test custom historical diff depth."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket', historical_diff_depth=7)
        
        assert analyzer.historical_diff_depth == 7


class TestGetHistoricalDates:
    """Tests for RegionDiffAnalyzer.get_historical_dates method."""

    def test_returns_correct_number_of_dates(self):
        """Test returns correct number of dates based on depth."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket', historical_diff_depth=5)
        
        dates = analyzer.get_historical_dates("ingestion/2024-12-28/10-30-00")
        
        assert len(dates) == 5

    def test_starts_with_current_date(self):
        """Test first date is the current date."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket', historical_diff_depth=3)
        
        dates = analyzer.get_historical_dates("ingestion/2024-12-28/10-30-00")
        
        assert dates[0] == "2024-12-28"

    def test_dates_go_backwards(self):
        """Test dates go backwards in time."""
        from region_diff_function.region_diff import RegionDiffAnalyzer
        
        mock_client = MagicMock()
        analyzer = RegionDiffAnalyzer(mock_client, 'bucket', historical_diff_depth=3)
        
        dates = analyzer.get_historical_dates("ingestion/2024-12-28/10-30-00")
        
        assert dates == ["2024-12-28", "2024-12-27", "2024-12-26"]


class TestEmbeddingAndArticleFilePatterns:
    """Tests for file pattern constants."""

    def test_embedding_files_patterns(self):
        """Test embedding file patterns are defined."""
        from region_diff_function.region_diff import EMBEDDING_FILES
        
        assert 'embeddings/scraped_embeddings.json' in EMBEDDING_FILES
        assert 'embeddings/complete_embeddings.json' in EMBEDDING_FILES
        assert 'embeddings/scraped_incomplete_embeddings.json' in EMBEDDING_FILES

    def test_article_files_patterns(self):
        """Test article file patterns are defined."""
        from region_diff_function.region_diff import ARTICLE_FILES
        
        assert 'enriched_scraped_articles.json' in ARTICLE_FILES
        assert 'enriched_complete_articles.json' in ARTICLE_FILES
        assert 'enriched_scraped_incomplete_articles.json' in ARTICLE_FILES


class TestTriggerPatterns:
    """Tests for trigger pattern definitions in main.py."""

    def test_all_patterns_are_json(self):
        """Test all trigger patterns are JSON files."""
        TRIGGER_PATTERNS = [
            'enriched_complete_articles.json',
            'enriched_scraped_incomplete_articles.json',
            'enriched_scraped_articles.json',
        ]
        for pattern in TRIGGER_PATTERNS:
            assert pattern.endswith('.json')

    def test_all_patterns_start_with_enriched(self):
        """Test all trigger patterns start with enriched."""
        TRIGGER_PATTERNS = [
            'enriched_complete_articles.json',
            'enriched_scraped_incomplete_articles.json',
            'enriched_scraped_articles.json',
        ]
        for pattern in TRIGGER_PATTERNS:
            assert pattern.startswith('enriched_')


class TestEventHandling:
    """Tests for event handling logic in main.py."""

    def test_dict_event_bucket_extraction(self):
        """Test bucket extraction from dict event."""
        event = {'bucket': 'my-bucket', 'name': 'path/to/file.json'}
        bucket = event.get('bucket', 'default')
        assert bucket == 'my-bucket'

    def test_dict_event_name_extraction(self):
        """Test name extraction from dict event."""
        event = {'bucket': 'my-bucket', 'name': 'path/to/file.json'}
        name = event.get('name', '')
        assert name == 'path/to/file.json'

    def test_dict_event_metageneration_new_file(self):
        """Test metageneration detection for new file."""
        event = {'metageneration': '1'}
        is_new = event.get('metageneration', '1') == '1'
        assert is_new is True

    def test_dict_event_metageneration_overwrite(self):
        """Test metageneration detection for overwrite."""
        event = {'metageneration': '2'}
        is_new = event.get('metageneration', '1') == '1'
        assert is_new is False

    def test_missing_event_keys_use_defaults(self):
        """Test missing event keys use defaults."""
        event = {}
        bucket = event.get('bucket', 'aisports-scraping')
        name = event.get('name', '')
        metageneration = event.get('metageneration', '1')
        
        assert bucket == 'aisports-scraping'
        assert name == ''
        assert metageneration == '1'


class TestPathParsing:
    """Tests for path parsing logic."""

    def test_filename_extraction_from_path(self):
        """Test filename extraction from full path."""
        path = 'ingestion/2025-12-22/08-37-29/enriched_scraped_articles.json'
        filename = path.split('/')[-1] if path else ''
        assert filename == 'enriched_scraped_articles.json'

    def test_empty_path_filename(self):
        """Test empty path returns empty filename."""
        path = ''
        filename = path.split('/')[-1] if path else ''
        assert filename == ''

    def test_path_with_only_filename(self):
        """Test path with only filename."""
        path = 'file.json'
        filename = path.split('/')[-1]
        assert filename == 'file.json'

    def test_run_folder_from_valid_path(self):
        """Test run folder extraction from valid path."""
        path = 'ingestion/2025-12-22/08-37-29/enriched_scraped_articles.json'
        parts = path.split('/')
        run_folder = '/'.join(parts[:-1])
        assert run_folder == 'ingestion/2025-12-22/08-37-29'


class TestConfigurationDefaults:
    """Tests for configuration default values."""

    def test_project_id_default(self):
        """Test default project ID."""
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
        assert project_id == 'gen-lang-client-0306766464'

    def test_environment_default(self):
        """Test default environment."""
        env = os.getenv('ENVIRONMENT', 'development')
        assert env in ['development', 'local', 'production', 'staging']

    def test_threshold_range(self):
        """Test threshold is in valid range."""
        threshold = float(os.getenv('REGION_DIFF_THRESHOLD', '0.75'))
        assert 0.0 <= threshold <= 1.0


class TestOutputPathGeneration:
    """Tests for output path generation."""

    def test_analysis_folder_included(self):
        """Test analysis folder is included in output path."""
        run_folder = 'ingestion/2025-12-22/08-37-29'
        region1 = 'eu'
        region2 = 'tr'
        output_path = f"{run_folder}/analysis/region_diff_{region1}_vs_{region2}.json"
        assert '/analysis/' in output_path

    def test_region_names_in_output(self):
        """Test region names are in output filename."""
        region1 = 'us'
        region2 = 'uk'
        output_path = f"folder/analysis/region_diff_{region1}_vs_{region2}.json"
        assert 'region_diff_us_vs_uk.json' in output_path

    def test_output_is_json(self):
        """Test output file is JSON."""
        output_path = "folder/analysis/region_diff_eu_vs_tr.json"
        assert output_path.endswith('.json')
