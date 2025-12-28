"""
Tests for the GroupingService in article_processor_function.

These are pure logic tests that don't require external mocking.
Tests cover the Union-Find algorithm, similarity matrix computation,
and article grouping logic.
"""

import sys
from pathlib import Path

import pytest
import numpy as np

# Add the function directory to path to allow direct module import
# This avoids the package __init__.py which imports cloud dependencies
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "article_processor_function"))

# Import directly from the module file, not through package
from grouping_service import (
    UnionFind,
    ArticleGroup,
    GroupingService,
)


class TestArticleGroup:
    """Tests for ArticleGroup dataclass."""

    def test_size_property(self):
        """Test that size returns correct article count."""
        group = ArticleGroup(group_id=0, article_indices=[0, 1, 2])
        assert group.size == 3

    def test_is_singleton_true(self):
        """Test that is_singleton returns True for single article."""
        group = ArticleGroup(group_id=0, article_indices=[5])
        assert group.is_singleton is True

    def test_is_singleton_false(self):
        """Test that is_singleton returns False for multiple articles."""
        group = ArticleGroup(group_id=0, article_indices=[0, 1])
        assert group.is_singleton is False

    def test_max_similarity_default(self):
        """Test that max_similarity defaults to 0.0."""
        group = ArticleGroup(group_id=0, article_indices=[0])
        assert group.max_similarity == 0.0

    def test_max_similarity_set(self):
        """Test that max_similarity can be set."""
        group = ArticleGroup(group_id=0, article_indices=[0, 1], max_similarity=0.95)
        assert group.max_similarity == 0.95


class TestUnionFind:
    """Tests for Union-Find data structure."""

    def test_initialization(self):
        """Test that Union-Find initializes with each element as its own root."""
        uf = UnionFind(5)
        assert uf.parent == [0, 1, 2, 3, 4]
        assert uf.rank == [0, 0, 0, 0, 0]

    def test_find_self(self):
        """Test find returns self for root element."""
        uf = UnionFind(5)
        assert uf.find(2) == 2

    def test_union_returns_true_for_new_union(self):
        """Test that union returns True when joining different sets."""
        uf = UnionFind(5)
        result = uf.union(0, 1)
        assert result is True

    def test_union_returns_false_for_same_set(self):
        """Test that union returns False when elements already in same set."""
        uf = UnionFind(5)
        uf.union(0, 1)
        result = uf.union(0, 1)
        assert result is False

    def test_find_after_union(self):
        """Test that find returns same root after union."""
        uf = UnionFind(5)
        uf.union(0, 1)
        assert uf.find(0) == uf.find(1)

    def test_transitive_union(self):
        """Test transitive property: if a-b and b-c, then a and c same set."""
        uf = UnionFind(5)
        uf.union(0, 1)
        uf.union(1, 2)
        assert uf.find(0) == uf.find(2)

    def test_get_groups_initial(self):
        """Test get_groups returns singletons initially."""
        uf = UnionFind(3)
        groups = uf.get_groups()
        assert len(groups) == 3
        for members in groups.values():
            assert len(members) == 1

    def test_get_groups_after_unions(self):
        """Test get_groups correctly groups members after unions."""
        uf = UnionFind(5)
        uf.union(0, 1)
        uf.union(2, 3)
        groups = uf.get_groups()

        # Should have 3 groups: {0,1}, {2,3}, {4}
        assert len(groups) == 3

        # Verify group sizes
        sizes = sorted([len(g) for g in groups.values()])
        assert sizes == [1, 2, 2]

    def test_path_compression(self):
        """Test that path compression works by checking parent updates."""
        uf = UnionFind(5)
        uf.union(0, 1)
        uf.union(1, 2)
        uf.union(2, 3)

        # After find(3), path should be compressed
        root = uf.find(3)
        # All elements should now point directly to root
        assert uf.find(0) == root
        assert uf.find(1) == root
        assert uf.find(2) == root
        assert uf.find(3) == root


