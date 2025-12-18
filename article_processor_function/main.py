"""
Article Processor Function - Main Entry Point

Unified article processing pipeline using vector embeddings for grouping
and a single LLM call per group for all processing tasks.

Replaces the two-stage batch_builder + result_merger architecture.
"""

import os
import json
import base64
import asyncio
import logging
import sys
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set

from google.cloud import pubsub_v1, storage
from google import genai
from google.genai.types import HttpOptions

from embedding_service import EmbeddingService
from grouping_service import GroupingService, ArticleGroup
from llm_processor import LLMProcessor
from models import ProcessingSummary, ProcessingOutput

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
    publisher = pubsub_v1.PublisherClient()
    storage_client = storage.Client()
else:
    publisher = None
    storage_client = None
    logger.info("Running in local environment - skipping Google Cloud client initialization")

# Configuration from environment variables
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
SESSION_DATA_CREATED_TOPIC = os.getenv('SESSION_DATA_CREATED_TOPIC', 'session-data-created')
PROCESSING_COMPLETED_TOPIC = os.getenv('PROCESSING_COMPLETED_TOPIC', 'processing-completed')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
NEWS_DATA_ROOT_PREFIX = os.getenv('NEWS_DATA_ROOT_PREFIX', 'news_data/')
VERTEX_AI_LOCATION = os.getenv('VERTEX_AI_LOCATION', 'us-central1')
VERTEX_AI_MODEL = os.getenv('VERTEX_AI_MODEL', 'gemini-3-pro-preview')
THINKING_LEVEL = os.getenv('THINKING_LEVEL', 'LOW')

# Embedding and grouping configuration
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-004')
SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.85'))


