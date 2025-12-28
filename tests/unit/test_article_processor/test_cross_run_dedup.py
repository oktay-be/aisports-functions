"""Unit tests for article_processor_function/cross_run_dedup.py."""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch


class TestCrossRunDeduplicatorInit:
    """Tests for CrossRunDeduplicator initialization."""

    def test_default_region_thresholds(self):
        """Test default region thresholds."""
        from article_processor_function.cross_run_dedup import (
            CrossRunDeduplicator, DEFAULT_REGION_THRESHOLDS
        )
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        assert dedup.region_thresholds == DEFAULT_REGION_THRESHOLDS

    def test_custom_region_thresholds(self):
        """Test custom region thresholds."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        custom_thresholds = {'tr': 0.8, 'eu': 0.85}
        dedup = CrossRunDeduplicator(mock_client, 'bucket', region_thresholds=custom_thresholds)
        
        assert dedup.region_thresholds == custom_thresholds

    def test_default_dedup_depth(self):
        """Test default dedup depth is 1."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        assert dedup.dedup_depth == 1

    def test_custom_dedup_depth(self):
        """Test custom dedup depth."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket', dedup_depth=5)
        
        assert dedup.dedup_depth == 5

    def test_dedup_depth_minimum_is_one(self):
        """Test dedup depth minimum is enforced to 1."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket', dedup_depth=0)
        
        assert dedup.dedup_depth == 1

    def test_fallback_threshold(self):
        """Test fallback threshold is EU threshold."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        assert dedup.fallback_threshold == dedup.region_thresholds.get('eu', 0.9)


class TestGetThresholdForRegion:
    """Tests for CrossRunDeduplicator.get_threshold_for_region method."""

    def test_tr_region_threshold(self):
        """Test TR region returns TR threshold."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        threshold = dedup.get_threshold_for_region('tr')
        assert threshold == 0.85

    def test_eu_region_threshold(self):
        """Test EU region returns EU threshold."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        threshold = dedup.get_threshold_for_region('eu')
        assert threshold == 0.9

    def test_unknown_region_returns_fallback(self):
        """Test unknown region returns fallback threshold."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        threshold = dedup.get_threshold_for_region('us')
        assert threshold == dedup.fallback_threshold

    def test_none_region_returns_fallback(self):
        """Test None region returns fallback threshold."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        threshold = dedup.get_threshold_for_region(None)
        assert threshold == dedup.fallback_threshold

    def test_case_insensitive_region(self):
        """Test region lookup is case insensitive."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        assert dedup.get_threshold_for_region('TR') == 0.85
        assert dedup.get_threshold_for_region('Eu') == 0.9


class TestComputeMaxSimilarity:
    """Tests for CrossRunDeduplicator.compute_max_similarity method."""

    def test_identical_embeddings(self):
        """Test identical embeddings have max similarity 1."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        new_emb = np.array([[1.0, 0.0, 0.0]])
        prev_emb = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        
        max_sim, max_idx = dedup.compute_max_similarity(new_emb, prev_emb)
        
        assert np.allclose(max_sim[0], 1.0)
        assert max_idx[0] == 0

    def test_empty_previous_embeddings(self):
        """Test empty previous embeddings return zeros."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        new_emb = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        prev_emb = np.array([])
        
        max_sim, max_idx = dedup.compute_max_similarity(new_emb, prev_emb)
        
        assert np.allclose(max_sim, [0.0, 0.0])

    def test_orthogonal_embeddings(self):
        """Test orthogonal embeddings have similarity 0."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        new_emb = np.array([[1.0, 0.0, 0.0]])
        prev_emb = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        
        max_sim, max_idx = dedup.compute_max_similarity(new_emb, prev_emb)
        
        assert np.allclose(max_sim[0], 0.0)

    def test_returns_correct_shapes(self):
        """Test returns arrays with correct shapes."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        new_emb = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        prev_emb = np.array([[1.0, 0.0], [0.0, 1.0]])
        
        max_sim, max_idx = dedup.compute_max_similarity(new_emb, prev_emb)
        
        assert max_sim.shape == (3,)
        assert max_idx.shape == (3,)


class TestDefaultRegionThresholds:
    """Tests for DEFAULT_REGION_THRESHOLDS constant."""

    def test_tr_threshold(self):
        """Test TR default threshold."""
        from article_processor_function.cross_run_dedup import DEFAULT_REGION_THRESHOLDS
        
        assert DEFAULT_REGION_THRESHOLDS['tr'] == 0.85

    def test_eu_threshold(self):
        """Test EU default threshold."""
        from article_processor_function.cross_run_dedup import DEFAULT_REGION_THRESHOLDS
        
        assert DEFAULT_REGION_THRESHOLDS['eu'] == 0.9

    def test_tr_less_strict_than_eu(self):
        """Test TR threshold is less strict than EU."""
        from article_processor_function.cross_run_dedup import DEFAULT_REGION_THRESHOLDS
        
        # Lower threshold = more lenient (allows more duplicates)
        assert DEFAULT_REGION_THRESHOLDS['tr'] < DEFAULT_REGION_THRESHOLDS['eu']


