"""
Regional News Diff Analyzer

Finds articles that appear in one region but not in another by comparing
embeddings. Uses cosine similarity to determine if an article has coverage
in the other region.

Example: get_diff("eu", "tr") finds EU news not covered in Turkey.

With HISTORICAL_DIFF_DEPTH > 1, compares new EU articles against TR articles
from the last N days, not just the same run.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from google.cloud import storage

logger = logging.getLogger(__name__)

# Default threshold for considering articles as "same story"
# Articles with similarity >= threshold are considered covered in both regions
DEFAULT_DIFF_THRESHOLD = 0.75

# File patterns for different run types
# Scrape-triggered runs produce scraped_* files
# API-triggered runs produce complete_* and scraped_incomplete_* files
EMBEDDING_FILES = [
    'embeddings/scraped_embeddings.json',
    'embeddings/complete_embeddings.json',
    'embeddings/scraped_incomplete_embeddings.json'
]

ARTICLE_FILES = [
    'enriched_scraped_articles.json',
    'enriched_complete_articles.json',
    'enriched_scraped_incomplete_articles.json'
]


class RegionDiffAnalyzer:
    """
    Analyzes regional coverage differences using embeddings.

    Compares articles between two regions to find stories that are
    unique to one region (not covered in the other).
    """

    def __init__(
        self,
        storage_client: storage.Client,
        bucket_name: str,
        diff_threshold: float = DEFAULT_DIFF_THRESHOLD,
        historical_diff_depth: int = 3
    ):
        """
        Initialize the region diff analyzer.

        Args:
            storage_client: GCS storage client
            bucket_name: GCS bucket name
            diff_threshold: Similarity threshold (default 0.75)
                           Articles with max_similarity < threshold are "unique"
            historical_diff_depth: Number of days of TR history to compare against (default 3)
        """
        self.storage_client = storage_client
        self.bucket_name = bucket_name
        self.diff_threshold = diff_threshold
        self.historical_diff_depth = historical_diff_depth
        logger.info(
            f"RegionDiffAnalyzer initialized: bucket={bucket_name}, "
            f"diff_threshold={diff_threshold}, historical_diff_depth={historical_diff_depth}"
        )

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

    def load_articles_from_gcs(self, blob_path: str) -> List[Dict[str, Any]]:
        """
        Load articles from a GCS JSON file.

        Args:
            blob_path: GCS blob path to articles file

        Returns:
            List of article dictionaries
        """
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(blob_path)
            content = blob.download_as_text()
            data = json.loads(content)

            # Handle both {"articles": [...]} and direct [...] format
            if isinstance(data, dict):
                articles = data.get('articles', [])
            else:
                articles = data

            logger.debug(f"Loaded {len(articles)} articles from {blob_path}")
            return articles

        except Exception as e:
            logger.error(f"Error loading articles from {blob_path}: {e}")
            return []

    def load_all_embeddings_from_run(self, run_folder: str) -> Tuple[List[str], np.ndarray]:
        """
        Load embeddings from all available embedding files in a run folder.

        Handles both scrape-triggered runs (scraped_embeddings.json) and
        API-triggered runs (complete_embeddings.json, scraped_incomplete_embeddings.json).

        Args:
            run_folder: GCS path to run folder (e.g., "ingestion/2025-12-22/08-37-29")

        Returns:
            Tuple of (all_article_ids, all_embeddings_array)
        """
        all_article_ids = []
        all_embeddings = []

        for emb_file in EMBEDDING_FILES:
            path = f"{run_folder}/{emb_file}"
            article_ids, embeddings = self.load_embeddings_from_gcs(path)
            if len(article_ids) > 0:
                logger.debug(f"Loaded {len(article_ids)} embeddings from {emb_file}")
                all_article_ids.extend(article_ids)
                all_embeddings.extend(embeddings)

        if all_embeddings:
            logger.info(f"Total {len(all_article_ids)} embeddings loaded from {run_folder}")
            return all_article_ids, np.array(all_embeddings)

        return [], np.array([])

    def load_all_articles_from_run(self, run_folder: str) -> List[Dict[str, Any]]:
        """
        Load articles from all available article files in a run folder.

        Handles both scrape-triggered runs (enriched_scraped_articles.json) and
        API-triggered runs (enriched_complete_articles.json, enriched_scraped_incomplete_articles.json).

        Args:
            run_folder: GCS path to run folder (e.g., "ingestion/2025-12-22/08-37-29")

        Returns:
            List of all articles (deduplicated by article_id)
        """
        all_articles = []
        seen_ids = set()

        for art_file in ARTICLE_FILES:
            path = f"{run_folder}/{art_file}"
            articles = self.load_articles_from_gcs(path)
            for article in articles:
                aid = article.get('article_id')
                if aid and aid not in seen_ids:
                    seen_ids.add(aid)
                    all_articles.append(article)

        if all_articles:
            logger.info(f"Total {len(all_articles)} articles loaded from {run_folder}")

        return all_articles

    def get_historical_dates(self, run_folder: str) -> List[str]:
        """
        Get list of dates to load TR articles from based on historical_diff_depth.

        Args:
            run_folder: Current run folder (e.g., "ingestion/2025-12-22/08-37-29")

        Returns:
            List of date strings (YYYY-MM-DD) going back historical_diff_depth days
        """
        # Extract date from run_folder: ingestion/2025-12-22/08-37-29 -> 2025-12-22
        parts = run_folder.split('/')
        if len(parts) >= 2:
            current_date_str = parts[1]  # 2025-12-22
        else:
            current_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        try:
            current_date = datetime.strptime(current_date_str, '%Y-%m-%d')
        except ValueError:
            current_date = datetime.now(timezone.utc)

        dates = []
        for i in range(self.historical_diff_depth):
            date = current_date - timedelta(days=i)
            dates.append(date.strftime('%Y-%m-%d'))

        logger.info(f"Historical dates for TR comparison: {dates}")
        return dates

    def find_run_folders_for_date(self, date: str) -> List[str]:
        """
        Find all run folders for a given date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            List of run folder paths (e.g., ["ingestion/2025-12-22/08-37-29", ...])
        """
        prefix = f"ingestion/{date}/"
        run_folders = set()

        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blobs = bucket.list_blobs(prefix=prefix, delimiter='/')

            # Get prefixes (subdirectories)
            for page in blobs.pages:
                for prefix_path in page.prefixes:
                    # prefix_path is like "ingestion/2025-12-22/08-37-29/"
                    run_folder = prefix_path.rstrip('/')
                    run_folders.add(run_folder)

            logger.debug(f"Found {len(run_folders)} run folders for {date}")

        except Exception as e:
            logger.error(f"Error finding run folders for {date}: {e}")

        return list(run_folders)

    def load_historical_tr_data(
        self,
        current_run_folder: str,
        region2: str
    ) -> Tuple[List[Tuple[str, int, Dict]], np.ndarray]:
        """
        Load TR articles and embeddings from historical dates.

        Args:
            current_run_folder: The current run folder (for EU articles)
            region2: The region to load historical data for (e.g., "tr")

        Returns:
            Tuple of (region2_data list, region2_embeddings array)
        """
        historical_dates = self.get_historical_dates(current_run_folder)
        all_region2_data = []  # (article_id, embedding)
        all_region2_embeddings = []
        seen_article_ids = set()

        for date in historical_dates:
            run_folders = self.find_run_folders_for_date(date)
            logger.info(f"Loading TR data from {date}: {len(run_folders)} run folders")

            for run_folder in run_folders:
                # Load all embeddings (scraped, complete, scraped_incomplete)
                article_ids, embeddings = self.load_all_embeddings_from_run(run_folder)

                if len(article_ids) == 0:
                    continue

                # Load all enriched articles to filter by region
                articles = self.load_all_articles_from_run(run_folder)

                if not articles:
                    continue

                # Create article_id to article mapping
                article_map = {a.get('article_id'): a for a in articles}

                # Filter for region2 articles only
                for idx, article_id in enumerate(article_ids):
                    # Skip if we've already seen this article
                    if article_id in seen_article_ids:
                        continue

                    article = article_map.get(article_id)
                    if not article:
                        continue

                    region = article.get('region', '').lower()
                    if region == region2.lower():
                        seen_article_ids.add(article_id)
                        all_region2_data.append((article_id, len(all_region2_embeddings), article))
                        all_region2_embeddings.append(embeddings[idx])

        if all_region2_embeddings:
            embeddings_array = np.array(all_region2_embeddings)
        else:
            embeddings_array = np.array([])

        logger.info(
            f"Loaded {len(all_region2_data)} unique {region2} articles "
            f"from {len(historical_dates)} days of history"
        )

        return all_region2_data, embeddings_array

    def compute_similarity_matrix(
        self,
        embeddings1: np.ndarray,
        embeddings2: np.ndarray
    ) -> np.ndarray:
        """
        Compute cosine similarity matrix between two sets of embeddings.

        Args:
            embeddings1: Array of shape (N, dim)
            embeddings2: Array of shape (M, dim)

        Returns:
            Similarity matrix of shape (N, M)
        """
        if embeddings1.size == 0 or embeddings2.size == 0:
            return np.array([])

        # Normalize embeddings
        norms1 = np.linalg.norm(embeddings1, axis=1, keepdims=True)
        norms1 = np.where(norms1 == 0, 1, norms1)
        normalized1 = embeddings1 / norms1

        norms2 = np.linalg.norm(embeddings2, axis=1, keepdims=True)
        norms2 = np.where(norms2 == 0, 1, norms2)
        normalized2 = embeddings2 / norms2

        # Compute similarity matrix: (N, M)
        similarity_matrix = np.dot(normalized1, normalized2.T)

        return similarity_matrix

    def get_diff(
        self,
        region1: str,
        region2: str,
        run_folder: str,
        diff_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Find articles in region1 that have no similar match in region2.

        Compares EU articles from current run against TR articles from
        the last HISTORICAL_DIFF_DEPTH days (not just current run).

        Args:
            region1: Source region (e.g., "eu")
            region2: Comparison region (e.g., "tr")
            run_folder: GCS path to run folder (e.g., "ingestion/2025-12-22/08-37-29")
            diff_threshold: Override default threshold if provided

        Returns:
            Dict with metadata, summary, and unique_articles
        """
        threshold = diff_threshold if diff_threshold is not None else self.diff_threshold

        logger.info(
            f"Computing diff: {region1} vs {region2}, "
            f"run_folder={run_folder}, threshold={threshold}, "
            f"historical_diff_depth={self.historical_diff_depth}"
        )

        # ===== LOAD REGION1 (EU) DATA FROM CURRENT RUN ONLY =====
        # Load all embeddings (scraped, complete, scraped_incomplete)
        article_ids, embeddings = self.load_all_embeddings_from_run(run_folder)

        if len(article_ids) == 0:
            logger.warning(f"No embeddings found in {run_folder}")
            return self._empty_result(region1, region2, run_folder, threshold)

        # Load all enriched articles to get region info
        articles = self.load_all_articles_from_run(run_folder)

        if not articles:
            logger.warning(f"No articles found in {run_folder}")
            return self._empty_result(region1, region2, run_folder, threshold)

        # Create article_id to article mapping
        article_map = {a.get('article_id'): a for a in articles}

        # Extract region1 (EU) articles from current run
        region1_data = []  # (article_id, embedding_index, article)

        for idx, article_id in enumerate(article_ids):
            article = article_map.get(article_id)
            if not article:
                continue

            region = article.get('region', '').lower()
            if region == region1.lower():
                region1_data.append((article_id, idx, article))

        logger.info(f"Found {len(region1_data)} {region1} articles in current run")

        # Handle edge case: no region1 articles
        if len(region1_data) == 0:
            logger.info(f"No {region1} articles found in current run")
            return self._empty_result(region1, region2, run_folder, threshold)

        # ===== LOAD REGION2 (TR) DATA FROM HISTORICAL DATES =====
        region2_data, region2_embeddings = self.load_historical_tr_data(
            run_folder, region2
        )

        # Handle edge case: no region2 articles in history
        if len(region2_data) == 0:
            logger.info(
                f"No {region2} articles found in last {self.historical_diff_depth} days - "
                f"all {region1} articles are unique"
            )
            unique_articles = [
                self._format_unique_article(article, 0.0, None)
                for _, _, article in region1_data
            ]
            return self._build_result(
                region1, region2, run_folder, threshold,
                len(region1_data), 0, unique_articles
            )

        # ===== BUILD EMBEDDING MATRICES =====
        region1_indices = [idx for _, idx, _ in region1_data]
        region1_embeddings = embeddings[region1_indices]

        # region2_embeddings is already built by load_historical_tr_data

        # ===== COMPUTE SIMILARITY MATRIX =====
        similarity_matrix = self.compute_similarity_matrix(
            region1_embeddings, region2_embeddings
        )

        # Find unique articles (max_similarity < threshold)
        max_similarities = np.max(similarity_matrix, axis=1)
        max_indices = np.argmax(similarity_matrix, axis=1)

        unique_articles = []
        for i, (article_id, emb_idx, article) in enumerate(region1_data):
            max_sim = float(max_similarities[i])

            if max_sim < threshold:
                # This article is unique to region1
                closest_idx = int(max_indices[i])
                closest_article = region2_data[closest_idx][2] if closest_idx < len(region2_data) else None

                unique_articles.append(
                    self._format_unique_article(article, max_sim, closest_article)
                )

        logger.info(
            f"Diff complete: {len(unique_articles)} unique to {region1} "
            f"(out of {len(region1_data)}, compared against {len(region2_data)} "
            f"{region2} articles from {self.historical_diff_depth} days)"
        )

        return self._build_result(
            region1, region2, run_folder, threshold,
            len(region1_data), len(region2_data), unique_articles
        )

    def _format_unique_article(
        self,
        article: Dict[str, Any],
        max_similarity: float,
        closest_article: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Format a unique article for output."""
        result = {
            "article_id": article.get("article_id", ""),
            "title": article.get("title", ""),
            "original_url": article.get("original_url", ""),
            "source": article.get("source", ""),
            "publish_date": article.get("publish_date", ""),
            "max_similarity": round(max_similarity, 4),
            # Preserve original metadata
            "source_type": article.get("source_type", "scraped"),
            "language": article.get("language", ""),
            "original_region": article.get("region", "eu"),
        }

        if closest_article:
            result["closest_match"] = {
                "article_id": closest_article.get("article_id", ""),
                "title": closest_article.get("title", ""),
            }
            result["closest_match_url"] = closest_article.get("original_url", "")
        else:
            result["closest_match"] = None
            result["closest_match_url"] = ""

        return result

    def _empty_result(
        self,
        region1: str,
        region2: str,
        run_folder: str,
        threshold: float
    ) -> Dict[str, Any]:
        """Return empty result structure."""
        return self._build_result(region1, region2, run_folder, threshold, 0, 0, [])

    def _build_result(
        self,
        region1: str,
        region2: str,
        run_folder: str,
        threshold: float,
        total_region1: int,
        total_region2: int,
        unique_articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build the final result structure."""
        return {
            "metadata": {
                "region1": region1,
                "region2": region2,
                "run_folder": run_folder,
                "diff_threshold": threshold,
                "generated_at": datetime.now(timezone.utc).isoformat()
            },
            "summary": {
                "total_region1_articles": total_region1,
                "total_region2_articles": total_region2,
                "unique_to_region1": len(unique_articles)
            },
            "unique_articles": unique_articles
        }

    def save_result_to_gcs(self, result: Dict[str, Any], output_path: str) -> str:
        """
        Save diff result to GCS.

        Args:
            result: Diff result dictionary
            output_path: GCS blob path for output

        Returns:
            GCS URI of saved file
        """
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(output_path)
        blob.upload_from_string(
            json.dumps(result, indent=2),
            content_type="application/json"
        )

        gcs_uri = f"gs://{self.bucket_name}/{output_path}"
        logger.info(f"Saved diff result to {gcs_uri}")

        return gcs_uri