class ArticleProcessor:
    """
    Main orchestrator for the unified article processing pipeline.

    Flow:
    1. Download session data from GCS
    2. Pre-filter exact duplicates (code-based)
    3. Generate embeddings
    4. Compute similarity and form groups
    5. Create batch LLM requests per group
    6. Submit batch job and save results
    """

    def __init__(self):
        """Initialize the article processor with necessary clients."""
        self.storage_client = storage_client
        self.genai_client = None
        self.embedding_service = None
        self.grouping_service = None
        self.llm_processor = None

        if ENVIRONMENT != 'local':
            try:
                # Initialize Vertex AI client
                if "gemini-3" in VERTEX_AI_MODEL.lower():
                    location = "global"
                else:
                    location = VERTEX_AI_LOCATION

                http_options = HttpOptions(api_version="v1")

                self.genai_client = genai.Client(
                    vertexai=True,
                    project=PROJECT_ID,
                    location=location,
                    http_options=http_options
                )
                logger.info(f"Vertex AI client initialized: project={PROJECT_ID}, location={location}")

                # Initialize services
                self.embedding_service = EmbeddingService(self.genai_client)
                self.grouping_service = GroupingService(threshold=SIMILARITY_THRESHOLD)
                self.llm_processor = LLMProcessor(
                    genai_client=self.genai_client,
                    storage_client=self.storage_client,
                    bucket_name=GCS_BUCKET_NAME,
                    model=VERTEX_AI_MODEL,
                    thinking_level=THINKING_LEVEL,
                )

            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI client: {e}")

    def download_session_data(self, gcs_uris: List[str]) -> List[Dict[str, Any]]:
        """
        Download and parse session data files from GCS.

        Args:
            gcs_uris: List of GCS URIs pointing to session data JSON files

        Returns:
            Combined list of all articles from all session files
        """
        all_articles = []

        for gcs_uri in gcs_uris:
            try:
                if not gcs_uri.startswith('gs://'):
                    logger.warning(f"Invalid GCS URI: {gcs_uri}")
                    continue

                parts = gcs_uri.replace('gs://', '').split('/', 1)
                bucket_name = parts[0]
                blob_path = parts[1] if len(parts) > 1 else ''

                bucket = self.storage_client.bucket(bucket_name)
                blob = bucket.blob(blob_path)
                content = blob.download_as_text()

                data = json.loads(content)
                articles = data.get('articles', [])

                # Add source metadata to each article
                for article in articles:
                    if 'article_id' not in article or not article['article_id']:
                        # Generate article_id from URL if missing
                        url = article.get('url', '')
                        article['article_id'] = hashlib.md5(url.encode()).hexdigest()[:16]

                all_articles.extend(articles)
                logger.info(f"Downloaded {len(articles)} articles from {gcs_uri}")

            except Exception as e:
                logger.error(f"Error downloading {gcs_uri}: {e}")
                continue

        logger.info(f"Total articles downloaded: {len(all_articles)}")
        return all_articles

    def pre_filter_duplicates(self, articles: List[Dict]) -> Tuple[List[Dict], int]:
        """
        Remove exact duplicates based on URL and title similarity.

        This is a fast, code-based pre-filter before embedding generation.

        Args:
            articles: List of raw articles

        Returns:
            Tuple of (filtered_articles, num_removed)
        """
        if not articles:
            return [], 0

        seen_urls: Set[str] = set()
        seen_titles: Dict[str, int] = {}  # title -> index of best article
        filtered = []

        def normalize_url(url: str) -> str:
            """Normalize URL for comparison."""
            url = url.lower().strip()
            # Remove query params and fragments
            url = url.split('?')[0].split('#')[0]
            # Remove trailing slashes
            url = url.rstrip('/')
            return url

        def normalize_title(title: str) -> str:
            """Normalize title for comparison."""
            return title.lower().strip()

        for article in articles:
            url = article.get('url', '')
            title = article.get('title', '')

            norm_url = normalize_url(url)
            norm_title = normalize_title(title)

            # Skip if exact URL match
            if norm_url and norm_url in seen_urls:
                logger.debug(f"Skipping duplicate URL: {url[:50]}...")
                continue

            # Skip if exact title match (keep longer body)
            if norm_title and norm_title in seen_titles:
                existing_idx = seen_titles[norm_title]
                existing_body_len = len(filtered[existing_idx].get('body', ''))
                new_body_len = len(article.get('body', ''))

                if new_body_len > existing_body_len:
                    # Replace with better version
                    filtered[existing_idx] = article
                    logger.debug(f"Replacing duplicate title with better version: {title[:50]}...")
                continue

            # Add article
            seen_urls.add(norm_url)
            if norm_title:
                seen_titles[norm_title] = len(filtered)
            filtered.append(article)

        num_removed = len(articles) - len(filtered)
        logger.info(f"Pre-filter removed {num_removed} exact duplicates ({len(filtered)} remaining)")

        return filtered, num_removed

    def extract_path_info(self, source_files: List[str]) -> Tuple[str, str, str, str]:
        """
        Extract path components from source file URIs.

        Args:
            source_files: List of GCS URIs

        Returns:
            Tuple of (source_type, date_str, run_id, ingestion_base_path)
        """
        default_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        default_run = datetime.now(timezone.utc).strftime("%H-%M-%S")

        if not source_files:
            return "unknown", default_date, default_run, None

        first_file = source_files[0]

        # New structure: ingestion/api/YYYY-MM-DD/HH-MM-SS/
        api_pattern = r'(ingestion/api/(\d{4}-\d{2}-\d{2})/(\d{2}-\d{2}-\d{2}))'
        api_match = re.search(api_pattern, first_file)

        if api_match:
            base_path = api_match.group(1)
            date_str = api_match.group(2)
            run_id = api_match.group(3)
            logger.info(f"Detected API ingestion path: {base_path}")
            return "api", date_str, run_id, base_path

        # New structure: ingestion/scrape/YYYY-MM-DD/HH-MM-SS/
        scrape_pattern = r'(ingestion/scrape/(\d{4}-\d{2}-\d{2})/(\d{2}-\d{2}-\d{2}))'
        scrape_match = re.search(scrape_pattern, first_file)

        if scrape_match:
            base_path = scrape_match.group(1)
            date_str = scrape_match.group(2)
            run_id = scrape_match.group(3)
            logger.info(f"Detected scrape ingestion path: {base_path}")
            return "scrape", date_str, run_id, base_path

        # Legacy pattern (for backwards compatibility during transition)
        legacy_api_pattern = r'news_data/api/\d{4}-\d{2}/(\d{4}-\d{2}-\d{2})/run_(\d{2}-\d{2}-\d{2})'
        legacy_match = re.search(legacy_api_pattern, first_file)

        if legacy_match:
            date_str = legacy_match.group(1)
            run_id = legacy_match.group(2)
            logger.info(f"Detected legacy API path (migration mode)")
            return "api_legacy", date_str, run_id, None

        return "unknown", default_date, default_run, None

    async def process(self, gcs_files: List[str], run_id: str) -> Dict[str, Any]:
        """
        Main processing pipeline.

        Args:
            gcs_files: List of GCS URIs to process
            run_id: Unique run identifier

        Returns:
            Processing result with metadata
        """
        logger.info(f"Starting article processing: {len(gcs_files)} files, run_id={run_id}")

        # Step 1: Download all session data
        logger.info("Step 1: Downloading session data...")
        articles = self.download_session_data(gcs_files)

        if not articles:
            logger.warning("No articles found in session data")
            return {"status": "empty", "total_articles": 0}

        total_input = len(articles)

        # Step 2: Pre-filter exact duplicates
        logger.info("Step 2: Pre-filtering exact duplicates...")
        articles, prefilter_removed = self.pre_filter_duplicates(articles)

        if not articles:
            logger.warning("All articles removed by pre-filter")
            return {"status": "empty_after_prefilter", "total_articles": total_input, "prefilter_removed": prefilter_removed}

        # Step 3: Generate embeddings
        logger.info("Step 3: Generating embeddings...")
        embeddings = self.embedding_service.generate_embeddings(articles)

        # Step 4: Form groups
        logger.info("Step 4: Forming article groups...")
        groups = self.grouping_service.group_articles(embeddings)

        # Separate multi-article groups from singletons
        multi_groups = [g for g in groups if not g.is_singleton]
        singleton_groups = [g for g in groups if g.is_singleton]

        logger.info(f"Grouped into {len(multi_groups)} multi-article groups and {len(singleton_groups)} singletons")

        # Step 5: Create batch requests
        logger.info("Step 5: Creating batch requests...")
        prompt_template = self.llm_processor.load_prompt_template()

        # Create requests for multi-article groups
        batch_requests = self.llm_processor.create_batch_request(
            groups=multi_groups + singleton_groups,  # Process all together
            articles=articles,
            prompt_template=prompt_template,
        )

        # Step 6: Upload batch request and submit job
        logger.info("Step 6: Uploading batch request and submitting job...")

        source_type, date_str, extracted_run_id, ingestion_base_path = self.extract_path_info(gcs_files)

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

        # Output always goes to processing/ folder (separate from ingestion/)
        # Structure: processing/YYYY-MM-DD/HH-MM-SS/
        processing_base = f"processing/{date_str}/{extracted_run_id}"
        request_path = f"{processing_base}/llm/requests/batch.jsonl"
        results_path = f"{processing_base}/llm/results/"
        output_path = f"{processing_base}/articles.json"
        manifest_path = f"{processing_base}/source_manifest.json"

        # Upload batch request
        batch_request_uri = self.llm_processor.write_batch_jsonl(batch_requests, request_path)

        # Submit batch job
        display_name = f"aisports_{source_type}_processor_{date_str.replace('-', '')}_{timestamp}"
        job_name, results_uri = self.llm_processor.submit_batch_job(
            batch_request_uri=batch_request_uri,
            output_path=results_path,
            display_name=display_name,
        )

        # Save source manifest (links processing output back to ingestion source)
        source_manifest = {
            "source_type": source_type,
            "source_paths": gcs_files,
            "ingestion_base_path": ingestion_base_path,
            "input_article_count": total_input,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }

        bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
        manifest_blob = bucket.blob(manifest_path)
        manifest_blob.upload_from_string(json.dumps(source_manifest, indent=2), content_type='application/json')
        logger.info(f"Source manifest saved to gs://{GCS_BUCKET_NAME}/{manifest_path}")

        # Save processing metadata
        metadata = {
            "status": "batch_job_submitted",
            "run_id": run_id,
            "job_name": job_name,
            "results_uri": results_uri,
            "output_path": output_path,
            "source_manifest_path": manifest_path,
            "source_type": source_type,
            "total_input_articles": total_input,
            "articles_after_prefilter": len(articles),
            "prefilter_removed": prefilter_removed,
            "num_groups": len(groups),
            "multi_article_groups": len(multi_groups),
            "singleton_groups": len(singleton_groups),
            "embedding_model": EMBEDDING_MODEL,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "llm_model": VERTEX_AI_MODEL,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save metadata to GCS
        metadata_path = f"{processing_base}/metadata.json"
        metadata_blob = bucket.blob(metadata_path)
        metadata_blob.upload_from_string(json.dumps(metadata, indent=2), content_type='application/json')

        logger.info(f"Processing metadata saved to gs://{GCS_BUCKET_NAME}/{metadata_path}")
        logger.info(f"Batch job submitted: {job_name}")

        return metadata


async def _process_request(message_data: dict):
    """
    Process an incoming request from PubSub.

    Args:
        message_data: Decoded PubSub message data
    """
    logger.info(f"Received processing request: {message_data}")

    # Validate message format
    if message_data.get("status") != "batch_success":
        logger.error(f"Invalid message status: {message_data.get('status')}")
        return

    success_messages = message_data.get("success_messages", [])
    if not success_messages:
        logger.error("No success messages found")
        return

    # Extract GCS paths
    gcs_files = []
    for msg in success_messages:
        gcs_path = msg.get("gcs_path")
        if gcs_path and gcs_path.startswith("gs://"):
            gcs_files.append(gcs_path)

    if not gcs_files:
        logger.error("No valid GCS files found")
        return

    # Get or generate run_id
    run_id = message_data.get("run_id")
    if not run_id:
        run_id = f"run_{datetime.now(timezone.utc).strftime('%H-%M-%S')}"

    logger.info(f"Processing {len(gcs_files)} files with run_id={run_id}")

    try:
        processor = ArticleProcessor()

        if not processor.genai_client and ENVIRONMENT != 'local':
            logger.error("Vertex AI client not available")
            return

        result = await processor.process(gcs_files, run_id)

        # Publish completion message
        if ENVIRONMENT != 'local' and result.get("status") == "batch_job_submitted":
            completion_message = {
                "status": "processing_job_created",
                "run_id": run_id,
                "job_name": result.get("job_name"),
                "results_uri": result.get("results_uri"),
                "output_path": result.get("output_path"),
                "source_files_count": len(gcs_files),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            topic_path = publisher.topic_path(PROJECT_ID, PROCESSING_COMPLETED_TOPIC)
            future = publisher.publish(topic_path, json.dumps(completion_message).encode("utf-8"))
            future.result()
            logger.info(f"Completion message published to {PROCESSING_COMPLETED_TOPIC}")

        logger.info(f"Processing complete: {result}")

    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)


def process_articles(event, context):
    """
    Cloud Function entry point.

    Triggered by PubSub message from session-data-created topic.

    Args:
        event: PubSub event data
        context: Cloud Functions context
    """
    logger.info("=== ARTICLE PROCESSOR FUNCTION TRIGGERED ===")
    logger.info(f"Event: {event}")

    if isinstance(event, dict) and "data" in event:
        try:
            message_data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
            logger.info(f"Decoded message: {message_data}")
            asyncio.run(_process_request(message_data))
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
    else:
        logger.error("Invalid PubSub message format")

    logger.info("=== ARTICLE PROCESSOR FUNCTION COMPLETED ===")


if __name__ == "__main__":
    """Local testing entry point."""
    logger.info("Running in local mode")

    test_message = {
        "status": "batch_success",
        "run_id": "run_test_local",
        "success_messages": [
            {
                # New path structure: ingestion/api/YYYY-MM-DD/HH-MM-SS/articles.json
                "gcs_path": f"gs://{GCS_BUCKET_NAME}/ingestion/api/2025-01-15/12-00-00/articles.json"
            }
        ]
    }

    asyncio.run(_process_request(test_message))