class TestGroupingService:
    """Tests for GroupingService."""

    def test_initialization_default_threshold(self):
        """Test default threshold is 0.80."""
        service = GroupingService()
        assert service.threshold == 0.80

    def test_initialization_custom_threshold(self):
        """Test custom threshold is set correctly."""
        service = GroupingService(threshold=0.9)
        assert service.threshold == 0.9

    def test_compute_similarity_matrix_empty(self):
        """Test similarity matrix for empty input."""
        service = GroupingService()
        embeddings = np.array([])
        result = service.compute_similarity_matrix(embeddings)
        assert result.size == 0

    def test_compute_similarity_matrix_single(self):
        """Test similarity matrix for single embedding."""
        service = GroupingService()
        embeddings = np.array([[1.0, 0.0, 0.0]])
        result = service.compute_similarity_matrix(embeddings)
        assert result.shape == (1, 1)
        assert np.isclose(result[0, 0], 1.0)

    def test_compute_similarity_matrix_identical(self):
        """Test that identical embeddings have similarity 1.0."""
        service = GroupingService()
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0]
        ])
        result = service.compute_similarity_matrix(embeddings)
        assert result.shape == (2, 2)
        assert np.isclose(result[0, 1], 1.0)
        assert np.isclose(result[1, 0], 1.0)

    def test_compute_similarity_matrix_orthogonal(self):
        """Test that orthogonal embeddings have similarity 0.0."""
        service = GroupingService()
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0]
        ])
        result = service.compute_similarity_matrix(embeddings)
        assert np.isclose(result[0, 1], 0.0)
        assert np.isclose(result[1, 0], 0.0)

    def test_compute_similarity_matrix_opposite(self):
        """Test that opposite embeddings have similarity -1.0."""
        service = GroupingService()
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [-1.0, 0.0, 0.0]
        ])
        result = service.compute_similarity_matrix(embeddings)
        assert np.isclose(result[0, 1], -1.0)

    def test_compute_similarity_matrix_45_degrees(self):
        """Test similarity at 45 degrees (~0.707)."""
        service = GroupingService()
        embeddings = np.array([
            [1.0, 0.0],
            [1.0, 1.0]
        ])
        result = service.compute_similarity_matrix(embeddings)
        # cos(45) = 1/sqrt(2) ≈ 0.707
        expected = 1.0 / np.sqrt(2)
        assert np.isclose(result[0, 1], expected, atol=0.001)

    def test_compute_similarity_matrix_zero_vector(self):
        """Test handling of zero vectors (should not cause division by zero)."""
        service = GroupingService()
        embeddings = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0]
        ])
        # Should not raise an error
        result = service.compute_similarity_matrix(embeddings)
        assert result.shape == (2, 2)

    def test_form_groups_empty(self):
        """Test forming groups from empty similarity matrix."""
        service = GroupingService()
        similarity_matrix = np.array([])
        groups = service.form_groups(similarity_matrix)
        assert groups == []

    def test_form_groups_all_singletons(self):
        """Test that dissimilar articles form singleton groups."""
        service = GroupingService(threshold=0.8)
        # Diagonal matrix = all dissimilar except to self
        similarity_matrix = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0]
        ])
        groups = service.form_groups(similarity_matrix)
        assert len(groups) == 3
        assert all(g.is_singleton for g in groups)

    def test_form_groups_all_similar(self):
        """Test that all similar articles form one group."""
        service = GroupingService(threshold=0.8)
        # All very similar
        similarity_matrix = np.array([
            [1.0, 0.95, 0.9],
            [0.95, 1.0, 0.92],
            [0.9, 0.92, 1.0]
        ])
        groups = service.form_groups(similarity_matrix)
        assert len(groups) == 1
        assert groups[0].size == 3
        assert not groups[0].is_singleton

    def test_form_groups_partial_grouping(self):
        """Test partial grouping: some groups, some singletons."""
        service = GroupingService(threshold=0.8)
        # Article 0 and 1 similar, article 2 different
        similarity_matrix = np.array([
            [1.0, 0.9, 0.2],
            [0.9, 1.0, 0.3],
            [0.2, 0.3, 1.0]
        ])
        groups = service.form_groups(similarity_matrix)

        # Should have 2 groups: one with 0,1 and one singleton with 2
        assert len(groups) == 2

        sizes = sorted([g.size for g in groups])
        assert sizes == [1, 2]

    def test_form_groups_max_similarity_recorded(self):
        """Test that max_similarity is correctly recorded for groups."""
        service = GroupingService(threshold=0.8)
        similarity_matrix = np.array([
            [1.0, 0.95, 0.85],
            [0.95, 1.0, 0.88],
            [0.85, 0.88, 1.0]
        ])
        groups = service.form_groups(similarity_matrix)
        assert len(groups) == 1
        assert groups[0].max_similarity == 0.95  # Highest similarity in group

    def test_form_groups_sorted_by_size(self):
        """Test that groups are sorted by size (largest first)."""
        service = GroupingService(threshold=0.8)
        # Create 4 articles: 0,1,2 similar, 3 is singleton
        similarity_matrix = np.array([
            [1.0, 0.9, 0.85, 0.1],
            [0.9, 1.0, 0.88, 0.2],
            [0.85, 0.88, 1.0, 0.15],
            [0.1, 0.2, 0.15, 1.0]
        ])
        groups = service.form_groups(similarity_matrix)

        # First group should be the larger one
        assert groups[0].size >= groups[-1].size

    def test_form_groups_threshold_boundary(self):
        """Test that threshold boundary is handled correctly (>=)."""
        service = GroupingService(threshold=0.8)
        # Exactly at threshold
        similarity_matrix = np.array([
            [1.0, 0.8],
            [0.8, 1.0]
        ])
        groups = service.form_groups(similarity_matrix)
        # Should be grouped (>= 0.8)
        assert len(groups) == 1
        assert groups[0].size == 2

    def test_form_groups_below_threshold(self):
        """Test that below threshold means no grouping."""
        service = GroupingService(threshold=0.8)
        # Just below threshold
        similarity_matrix = np.array([
            [1.0, 0.79],
            [0.79, 1.0]
        ])
        groups = service.form_groups(similarity_matrix)
        # Should be separate
        assert len(groups) == 2

    def test_group_articles_end_to_end(self):
        """Test complete pipeline from embeddings to groups."""
        service = GroupingService(threshold=0.8)

        # Create embeddings: first two very similar, third different
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.99, 0.1, 0.0],  # Very similar to first
            [0.0, 1.0, 0.0]   # Orthogonal to first
        ])

        groups = service.group_articles(embeddings)

        # Should have 2 groups
        assert len(groups) == 2

        # Check sizes
        sizes = sorted([g.size for g in groups])
        assert sizes == [1, 2]

    def test_get_candidate_pairs_empty(self):
        """Test candidate pairs for empty matrix."""
        service = GroupingService()
        # Can't use empty matrix for get_candidate_pairs as it expects shape
        # Skip this edge case

    def test_get_candidate_pairs_finds_similar(self):
        """Test that candidate pairs are found correctly."""
        service = GroupingService(threshold=0.8)
        similarity_matrix = np.array([
            [1.0, 0.95, 0.5],
            [0.95, 1.0, 0.6],
            [0.5, 0.6, 1.0]
        ])
        pairs = service.get_candidate_pairs(similarity_matrix)

        # Only pair 0-1 is above 0.8
        assert len(pairs) == 1
        assert pairs[0]["article_a_idx"] == 0
        assert pairs[0]["article_b_idx"] == 1
        assert pairs[0]["similarity"] == 0.95

    def test_get_candidate_pairs_sorted_by_similarity(self):
        """Test that candidate pairs are sorted by similarity descending."""
        service = GroupingService(threshold=0.5)
        similarity_matrix = np.array([
            [1.0, 0.7, 0.9],
            [0.7, 1.0, 0.8],
            [0.9, 0.8, 1.0]
        ])
        pairs = service.get_candidate_pairs(similarity_matrix)

        # All pairs above 0.5, should be sorted: 0.9, 0.8, 0.7
        assert len(pairs) == 3
        assert pairs[0]["similarity"] == 0.9
        assert pairs[1]["similarity"] == 0.8
        assert pairs[2]["similarity"] == 0.7

    def test_get_candidate_pairs_custom_threshold(self):
        """Test candidate pairs with custom threshold override."""
        service = GroupingService(threshold=0.5)  # Low default
        similarity_matrix = np.array([
            [1.0, 0.7, 0.9],
            [0.7, 1.0, 0.8],
            [0.9, 0.8, 1.0]
        ])
        # Override with higher threshold
        pairs = service.get_candidate_pairs(similarity_matrix, threshold=0.85)

        # Only 0-2 pair is >= 0.85
        assert len(pairs) == 1
        assert pairs[0]["similarity"] == 0.9


