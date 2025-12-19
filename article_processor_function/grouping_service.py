"""
Grouping Service for Article Processing

Groups similar articles based on cosine similarity of their embeddings.
Uses Union-Find (Disjoint Set) algorithm for efficient group formation.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Set

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ArticleGroup:
    """Represents a group of similar articles."""
    group_id: int
    article_indices: List[int]
    max_similarity: float = 0.0

    @property
    def size(self) -> int:
        return len(self.article_indices)

    @property
    def is_singleton(self) -> bool:
        return self.size == 1


class UnionFind:
    """
    Union-Find (Disjoint Set) data structure for efficient grouping.

    Supports path compression and union by rank for O(alpha(n)) operations.
    """

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        """Find root with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        """
        Union two sets by rank.

        Returns True if a union was performed, False if already in same set.
        """
        px, py = self.find(x), self.find(y)
        if px == py:
            return False

        # Union by rank
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1

        return True

    def get_groups(self) -> Dict[int, List[int]]:
        """Get all groups as a dictionary mapping root -> members."""
        groups = defaultdict(list)
        for i in range(len(self.parent)):
            groups[self.find(i)].append(i)
        return dict(groups)


class GroupingService:
    """
    Service for grouping similar articles based on embedding similarity.

    Uses cosine similarity and Union-Find for efficient O(n^2) grouping.
    """

    def __init__(self, threshold: float = 0.80):
        """
        Initialize the grouping service.

        Args:
            threshold: Minimum cosine similarity for grouping (0.0 to 1.0)
                      Default 0.80 for within-run grouping (merge decision candidates)
        """
        self.threshold = threshold
        logger.info(f"GroupingService initialized with threshold: {threshold}")

    def compute_similarity_matrix(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Compute pairwise cosine similarity matrix.

        Args:
            embeddings: numpy array of shape (n_articles, embedding_dim)

        Returns:
            Similarity matrix of shape (n_articles, n_articles)
        """
        if embeddings.size == 0:
            return np.array([])

        # Normalize embeddings for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        # Avoid division by zero
        norms = np.where(norms == 0, 1, norms)
        normalized = embeddings / norms

        # Cosine similarity = dot product of normalized vectors
        similarity_matrix = np.dot(normalized, normalized.T)

        logger.info(f"Computed similarity matrix: shape {similarity_matrix.shape}")

        return similarity_matrix

    def form_groups(self, similarity_matrix: np.ndarray) -> List[ArticleGroup]:
        """
        Form groups of similar articles using Union-Find.

        Args:
            similarity_matrix: Pairwise similarity matrix

        Returns:
            List of ArticleGroup objects
        """
        if similarity_matrix.size == 0:
            return []

        n = similarity_matrix.shape[0]
        uf = UnionFind(n)

        # Track max similarity within each potential group
        pair_similarities: Dict[Tuple[int, int], float] = {}

        # Union articles with similarity >= threshold
        unions_performed = 0
        for i in range(n):
            for j in range(i + 1, n):
                similarity = similarity_matrix[i][j]
                if similarity >= self.threshold:
                    if uf.union(i, j):
                        unions_performed += 1
                    # Track similarity for this pair
                    pair_similarities[(min(i, j), max(i, j))] = similarity

        logger.info(f"Performed {unions_performed} unions with threshold {self.threshold}")

        # Collect groups
        raw_groups = uf.get_groups()

        # Build ArticleGroup objects with metadata
        article_groups = []
        for group_id, (root, indices) in enumerate(raw_groups.items()):
            # Find max similarity within group
            max_sim = 0.0
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    pair_key = (min(indices[i], indices[j]), max(indices[i], indices[j]))
                    if pair_key in pair_similarities:
                        max_sim = max(max_sim, pair_similarities[pair_key])

            group = ArticleGroup(
                group_id=group_id,
                article_indices=sorted(indices),
                max_similarity=max_sim if len(indices) > 1 else 1.0
            )
            article_groups.append(group)

        # Sort by group size (largest first) for processing priority
        article_groups.sort(key=lambda g: (-g.size, g.group_id))

        # Log statistics
        singleton_count = sum(1 for g in article_groups if g.is_singleton)
        multi_count = len(article_groups) - singleton_count
        logger.info(
            f"Formed {len(article_groups)} groups: "
            f"{multi_count} multi-article groups, {singleton_count} singletons"
        )

        return article_groups

    def group_articles(self, embeddings: np.ndarray) -> List[ArticleGroup]:
        """
        Complete pipeline: compute similarity and form groups.

        Args:
            embeddings: numpy array of article embeddings

        Returns:
            List of ArticleGroup objects
        """
        similarity_matrix = self.compute_similarity_matrix(embeddings)
        return self.form_groups(similarity_matrix)

    def get_candidate_pairs(
        self,
        similarity_matrix: np.ndarray,
        threshold: float = None
    ) -> List[Dict]:
        """
        Get list of similar article pairs above threshold.

        Useful for debugging and analysis.

        Args:
            similarity_matrix: Pairwise similarity matrix
            threshold: Override default threshold

        Returns:
            List of dictionaries with pair info
        """
        threshold = threshold or self.threshold
        pairs = []

        n = similarity_matrix.shape[0]
        for i in range(n):
            for j in range(i + 1, n):
                score = similarity_matrix[i][j]
                if score >= threshold:
                    pairs.append({
                        "article_a_idx": i,
                        "article_b_idx": j,
                        "similarity": float(score)
                    })

        # Sort by similarity descending
        pairs.sort(key=lambda x: -x["similarity"])

        logger.info(f"Found {len(pairs)} similar pairs above threshold {threshold}")
        return pairs
