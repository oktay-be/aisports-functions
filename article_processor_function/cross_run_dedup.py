"""
Cross-Run Deduplication Service

Compares articles against embeddings from previous runs within the same day.
Drops articles that are too similar to previously processed articles.

Supports region-specific thresholds (e.g., EU: 0.9, TR: 0.7) to account for
different content overlap characteristics across regions.
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Set, Optional
import numpy as np
from google.cloud import storage

logger = logging.getLogger(__name__)

# Default cross-run dedup threshold - drop if similarity exceeds this
CROSS_RUN_DEDUP_THRESHOLD = 0.7

# Region-specific defaults (can be overridden via constructor)
DEFAULT_REGION_THRESHOLDS = {
    'tr': 0.7,  # Turkish content - lower threshold due to higher content overlap
    'eu': 0.9,  # European content - higher threshold for stricter dedup
}


class CrossRunDeduplicator:
    """
    Deduplicates articles against previous runs within the same day.

    Loads embeddings from all previous run folders that have completed
    (identified by presence of embeddings/*.json files) and compares
    new articles against them.
    
    Supports region-specific thresholds to handle varying content overlap
    characteristics across different regions.
    """

    def __init__(
        self,
        storage_client: storage.Client,
        bucket_name: str,
        threshold: float = CROSS_RUN_DEDUP_THRESHOLD,
        region_thresholds: Optional[Dict[str, float]] = None
    ):
        """
        Initialize the cross-run deduplicator.

        Args:
            storage_client: GCS storage client
            bucket_name: GCS bucket name
            threshold: Default similarity threshold for deduplication (default 0.7)
            region_thresholds: Optional dict mapping region codes to thresholds
                              e.g., {'tr': 0.7, 'eu': 0.9}
        """
        self.storage_client = storage_client
        self.bucket_name = bucket_name
        self.threshold = threshold
        self.region_thresholds = region_thresholds or DEFAULT_REGION_THRESHOLDS.copy()
        logger.info(
            f"CrossRunDeduplicator initialized: default_threshold={threshold}, "
            f"region_thresholds={self.region_thresholds}"
        )

    def get_threshold_for_region(self, region: Optional[str]) -> float:
        """
        Get the deduplication threshold for a specific region.
        
        Args:
            region: Region code (e.g., 'tr', 'eu') or None
            
        Returns:
            Threshold for the region, or default threshold if region not configured
        """
        if region and region.lower() in self.region_thresholds:
            return self.region_thresholds[region.lower()]
        return self.threshold

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
        prefix = f"ingestion/{date_str}/"

        embedding_files = []

        # List all blobs under date prefix
        blobs = bucket.list_blobs(prefix=prefix)

        for blob in blobs:
            # Match pattern: ingestion/{date}/{HH-MM-SS}/embeddings/*.json
            path = blob.name
            if "/embeddings/" in path and path.endswith("_embeddings.json"):
                # Extract run_id from path
                parts = path.split("/")
                if len(parts) >= 4:
                    run_id = parts[2]  # HH-MM-SS (after ingestion/date/)
                    # Skip current run
                    if run_id != current_run_id:
                        embedding_files.append(path)
                        logger.debug(f"Found previous embedding file: {path}")

        logger.info(f"Found {len(embedding_files)} embedding files from previous runs")
        return embedding_files

    def load_embeddings_from_gcs(self, blob_path: str) -> Tuple[List[str], List[str], np.ndarray]:
        """
        Load embeddings from a GCS JSON file.

        Args:
            blob_path: GCS blob path to embeddings file

        Returns:
            Tuple of (article_ids, urls, embeddings_array)
        """
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(blob_path)
            content = blob.download_as_text()
            data = json.loads(content)

            article_ids = data.get("article_ids", [])
            urls = data.get("urls", [])  # May be empty for old embedding files
            embeddings = np.array(data.get("embeddings", []))

            logger.debug(f"Loaded {len(article_ids)} embeddings from {blob_path}")
            return article_ids, urls, embeddings

        except Exception as e:
            logger.error(f"Error loading embeddings from {blob_path}: {e}")
            return [], [], np.array([])

    def load_all_previous_embeddings(
        self,
        date_str: str,
        current_run_id: str
    ) -> Tuple[List[str], List[str], np.ndarray]:
        """
        Load and combine all embeddings from previous runs.

        Args:
            date_str: Date string (YYYY-MM-DD)
            current_run_id: Current run ID to exclude

        Returns:
            Tuple of (all_article_ids, all_urls, combined_embeddings_array)
        """
        embedding_files = self.list_previous_embedding_files(date_str, current_run_id)

        if not embedding_files:
            logger.info("No previous embeddings found")
            return [], [], np.array([])

        all_article_ids = []
        all_urls = []
        all_embeddings = []

        for blob_path in embedding_files:
            article_ids, urls, embeddings = self.load_embeddings_from_gcs(blob_path)
            if len(article_ids) > 0 and embeddings.size > 0:
                all_article_ids.extend(article_ids)
                # Handle old embedding files that don't have URLs
                if urls:
                    all_urls.extend(urls)
                else:
                    all_urls.extend([''] * len(article_ids))
                all_embeddings.append(embeddings)

        if not all_embeddings:
            return [], [], np.array([])

        combined_embeddings = np.vstack(all_embeddings)
        logger.info(f"Loaded {len(all_article_ids)} total embeddings from {len(embedding_files)} files")

        return all_article_ids, all_urls, combined_embeddings

    def compute_max_similarity(
        self,
        new_embeddings: np.ndarray,
        previous_embeddings: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute max similarity of each new embedding against all previous embeddings.

        Args:
            new_embeddings: Array of shape (n_new, dim)
            previous_embeddings: Array of shape (n_prev, dim)

        Returns:
            Tuple of:
            - Array of shape (n_new,) with max similarity for each new embedding
            - Array of shape (n_new,) with index of best matching previous embedding
        """
        if previous_embeddings.size == 0:
            return np.zeros(len(new_embeddings)), np.zeros(len(new_embeddings), dtype=int)

        # Normalize both sets
        new_norms = np.linalg.norm(new_embeddings, axis=1, keepdims=True)
        new_norms = np.where(new_norms == 0, 1, new_norms)
        new_normalized = new_embeddings / new_norms

        prev_norms = np.linalg.norm(previous_embeddings, axis=1, keepdims=True)
        prev_norms = np.where(prev_norms == 0, 1, prev_norms)
        prev_normalized = previous_embeddings / prev_norms

        # Compute similarity matrix: (n_new, n_prev)
        similarity_matrix = np.dot(new_normalized, prev_normalized.T)

        # Get max similarity and its index for each new embedding
        max_similarities = np.max(similarity_matrix, axis=1)
        max_indices = np.argmax(similarity_matrix, axis=1)

        return max_similarities, max_indices

    def deduplicate(
        self,
        articles: List[Dict[str, Any]],
        embeddings: np.ndarray,
        date_str: str,
        current_run_id: str
    ) -> Tuple[List[Dict[str, Any]], np.ndarray, List[Dict[str, Any]]]:
        """
        Deduplicate articles against previous runs.

        Uses region-specific thresholds when available. Each article's region
        is checked to determine the appropriate threshold.

        Args:
            articles: List of article dictionaries (may contain 'region' field)
            embeddings: Embeddings for the articles (same order)
            date_str: Date string (YYYY-MM-DD)
            current_run_id: Current run ID

        Returns:
            Tuple of (kept_articles, kept_embeddings, dropped_articles_log)
        """
        if not articles:
            return [], np.array([]), []

        # Load previous embeddings (now includes URLs)
        prev_article_ids, prev_urls, prev_embeddings = self.load_all_previous_embeddings(
            date_str, current_run_id
        )

        if prev_embeddings.size == 0:
            logger.info("No previous embeddings - keeping all articles")
            return articles, embeddings, []

        # Compute max similarity against previous articles (now returns indices too)
        max_similarities, max_indices = self.compute_max_similarity(embeddings, prev_embeddings)

        kept_articles = []
        kept_embeddings = []
        dropped_log = []

        # Track stats by region for logging
        region_stats = {}

        for i, (article, similarity) in enumerate(zip(articles, max_similarities)):
            # Get region-specific threshold
            region = article.get('region')
            threshold = self.get_threshold_for_region(region)

            # Track region stats
            region_key = region or 'unknown'
            if region_key not in region_stats:
                region_stats[region_key] = {'threshold': threshold, 'kept': 0, 'dropped': 0}

            if similarity >= threshold:
                # Get the URL of the matched article
                matched_idx = int(max_indices[i])
                matched_url = prev_urls[matched_idx] if matched_idx < len(prev_urls) else None

                # Drop - too similar to previous article
                dropped_log.append({
                    "article_id": article.get("article_id", "unknown"),
                    "title": article.get("title", "")[:100],
                    "url": article.get("url", ""),
                    "matched_article_url": matched_url,
                    "region": region,
                    "max_similarity": float(similarity),
                    "threshold": threshold,
                    "reason": "cross_run_duplicate"
                })
                region_stats[region_key]['dropped'] += 1
                logger.debug(
                    f"Dropping article (sim={similarity:.3f}, threshold={threshold}, region={region}): "
                    f"{article.get('title', '')[:50]}"
                )
            else:
                kept_articles.append(article)
                kept_embeddings.append(embeddings[i])
                region_stats[region_key]['kept'] += 1

        kept_embeddings_array = np.array(kept_embeddings) if kept_embeddings else np.array([])

        # Log overall stats
        logger.info(
            f"Cross-run dedup: {len(articles)} -> {len(kept_articles)} articles "
            f"({len(dropped_log)} dropped)"
        )
        
        # Log per-region stats
        for region, stats in region_stats.items():
            logger.info(
                f"  Region '{region}': threshold={stats['threshold']}, "
                f"kept={stats['kept']}, dropped={stats['dropped']}"
            )

        return kept_articles, kept_embeddings_array, dropped_log

    def save_embeddings(
        self,
        article_ids: List[str],
        urls: List[str],
        embeddings: np.ndarray,
        output_path: str
    ) -> str:
        """
        Save embeddings to GCS for future cross-run deduplication.

        Args:
            article_ids: List of article IDs (same order as embeddings)
            urls: List of article URLs (same order as embeddings)
            embeddings: Numpy array of embeddings
            output_path: GCS blob path for output

        Returns:
            GCS URI of saved file
        """
        data = {
            "article_ids": article_ids,
            "urls": urls,
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
