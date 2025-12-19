"""
Cross-Run Deduplication Service

Compares articles against embeddings from previous runs within the same day.
Drops articles that are too similar to previously processed articles.
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Set
import numpy as np
from google.cloud import storage

logger = logging.getLogger(__name__)

# Cross-run dedup threshold - drop if similarity exceeds this
CROSS_RUN_DEDUP_THRESHOLD = 0.7


class CrossRunDeduplicator:
    """
    Deduplicates articles against previous runs within the same day.

    Loads embeddings from all previous run folders that have completed
    (identified by presence of embeddings/*.json files) and compares
    new articles against them.
    """

    def __init__(
        self,
        storage_client: storage.Client,
        bucket_name: str,
        threshold: float = CROSS_RUN_DEDUP_THRESHOLD
    ):
        """
        Initialize the cross-run deduplicator.

        Args:
            storage_client: GCS storage client
            bucket_name: GCS bucket name
            threshold: Similarity threshold for deduplication (default 0.7)
        """
        self.storage_client = storage_client
        self.bucket_name = bucket_name
        self.threshold = threshold
        logger.info(f"CrossRunDeduplicator initialized: threshold={threshold}")

    def list_previous_embedding_files(
        self,
        date_str: str,
        current_run_id: str
    ) -> List[str]:
        """
        List all embedding files from previous runs on the same day.

        Only considers runs with embeddings/*.json files (completed runs).
        Skips the current run.

        Args:
            date_str: Date string (YYYY-MM-DD)
            current_run_id: Current run ID to exclude (HH-MM-SS)

        Returns:
            List of GCS blob paths to embedding files
        """
        bucket = self.storage_client.bucket(self.bucket_name)
        prefix = f"{date_str}/"

        embedding_files = []

        # List all blobs under date prefix
        blobs = bucket.list_blobs(prefix=prefix)

        for blob in blobs:
            # Match pattern: {date}/{HH-MM-SS}/embeddings/*.json
            path = blob.name
            if "/embeddings/" in path and path.endswith("_embeddings.json"):
                # Extract run_id from path
                parts = path.split("/")
                if len(parts) >= 3:
                    run_id = parts[1]  # HH-MM-SS
                    # Skip current run
                    if run_id != current_run_id:
                        embedding_files.append(path)
                        logger.debug(f"Found previous embedding file: {path}")

        logger.info(f"Found {len(embedding_files)} embedding files from previous runs")
        return embedding_files

    def load_embeddings_from_gcs(self, blob_path: str) -> Tuple[List[str], np.ndarray]:
        """
        Load embeddings from a GCS JSON file.

        Args:
            blob_path: GCS blob path to embeddings file

        Returns:
            Tuple of (article_ids, embeddings_array)
        """
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(blob_path)
            content = blob.download_as_text()
            data = json.loads(content)

            article_ids = data.get("article_ids", [])
            embeddings = np.array(data.get("embeddings", []))

            logger.debug(f"Loaded {len(article_ids)} embeddings from {blob_path}")
            return article_ids, embeddings

        except Exception as e:
            logger.error(f"Error loading embeddings from {blob_path}: {e}")
            return [], np.array([])

    def load_all_previous_embeddings(
        self,
        date_str: str,
        current_run_id: str
    ) -> Tuple[List[str], np.ndarray]:
        """
        Load and combine all embeddings from previous runs.

        Args:
            date_str: Date string (YYYY-MM-DD)
            current_run_id: Current run ID to exclude

        Returns:
            Tuple of (all_article_ids, combined_embeddings_array)
        """
        embedding_files = self.list_previous_embedding_files(date_str, current_run_id)

        if not embedding_files:
            logger.info("No previous embeddings found")
            return [], np.array([])

        all_article_ids = []
        all_embeddings = []

        for blob_path in embedding_files:
            article_ids, embeddings = self.load_embeddings_from_gcs(blob_path)
            if len(article_ids) > 0 and embeddings.size > 0:
                all_article_ids.extend(article_ids)
                all_embeddings.append(embeddings)

        if not all_embeddings:
            return [], np.array([])

        combined_embeddings = np.vstack(all_embeddings)
        logger.info(f"Loaded {len(all_article_ids)} total embeddings from {len(embedding_files)} files")

        return all_article_ids, combined_embeddings

    def compute_max_similarity(
        self,
        new_embeddings: np.ndarray,
        previous_embeddings: np.ndarray
    ) -> np.ndarray:
        """
        Compute max similarity of each new embedding against all previous embeddings.

        Args:
            new_embeddings: Array of shape (n_new, dim)
            previous_embeddings: Array of shape (n_prev, dim)

        Returns:
            Array of shape (n_new,) with max similarity for each new embedding
        """
        if previous_embeddings.size == 0:
            return np.zeros(len(new_embeddings))

        # Normalize both sets
        new_norms = np.linalg.norm(new_embeddings, axis=1, keepdims=True)
        new_norms = np.where(new_norms == 0, 1, new_norms)
        new_normalized = new_embeddings / new_norms

        prev_norms = np.linalg.norm(previous_embeddings, axis=1, keepdims=True)
        prev_norms = np.where(prev_norms == 0, 1, prev_norms)
        prev_normalized = previous_embeddings / prev_norms

        # Compute similarity matrix: (n_new, n_prev)
        similarity_matrix = np.dot(new_normalized, prev_normalized.T)

        # Get max similarity for each new embedding
        max_similarities = np.max(similarity_matrix, axis=1)

        return max_similarities

    def deduplicate(
        self,
        articles: List[Dict[str, Any]],
        embeddings: np.ndarray,
        date_str: str,
        current_run_id: str
    ) -> Tuple[List[Dict[str, Any]], np.ndarray, List[Dict[str, Any]]]:
        """
        Deduplicate articles against previous runs.

        Args:
            articles: List of article dictionaries
            embeddings: Embeddings for the articles (same order)
            date_str: Date string (YYYY-MM-DD)
            current_run_id: Current run ID

        Returns:
            Tuple of (kept_articles, kept_embeddings, dropped_articles_log)
        """
        if not articles:
            return [], np.array([]), []

        # Load previous embeddings
        prev_article_ids, prev_embeddings = self.load_all_previous_embeddings(
            date_str, current_run_id
        )

        if prev_embeddings.size == 0:
            logger.info("No previous embeddings - keeping all articles")
            return articles, embeddings, []

        # Compute max similarity against previous articles
        max_similarities = self.compute_max_similarity(embeddings, prev_embeddings)

        kept_articles = []
        kept_embeddings = []
        dropped_log = []

        for i, (article, similarity) in enumerate(zip(articles, max_similarities)):
            if similarity >= self.threshold:
                # Drop - too similar to previous article
                dropped_log.append({
                    "article_id": article.get("article_id", "unknown"),
                    "title": article.get("title", "")[:100],
                    "url": article.get("url", ""),
                    "max_similarity": float(similarity),
                    "threshold": self.threshold,
                    "reason": "cross_run_duplicate"
                })
                logger.debug(
                    f"Dropping article (sim={similarity:.3f}): {article.get('title', '')[:50]}"
                )
            else:
                kept_articles.append(article)
                kept_embeddings.append(embeddings[i])

        kept_embeddings_array = np.array(kept_embeddings) if kept_embeddings else np.array([])

        logger.info(
            f"Cross-run dedup: {len(articles)} -> {len(kept_articles)} articles "
            f"({len(dropped_log)} dropped)"
        )

        return kept_articles, kept_embeddings_array, dropped_log

    def save_embeddings(
        self,
        article_ids: List[str],
        embeddings: np.ndarray,
        output_path: str
    ) -> str:
        """
        Save embeddings to GCS for future cross-run deduplication.

        Args:
            article_ids: List of article IDs (same order as embeddings)
            embeddings: Numpy array of embeddings
            output_path: GCS blob path for output

        Returns:
            GCS URI of saved file
        """
        data = {
            "article_ids": article_ids,
            "embeddings": embeddings.tolist(),
            "count": len(article_ids),
            "embedding_dim": embeddings.shape[1] if embeddings.ndim > 1 else 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(output_path)
        blob.upload_from_string(
            json.dumps(data),
            content_type="application/json"
        )

        gcs_uri = f"gs://{self.bucket_name}/{output_path}"
        logger.info(f"Saved {len(article_ids)} embeddings to {gcs_uri}")

        return gcs_uri