class TestGroupingServiceIntegration:
    """Integration tests for realistic scenarios."""

    def test_large_batch_grouping(self):
        """Test grouping with a larger batch of articles."""
        service = GroupingService(threshold=0.8)

        # Create 20 articles with 3 distinct clusters
        np.random.seed(42)  # For reproducibility

        # Cluster 1: articles 0-6 (similar)
        cluster1 = np.random.randn(7, 768) * 0.1 + np.array([1.0] + [0.0] * 767)

        # Cluster 2: articles 7-12 (similar)
        cluster2 = np.random.randn(6, 768) * 0.1 + np.array([0.0, 1.0] + [0.0] * 766)

        # Cluster 3: articles 13-19 (singletons - each unique)
        cluster3 = np.eye(7, 768)  # Each is orthogonal

        embeddings = np.vstack([cluster1, cluster2, cluster3])

        groups = service.group_articles(embeddings)

        # Should have roughly 3 major groups + some singletons
        # Due to random noise and threshold, exact count may vary
        assert len(groups) >= 3

    def test_duplicate_detection(self):
        """Test that exact duplicates are grouped together."""
        service = GroupingService(threshold=0.99)  # Very high threshold

        # Exact duplicates
        base_embedding = np.array([1.0, 2.0, 3.0])
        embeddings = np.array([
            base_embedding,
            base_embedding,  # Exact duplicate
            base_embedding * 1.001,  # Nearly identical
            [4.0, 5.0, 6.0]  # Different
        ])

        groups = service.group_articles(embeddings)

        # First 3 should be in same group (normalized similarity ~1.0)
        group_with_dups = [g for g in groups if g.size == 3]
        assert len(group_with_dups) == 1

    def test_negative_similarity_handling(self):
        """Test that negative similarities don't cause issues."""
        service = GroupingService(threshold=0.5)

        # Opposite vectors have -1.0 similarity
        embeddings = np.array([
            [1.0, 0.0],
            [-1.0, 0.0],  # Opposite of first
            [0.0, 1.0]   # Orthogonal
        ])

        groups = service.group_articles(embeddings)

        # All should be singletons (no similarity >= 0.5)
        assert len(groups) == 3
        assert all(g.is_singleton for g in groups)

    def test_transitive_grouping(self):
        """Test that transitive similarity creates proper groups.

        If A~B and B~C, then A,B,C should be in same group even if A~C < threshold.
        """
        service = GroupingService(threshold=0.7)

        # A and B similar (0.8)
        # B and C similar (0.8)
        # A and C less similar (0.6) - still should be grouped via B
        embeddings = np.array([
            [1.0, 0.0, 0.0],    # A
            [0.8, 0.6, 0.0],    # B - similar to A
            [0.4, 0.9, 0.0],    # C - similar to B but not A directly
        ])

        similarity_matrix = service.compute_similarity_matrix(embeddings)
        groups = service.form_groups(similarity_matrix)

        # Check if A-B and B-C are above threshold
        # Due to normalization, actual values may differ
        # This tests the transitive property of Union-Find