class TestCrossRunDeduplicatorEdgeCases:
    """Edge case tests for CrossRunDeduplicator."""

    def test_negative_dedup_depth_becomes_one(self):
        """Test negative dedup depth is corrected to 1."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket', dedup_depth=-5)
        
        assert dedup.dedup_depth == 1

    def test_large_dedup_depth(self):
        """Test large dedup depth is allowed."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket', dedup_depth=365)
        
        assert dedup.dedup_depth == 365

    def test_empty_region_thresholds(self):
        """Test empty region thresholds dict."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket', region_thresholds={})
        
        # Should still have fallback
        assert dedup.fallback_threshold >= 0.0

    def test_bucket_name_stored(self):
        """Test bucket name is stored."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'my-bucket')
        
        assert dedup.bucket_name == 'my-bucket'

    def test_storage_client_stored(self):
        """Test storage client is stored."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        assert dedup.storage_client == mock_client


class TestComputeMaxSimilarityEdgeCases:
    """Edge case tests for compute_max_similarity."""

    def test_single_new_embedding(self):
        """Test with single new embedding."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        new_emb = np.array([[1.0, 0.0]])
        prev_emb = np.array([[0.5, 0.5], [0.8, 0.2]])
        
        max_sim, max_idx = dedup.compute_max_similarity(new_emb, prev_emb)
        
        assert len(max_sim) == 1
        assert len(max_idx) == 1

    def test_single_previous_embedding(self):
        """Test with single previous embedding."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        new_emb = np.array([[1.0, 0.0], [0.0, 1.0]])
        prev_emb = np.array([[1.0, 0.0]])
        
        max_sim, max_idx = dedup.compute_max_similarity(new_emb, prev_emb)
        
        assert len(max_sim) == 2
        assert all(idx == 0 for idx in max_idx)  # All match single prev embedding

    def test_high_dimensional_embeddings(self):
        """Test with high dimensional embeddings."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        # 768-dimensional embeddings (typical for text models)
        np.random.seed(42)
        new_emb = np.random.randn(10, 768)
        prev_emb = np.random.randn(100, 768)
        
        # Normalize for cosine similarity
        new_emb = new_emb / np.linalg.norm(new_emb, axis=1, keepdims=True)
        prev_emb = prev_emb / np.linalg.norm(prev_emb, axis=1, keepdims=True)
        
        max_sim, max_idx = dedup.compute_max_similarity(new_emb, prev_emb)
        
        assert max_sim.shape == (10,)
        assert max_idx.shape == (10,)
        # All similarities should be in valid range
        assert all(-1.0 <= s <= 1.0 for s in max_sim)


class TestGetThresholdForRegionEdgeCases:
    """Edge case tests for get_threshold_for_region."""

    def test_empty_string_region(self):
        """Test empty string region returns fallback."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        # Empty string should return fallback
        threshold = dedup.get_threshold_for_region('')
        assert threshold == dedup.fallback_threshold

    def test_whitespace_region(self):
        """Test whitespace region returns fallback."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        threshold = dedup.get_threshold_for_region('  ')
        # Whitespace should not match any region
        assert threshold == dedup.fallback_threshold

    def test_mixed_case_region(self):
        """Test mixed case region handling."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        # All case variations should work
        assert dedup.get_threshold_for_region('TR') == dedup.get_threshold_for_region('tr')
        assert dedup.get_threshold_for_region('eU') == dedup.get_threshold_for_region('eu')

class TestComputeMaxSimilarityNormalization:
    """Tests for normalization in compute_max_similarity."""

    def test_handles_zero_norm_vectors(self):
        """Test handles zero norm vectors without division error."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        new_emb = np.array([[0.0, 0.0], [1.0, 0.0]])
        prev_emb = np.array([[1.0, 0.0]])
        
        # Should not raise ZeroDivisionError
        max_sim, max_idx = dedup.compute_max_similarity(new_emb, prev_emb)
        
        assert len(max_sim) == 2

    def test_normalization_preserves_direction(self):
        """Test that normalization preserves similarity relationships."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        dedup = CrossRunDeduplicator(mock_client, 'bucket')
        
        # Unnormalized embeddings
        new_emb = np.array([[2.0, 0.0], [0.0, 3.0]])
        prev_emb = np.array([[1.0, 0.0], [0.0, 1.0]])
        
        max_sim, max_idx = dedup.compute_max_similarity(new_emb, prev_emb)
        
        # First new should match first prev, second new should match second prev
        assert max_idx[0] == 0
        assert max_idx[1] == 1


class TestRegionThresholdValues:
    """Tests for threshold values."""

    def test_thresholds_in_valid_range(self):
        """Test all thresholds are in valid range [0, 1]."""
        from article_processor_function.cross_run_dedup import DEFAULT_REGION_THRESHOLDS
        
        for region, threshold in DEFAULT_REGION_THRESHOLDS.items():
            assert 0.0 <= threshold <= 1.0, f"Invalid threshold for {region}"

    def test_custom_thresholds_override_defaults(self):
        """Test custom thresholds completely override defaults."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        custom = {'tr': 0.5}  # Only TR
        dedup = CrossRunDeduplicator(mock_client, 'bucket', region_thresholds=custom)
        
        assert dedup.region_thresholds['tr'] == 0.5
        assert 'eu' not in dedup.region_thresholds


class TestFallbackThreshold:
    """Tests for fallback threshold behavior."""

    def test_fallback_when_custom_missing_eu(self):
        """Test fallback when custom thresholds don't include EU."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        custom = {'tr': 0.5}
        dedup = CrossRunDeduplicator(mock_client, 'bucket', region_thresholds=custom)
        
        # Fallback should be 0.9 (default EU threshold from code)
        assert dedup.fallback_threshold == 0.9

    def test_fallback_with_custom_eu(self):
        """Test fallback uses custom EU threshold when provided."""
        from article_processor_function.cross_run_dedup import CrossRunDeduplicator
        
        mock_client = MagicMock()
        custom = {'eu': 0.75, 'tr': 0.6}
        dedup = CrossRunDeduplicator(mock_client, 'bucket', region_thresholds=custom)
        
        assert dedup.fallback_threshold == 0.75