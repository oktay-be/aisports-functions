"""
Article Processor Function - Embedding + Cross-Run Dedup + Grouping

Stage 2 of the article processing pipeline.
NO LLM processing - that's handled by merge_decider and article_enricher.

Flow:
1. Triggered by GCS file creation (complete_articles.json, scraped_*.json)
2. Generate embeddings (title + 500 chars body)
3. Save embeddings to embeddings/ folder
4. Cross-run dedup against previous runs (last N days, configurable via CROSS_RUN_DEDUP_DEPTH)
   - Region-specific thresholds: TR=0.85, EU=0.9
5. Group remaining articles (threshold 0.8)
6. Output singleton_*.json and grouped_*.json
"""

import os
import json
import logging
import sys
import re
import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Tuple, Set

# CET timezone for run timestamps
CET = ZoneInfo("Europe/Berlin")

from google.cloud import storage
from google import genai

from embedding_service import EmbeddingService
from grouping_service import GroupingService, ArticleGroup
from cross_run_dedup import CrossRunDeduplicator

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

logger = logging.getLogger(__name__)
logger.info("Article Processor Function initialized")

# Environment configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIRONMENT != 'local':
    storage_client = storage.Client()
else:
    storage_client = None
    logger.info("Running in local environment - skipping Google Cloud client initialization")

# Configuration from environment variables
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
VERTEX_AI_LOCATION = os.getenv('VERTEX_AI_LOCATION', 'us-central1')

# Embedding and grouping configuration
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-004')
GROUPING_THRESHOLD = float(os.getenv('GROUPING_THRESHOLD', '0.8'))

# Region-specific cross-run dedup thresholds
# TR: 0.85 - Turkish content needs higher threshold to avoid false positives on transfer news
# EU: 0.9 - European content more unique, stricter dedup
CROSS_RUN_DEDUP_THRESHOLD_TR = float(os.getenv('CROSS_RUN_DEDUP_THRESHOLD_TR', '0.85'))
CROSS_RUN_DEDUP_THRESHOLD_EU = float(os.getenv('CROSS_RUN_DEDUP_THRESHOLD_EU', '0.9'))

# Cross-run dedup lookback depth (days)
# 1 = same day only, 3 = last 3 days (today + 2 previous)
CROSS_RUN_DEDUP_DEPTH = int(os.getenv('CROSS_RUN_DEDUP_DEPTH', '1'))

# Language normalization map
LANGUAGE_MAP = {
    'turkish': 'tr',
    'english': 'en',
    'portuguese': 'pt',
    'spanish': 'es',
    'french': 'fr',
    'german': 'de',
    'italian': 'it',
    'dutch': 'nl',
}

# File patterns that trigger this function
TRIGGER_PATTERNS = [
    'complete_articles.json',
    'scraped_incomplete_articles.json',
    'scraped_articles.json',
]


def extract_source_type(filename: str) -> str:
    """
    Extract source type from triggering filename.

    Args:
        filename: Name of the triggering file

    Returns:
        Source type string for output filenames
    """
    if filename == 'complete_articles.json':
        return 'complete'
    elif filename == 'scraped_incomplete_articles.json':
        return 'scraped_incomplete'
    elif filename == 'scraped_articles.json':
        return 'scraped'
    else:
        return 'unknown'


def extract_path_info(gcs_path: str) -> Tuple[str, str, str]:
    """
    Extract date and run_id from GCS path.

    Expected path format: {date}/{time}/filename.json

    Args:
        gcs_path: GCS blob path

    Returns:
        Tuple of (date_str, run_id, filename)
    """
    # Pattern: YYYY-MM-DD/HH-MM-SS/filename.json
    pattern = r'(\d{4}-\d{2}-\d{2})/(\d{2}-\d{2}-\d{2})/([^/]+\.json)$'
    match = re.search(pattern, gcs_path)

    if match:
        date_str = match.group(1)
        run_id = match.group(2)
        filename = match.group(3)
        return date_str, run_id, filename

    # Fallback to current time (CET for run timestamps)
    now = datetime.now(CET)
    return now.strftime('%Y-%m-%d'), now.strftime('%H-%M-%S'), 'unknown.json'


class ArticleProcessor:
    """
    Main orchestrator for article processing (embed + dedup + group).

    NO LLM processing - outputs go to merge_decider and article_enricher.
    """

    def __init__(self):
        """Initialize the article processor with necessary clients."""
        self.storage_client = storage_client
        self.genai_client = None
        self.embedding_service = None
        self.grouping_service = None
        self.deduplicator = None

        if ENVIRONMENT != 'local':
            try:
                self.genai_client = genai.Client(
                    vertexai=True,
                    project=PROJECT_ID,
                    location=VERTEX_AI_LOCATION
                )
                logger.info(f"Vertex AI client initialized: project={PROJECT_ID}")

                # Initialize services
                self.embedding_service = EmbeddingService(self.genai_client)
                self.grouping_service = GroupingService(threshold=GROUPING_THRESHOLD)
                
                # Build region-specific threshold map
                region_thresholds = {
                    'tr': CROSS_RUN_DEDUP_THRESHOLD_TR,
                    'eu': CROSS_RUN_DEDUP_THRESHOLD_EU,
                }
                logger.info(f"Region thresholds configured: {region_thresholds}")
                logger.info(f"Cross-run dedup depth: {CROSS_RUN_DEDUP_DEPTH} days")

                self.deduplicator = CrossRunDeduplicator(
                    storage_client=self.storage_client,
                    bucket_name=GCS_BUCKET_NAME,
                    region_thresholds=region_thresholds,
                    dedup_depth=CROSS_RUN_DEDUP_DEPTH
                )

            except Exception as e:
                logger.error(f"Failed to initialize clients: {e}")

    def download_articles(self, gcs_uri: str) -> List[Dict[str, Any]]:
        """
        Download and parse articles from GCS.

        Args:
            gcs_uri: GCS URI to articles file

        Returns:
            List of article dictionaries
        """
        try:
            if gcs_uri.startswith('gs://'):
                parts = gcs_uri.replace('gs://', '').split('/', 1)
                bucket_name = parts[0]
                blob_path = parts[1] if len(parts) > 1 else ''
            else:
                bucket_name = GCS_BUCKET_NAME
                blob_path = gcs_uri

            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            content = blob.download_as_text()

            data = json.loads(content)
            articles = data.get('articles', [])

            # Ensure article_id exists and original_url is set
            for article in articles:
                if 'article_id' not in article or not article['article_id']:
                    url = article.get('url', '')
                    article['article_id'] = hashlib.md5(url.encode()).hexdigest()[:16]
                
                # Ensure original_url is preserved
                if 'original_url' not in article:
                    article['original_url'] = article.get('url', '')

                # Normalize language - check both 'language' and 'lang' (GNews uses 'lang')
                raw_lang = article.get('language') or article.get('lang') or ''
                lang = raw_lang.lower().strip() if isinstance(raw_lang, str) else ''
                if lang in LANGUAGE_MAP:
                    article['language'] = LANGUAGE_MAP[lang]
                elif lang:
                    article['language'] = lang
                
                # Ensure region is set from language (tr -> tr, everything else -> eu)
                if 'region' not in article or not article.get('region'):
                    normalized_lang = article.get('language') or ''
                    article['region'] = 'tr' if normalized_lang == 'tr' else 'eu'

            logger.info(f"Downloaded {len(articles)} articles from {gcs_uri}")
            return articles

        except Exception as e:
            logger.error(f"Error downloading {gcs_uri}: {e}")
            return []

    def pre_filter_duplicates(self, articles: List[Dict]) -> Tuple[List[Dict], int]:
        """
        Remove exact duplicates based on URL and title.

        Args:
            articles: List of raw articles

        Returns:
            Tuple of (filtered_articles, num_removed)
        """
        if not articles:
            return [], 0

        seen_urls: Set[str] = set()
        seen_titles: Dict[str, int] = {}
        filtered = []

        def normalize_url(url: str) -> str:
            url = url.lower().strip()
            url = url.split('?')[0].split('#')[0]
            return url.rstrip('/')

        def normalize_title(title: str) -> str:
            return title.lower().strip()

        for article in articles:
            url = article.get('url', '')
            title = article.get('title', '')

            norm_url = normalize_url(url)
            norm_title = normalize_title(title)

            if norm_url and norm_url in seen_urls:
                continue

            if norm_title and norm_title in seen_titles:
                existing_idx = seen_titles[norm_title]
                existing_body_len = len(filtered[existing_idx].get('body', ''))
                new_body_len = len(article.get('body', ''))

                if new_body_len > existing_body_len:
                    filtered[existing_idx] = article
                continue

            seen_urls.add(norm_url)
            if norm_title:
                seen_titles[norm_title] = len(filtered)
            filtered.append(article)

        num_removed = len(articles) - len(filtered)
        logger.info(f"Pre-filter removed {num_removed} exact duplicates ({len(filtered)} remaining)")

        return filtered, num_removed

    def save_json_to_gcs(self, data: Any, blob_path: str) -> str:
        """
        Save JSON data to GCS.

        Args:
            data: Data to serialize as JSON
            blob_path: GCS blob path

        Returns:
            GCS URI of saved file
        """
        bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(data, ensure_ascii=False, indent=2),
            content_type='application/json'
        )

        gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_path}"
        logger.info(f"Saved to {gcs_uri}")
        return gcs_uri

    def process(self, gcs_path: str) -> Dict[str, Any]:
        """
        Main processing pipeline.

        Args:
            gcs_path: GCS blob path to triggering file

        Returns:
            Processing result with metadata
        """
        # Extract path info
        date_str, run_id, filename = extract_path_info(gcs_path)
        source_type = extract_source_type(filename)
        run_folder = f"ingestion/{date_str}/{run_id}"

        logger.info(f"Processing: date={date_str}, run={run_id}, source={source_type}")

        # Step 1: Download articles
        gcs_uri = f"gs://{GCS_BUCKET_NAME}/{gcs_path}"
        articles = self.download_articles(gcs_uri)

        if not articles:
            logger.warning("No articles found")
            return {"status": "empty", "total_articles": 0}

        total_input = len(articles)

        # Step 2: Pre-filter exact duplicates
        articles, prefilter_removed = self.pre_filter_duplicates(articles)

        if not articles:
            return {
                "status": "empty_after_prefilter",
                "total_articles": total_input,
                "prefilter_removed": prefilter_removed
            }

        # Step 3: Generate embeddings
        logger.info("Generating embeddings...")
        embeddings = self.embedding_service.generate_embeddings(articles)

        # Step 4: Save embeddings for future cross-run dedup
        article_ids = [a.get('article_id', '') for a in articles]
        article_urls = [a.get('url', '') for a in articles]
        article_titles = [a.get('title', '') for a in articles]
        article_content_lengths = [len(a.get('body', '') or a.get('content', '')) for a in articles]
        embeddings_path = f"{run_folder}/embeddings/{source_type}_embeddings.json"
        self.deduplicator.save_embeddings(
            article_ids, article_urls, embeddings, embeddings_path,
            titles=article_titles, content_lengths=article_content_lengths
        )

        # Step 5: Cross-run deduplication
        logger.info("Cross-run deduplication...")
        articles, embeddings, dedup_log = self.deduplicator.deduplicate(
            articles=articles,
            embeddings=embeddings,
            date_str=date_str,
            current_run_id=run_id
        )

        # Save dedup log
        if dedup_log:
            dedup_log_path = f"{run_folder}/dedup_log_{source_type}.json"
            self.save_json_to_gcs({
                "dropped_articles": dedup_log,
                "count": len(dedup_log),
                "region_thresholds": {
                    "tr": CROSS_RUN_DEDUP_THRESHOLD_TR,
                    "eu": CROSS_RUN_DEDUP_THRESHOLD_EU
                },
                "created_at": datetime.now(timezone.utc).isoformat()
            }, dedup_log_path)

        if not articles:
            return {
                "status": "all_duplicates",
                "total_articles": total_input,
                "prefilter_removed": prefilter_removed,
                "cross_run_removed": len(dedup_log)
            }

        # Step 6: Group articles by similarity
        logger.info("Grouping articles...")
        groups = self.grouping_service.group_articles(embeddings)

        # Separate singletons from multi-article groups
        singletons = [g for g in groups if g.is_singleton]
        multi_groups = [g for g in groups if not g.is_singleton]

        logger.info(f"Formed {len(singletons)} singletons, {len(multi_groups)} groups")

        # Step 7: Build output files
        # Normalize article fields for downstream compatibility
        def normalize_article(article: Dict, metadata: Dict) -> Dict:
            """Normalize raw article to ProcessedArticle-compatible format."""
            normalized = article.copy()
            # Field name normalization (raw -> ProcessedArticle)
            if 'url' in normalized and 'original_url' not in normalized:
                normalized['original_url'] = normalized.pop('url')
            # Normalize published_at -> publish_date (scraper uses published_at, standard is publish_date)
            if 'published_at' in normalized and 'publish_date' not in normalized:
                normalized['publish_date'] = normalized.pop('published_at')
            elif 'published_at' in normalized and normalized.get('publish_date'):
                # If both exist, prefer publish_date and remove published_at
                del normalized['published_at']
            # Ensure required fields have defaults
            normalized.setdefault('merged_from_urls', [])
            normalized.setdefault('summary', '')
            normalized.setdefault('categories', [])
            normalized.setdefault('key_entities', {
                'teams': [], 'players': [], 'amounts': [],
                'dates': [], 'competitions': [], 'locations': []
            })
            normalized.setdefault('content_quality', 'medium')
            normalized.setdefault('confidence', 0.5)
            # Don't default language - preserve from source or leave empty
            normalized.setdefault('language', '')
            normalized.setdefault('x_post', '')
            # Preserve keywords that matched this article (for UI highlighting)
            normalized.setdefault('keywords_used', [])
            # Derive region from language if not set: tr -> tr, everything else -> eu
            if 'region' not in normalized or not normalized.get('region'):
                lang = normalized.get('language', '')
                normalized['region'] = 'tr' if lang == 'tr' else 'eu'
            # Preserve source_type from article or infer from extraction_method
            if 'source_type' not in normalized:
                extraction_method = normalized.get('extraction_method', '')
                normalized['source_type'] = 'api' if extraction_method.startswith('api') else 'scraped'
            normalized['_processing_metadata'] = metadata
            return normalized

        singleton_articles = []
        for group in singletons:
            for idx in group.article_indices:
                article = normalize_article(articles[idx], {
                    'source_type': source_type,
                    'date': date_str,
                    'run_id': run_id,
                    'group_type': 'singleton'
                })
                singleton_articles.append(article)

        grouped_articles = []
        for group in multi_groups:
            group_data = {
                'group_id': group.group_id,
                'max_similarity': group.max_similarity,
                'articles': []
            }
            for idx in group.article_indices:
                article = normalize_article(articles[idx], {
                    'source_type': source_type,
                    'date': date_str,
                    'run_id': run_id,
                    'group_type': 'grouped',
                    'group_id': group.group_id
                })
                group_data['articles'].append(article)
            grouped_articles.append(group_data)

        # Step 8: Save output files
        outputs = {}

        if singleton_articles:
            singleton_path = f"{run_folder}/singleton_{source_type}_articles.json"
            outputs['singleton'] = self.save_json_to_gcs({
                'articles': singleton_articles,
                'count': len(singleton_articles),
                'source_type': source_type,
                'created_at': datetime.now(timezone.utc).isoformat()
            }, singleton_path)

        if grouped_articles:
            grouped_path = f"{run_folder}/grouped_{source_type}_articles.json"
            outputs['grouped'] = self.save_json_to_gcs({
                'groups': grouped_articles,
                'group_count': len(grouped_articles),
                'total_articles': sum(len(g['articles']) for g in grouped_articles),
                'source_type': source_type,
                'created_at': datetime.now(timezone.utc).isoformat()
            }, grouped_path)

        # Save processing metadata
        metadata = {
            "status": "success",
            "source_type": source_type,
            "date": date_str,
            "run_id": run_id,
            "input_file": gcs_path,
            "total_input_articles": total_input,
            "prefilter_removed": prefilter_removed,
            "cross_run_removed": len(dedup_log),
            "articles_after_dedup": len(articles),
            "singleton_count": len(singleton_articles),
            "group_count": len(multi_groups),
            "grouped_article_count": sum(len(g['articles']) for g in grouped_articles),
            "output_files": outputs,
            "thresholds": {
                "cross_run_dedup_tr": CROSS_RUN_DEDUP_THRESHOLD_TR,
                "cross_run_dedup_eu": CROSS_RUN_DEDUP_THRESHOLD_EU,
                "grouping": GROUPING_THRESHOLD
            },
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        metadata_path = f"{run_folder}/processing_metadata_{source_type}.json"
        self.save_json_to_gcs(metadata, metadata_path)

        logger.info(f"Processing complete: {len(singleton_articles)} singletons, {len(multi_groups)} groups")

        return metadata


def process_articles(event, context):
    """
    Cloud Function entry point.

    Triggered by GCS Eventarc on file creation.

    Args:
        event: CloudEvent data
        context: Cloud Functions context
    """
    logger.info("=== ARTICLE PROCESSOR FUNCTION TRIGGERED ===")

    # Extract file info from event
    if isinstance(event, dict):
        # GCS trigger format
        bucket = event.get('bucket', GCS_BUCKET_NAME)
        name = event.get('name', '')
    else:
        logger.error(f"Unknown event format: {type(event)}")
        return

    logger.info(f"Triggered by: gs://{bucket}/{name}")

    # Check if this is a file we should process
    filename = name.split('/')[-1] if name else ''
    if filename not in TRIGGER_PATTERNS:
        logger.info(f"Ignoring file: {filename} (not in trigger patterns)")
        return

    try:
        processor = ArticleProcessor()

        if not processor.genai_client and ENVIRONMENT != 'local':
            logger.error("Vertex AI client not available")
            return

        result = processor.process(name)
        logger.info(f"Processing result: {result.get('status')}")

    except Exception as e:
        logger.error(f"Error processing: {e}", exc_info=True)

    logger.info("=== ARTICLE PROCESSOR FUNCTION COMPLETED ===")


# HTTP entry point for Cloud Run
def main(request):
    """
    HTTP entry point for Cloud Run deployment.

    Args:
        request: Flask request object

    Returns:
        JSON response
    """
    logger.info("=== ARTICLE PROCESSOR HTTP TRIGGERED ===")

    try:
        # Parse request
        if request.is_json:
            data = request.get_json()
        else:
            data = {}

        gcs_path = data.get('gcs_path', '')

        if not gcs_path:
            return {"error": "gcs_path required"}, 400

        processor = ArticleProcessor()
        result = processor.process(gcs_path)

        return result, 200

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"error": str(e)}, 500


if __name__ == "__main__":
    """Local testing entry point."""
    logger.info("Running in local mode")

    # Test with a sample path
    test_path = "2025-01-15/12-00-00/complete_articles.json"
    logger.info(f"Test path: {test_path}")

    date_str, run_id, filename = extract_path_info(test_path)
    source_type = extract_source_type(filename)

    logger.info(f"Extracted: date={date_str}, run={run_id}, filename={filename}")
    logger.info(f"Source type: {source_type}")
