"""
JSONL Transformer Function

Transforms Vertex AI batch prediction JSONL output to JSON format for UI consumption.
Triggered by GCS Eventarc when predictions.jsonl files are created.

Handles two types of batch outputs:
1. Enrichment results → enriched_*.json
2. Merge decision results → decision_*.json

IMPORTANT: This function aggregates results from ALL prediction folders under a
source_type directory, not just the triggered file. This prevents data loss when
multiple batch jobs (e.g., singletons + decisions) create separate prediction folders.
"""

import os
import json
import logging
import sys
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Tuple

from google.cloud import storage

# CET timezone for timestamps
CET = ZoneInfo("Europe/Berlin")

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

logger = logging.getLogger(__name__)
logger.info("JSONL Transformer Function initialized")

# Environment configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIRONMENT != 'local':
    storage_client = storage.Client()
else:
    storage_client = None
    logger.info("Running in local environment - skipping Google Cloud client initialization")

# Configuration
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')


def extract_path_info(gcs_path: str) -> Tuple[str, str, str, str]:
    """
    Extract date, run_id, job_type, and source_type from GCS path.

    Expected path formats:
    - ingestion/YYYY-MM-DD/HH-MM-SS/batch_enrichment/{source_type}/predictions.jsonl
    - ingestion/YYYY-MM-DD/HH-MM-SS/batch_merge/{source_type}/predictions.jsonl

    Args:
        gcs_path: GCS blob path

    Returns:
        Tuple of (date_str, run_id, job_type, source_type)
    """
    # Pattern for batch output paths
    pattern = r'ingestion/(\d{4}-\d{2}-\d{2})/(\d{2}-\d{2}-\d{2})/(batch_\w+)/([^/]+)/.*predictions.*\.jsonl'
    match = re.search(pattern, gcs_path)

    if match:
        date_str = match.group(1)
        run_id = match.group(2)
        job_type = match.group(3)  # batch_enrichment or batch_merge
        source_type = match.group(4)  # complete, scraped_incomplete, etc.
        return date_str, run_id, job_type, source_type

    logger.warning(f"Could not parse path: {gcs_path}")
    now = datetime.now(CET)
    return now.strftime('%Y-%m-%d'), now.strftime('%H-%M-%S'), 'unknown', 'unknown'


def download_jsonl(gcs_path: str) -> List[Dict[str, Any]]:
    """
    Download and parse JSONL file from GCS.

    Args:
        gcs_path: GCS blob path

    Returns:
        List of parsed JSON objects
    """
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(gcs_path)
        content = blob.download_as_text()

        results = []
        for line in content.strip().split('\n'):
            if line.strip():
                results.append(json.loads(line))

        logger.info(f"Downloaded {len(results)} entries from {gcs_path}")
        return results

    except Exception as e:
        logger.error(f"Error downloading JSONL: {e}")
        raise


def find_all_prediction_folders(run_folder: str, job_type: str, source_type: str) -> List[str]:
    """
    Find all prediction folders under a source_type directory.

    Multiple batch jobs may create multiple prediction-model-* folders.
    This function finds all of them to aggregate results.

    Args:
        run_folder: Run folder path (e.g., ingestion/2025-12-20/12-29-24)
        job_type: Job type (batch_enrichment or batch_merge)
        source_type: Source type (complete, scraped_incomplete, etc.)

    Returns:
        List of GCS paths to predictions.jsonl files
    """
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        prefix = f"{run_folder}/{job_type}/{source_type}/"

        prediction_files = []
        blobs = bucket.list_blobs(prefix=prefix)

        for blob in blobs:
            if blob.name.endswith('predictions.jsonl'):
                prediction_files.append(blob.name)
                logger.info(f"Found prediction file: {blob.name}")

        logger.info(f"Found {len(prediction_files)} prediction files under {prefix}")
        return prediction_files

    except Exception as e:
        logger.error(f"Error listing prediction folders: {e}")
        return []


def aggregate_all_predictions(run_folder: str, job_type: str, source_type: str) -> List[Dict[str, Any]]:
    """
    Aggregate entries from ALL prediction files under a source_type.

    This fixes the overwrite bug by collecting results from all prediction folders.

    Args:
        run_folder: Run folder path
        job_type: Job type (batch_enrichment or batch_merge)
        source_type: Source type

    Returns:
        Combined list of all prediction entries
    """
    prediction_files = find_all_prediction_folders(run_folder, job_type, source_type)

    if not prediction_files:
        logger.warning(f"No prediction files found for {job_type}/{source_type}")
        return []

    all_entries = []
    truncated_count = 0
    complete_count = 0

    for pred_file in prediction_files:
        try:
            entries = download_jsonl(pred_file)

            # Check for truncation and log warnings
            for entry in entries:
                finish_reason = entry.get('response', {}).get('candidates', [{}])[0].get('finishReason', 'UNKNOWN')
                if finish_reason == 'MAX_TOKENS':
                    truncated_count += 1
                    logger.warning(f"TRUNCATED RESPONSE (MAX_TOKENS) in {pred_file}")
                elif finish_reason == 'STOP':
                    complete_count += 1
                else:
                    logger.warning(f"Unexpected finishReason: {finish_reason} in {pred_file}")

            all_entries.extend(entries)
        except Exception as e:
            logger.error(f"Error processing {pred_file}: {e}")
            continue

    logger.info(f"Aggregated {len(all_entries)} entries from {len(prediction_files)} prediction files")
    logger.info(f"  Complete responses (STOP): {complete_count}")
    logger.info(f"  Truncated responses (MAX_TOKENS): {truncated_count}")

    if truncated_count > 0:
        logger.warning(f"WARNING: {truncated_count}/{len(all_entries)} responses were truncated!")
        logger.warning("This may result in missing articles. Consider increasing maxOutputTokens.")

    return all_entries


def extract_response_content(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the actual response content from Vertex AI batch output format.

    Vertex AI batch format:
    {
        "response": {
            "candidates": [{
                "content": {
                    "parts": [{"text": "{...json...}"}]
                }
            }]
        },
        "request": {...}
    }

    Args:
        entry: Single JSONL entry

    Returns:
        Parsed response content
    """
    try:
        # Navigate nested structure
        response = entry.get('response', {})
        candidates = response.get('candidates', [])

        if not candidates:
            logger.warning("No candidates in response")
            return {}

        content = candidates[0].get('content', {})
        parts = content.get('parts', [])

        if not parts:
            logger.warning("No parts in content")
            return {}

        text = parts[0].get('text', '{}')

        # Parse the JSON text
        return json.loads(text)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse response JSON: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error extracting response content: {e}")
        return {}


def transform_enrichment_results(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform enrichment batch results to UI-consumable format.

    Args:
        entries: List of JSONL entries from batch enrichment job

    Returns:
        List of enriched articles in ProcessedArticle format
    """
    enriched_articles = []

    for entry in entries:
        content = extract_response_content(entry)

        # Handle both single article and batch response formats
        if 'enriched_articles' in content:
            articles = content['enriched_articles']
        elif 'articles' in content:
            articles = content['articles']
        elif isinstance(content, list):
            articles = content
        else:
            # Single article response
            articles = [content] if content else []

        for article in articles:
            if not article:
                continue

            enriched_articles.append({
                'article_id': article.get('article_id', ''),
                'original_url': article.get('original_url', ''),
                'merged_from_urls': article.get('merged_from_urls', []),
                'title': article.get('title', ''),
                'summary': article.get('summary', ''),
                'summary_translation': article.get('summary_translation'),
                'x_post': article.get('x_post'),
                'source': article.get('source', ''),
                'published_date': article.get('published_date', ''),
                'categories': article.get('categories', []),
                'key_entities': article.get('key_entities', {
                    'teams': [],
                    'players': [],
                    'amounts': [],
                    'dates': [],
                    'competitions': [],
                    'locations': []
                }),
                'content_quality': article.get('content_quality', 'medium'),
                'confidence': article.get('confidence', 0.8),
                'language': article.get('language', 'tr'),
                '_processing_metadata': {
                    'processed_at': datetime.now(timezone.utc).isoformat(),
                    'processor': 'batch_enrichment'
                }
            })

    logger.info(f"Transformed {len(enriched_articles)} enriched articles")
    return enriched_articles


def transform_merge_results(entries: List[Dict[str, Any]], groups_data: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Transform merge decision batch results to articles format.

    Args:
        entries: List of JSONL entries from batch merge job
        groups_data: Original groups data (optional, for applying decisions)

    Returns:
        List of articles with merge decisions applied
    """
    # Collect all decisions from batch results
    all_decisions = []

    for entry in entries:
        content = extract_response_content(entry)

        # Handle merge decision format
        if 'decisions' in content:
            decisions = content['decisions']
        elif isinstance(content, list):
            decisions = content
        else:
            decisions = [content] if content else []

        for decision in decisions:
            if decision:
                all_decisions.append(decision)

    logger.info(f"Extracted {len(all_decisions)} merge decisions from batch")

    # If we have original groups data, apply decisions to produce articles
    # Otherwise, just return the decisions (transformer will need to handle separately)
    decided_articles = []
    for decision in all_decisions:
        decided_articles.append({
            'group_id': decision.get('group_id'),
            'decision': decision.get('decision', 'KEEP_BOTH'),
            'reason': decision.get('reason', ''),
            'primary_article_id': decision.get('primary_article_id'),
            'merged_article_ids': decision.get('merged_article_ids', []),
            '_merge_metadata': {
                'decided_at': datetime.now(timezone.utc).isoformat(),
                'processor': 'batch_merge'
            }
        })

    logger.info(f"Transformed {len(decided_articles)} merge decisions")
    return decided_articles


def load_singletons(run_folder: str, source_type: str) -> List[Dict[str, Any]]:
    """Load singleton articles saved by merge_decider."""
    try:
        singleton_path = f"{run_folder}/batch_merge/{source_type}/singletons.json"
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(singleton_path)

        if not blob.exists():
            logger.info("No singletons file found")
            return []

        content = blob.download_as_text()
        data = json.loads(content)
        singletons = data.get('articles', [])
        logger.info(f"Loaded {len(singletons)} singleton articles")
        return singletons

    except Exception as e:
        logger.warning(f"Could not load singletons: {e}")
        return []


def load_groups_data(run_folder: str, source_type: str) -> Dict[str, Any]:
    """Load original groups data for applying merge decisions."""
    try:
        # The original grouped file
        groups_path = f"{run_folder}/grouped_{source_type}_articles.json"
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(groups_path)

        if not blob.exists():
            logger.info("No groups file found")
            return {}

        content = blob.download_as_text()
        return json.loads(content)

    except Exception as e:
        logger.warning(f"Could not load groups data: {e}")
        return {}


def apply_merge_decisions(decisions: List[Dict], groups_data: Dict) -> List[Dict[str, Any]]:
    """
    Apply merge decisions to original groups to produce output articles.

    Args:
        decisions: List of LLM decisions
        groups_data: Original groups with articles

    Returns:
        List of articles with decisions applied
    """
    groups = groups_data.get('groups', [])
    if not groups:
        logger.warning("No groups in groups_data")
        return []

    # Index decisions by group_id
    decision_map = {d.get('group_id'): d for d in decisions}

    output_articles = []

    for group in groups:
        group_id = group.get('group_id', 0)
        articles = group.get('articles', [])
        decision = decision_map.get(group_id, {})

        if decision.get('decision') == 'MERGE':
            # Find primary article
            primary_id = decision.get('primary_article_id')
            primary_article = None
            merged_urls = []

            for article in articles:
                if article.get('article_id') == primary_id:
                    primary_article = article.copy()
                merged_urls.append(article.get('url', ''))

            if not primary_article and articles:
                primary_article = articles[0].copy()

            if primary_article:
                primary_article['_merge_metadata'] = {
                    'decision': 'MERGED',
                    'reason': decision.get('reason', ''),
                    'group_id': group_id,
                    'merged_from_count': len(articles),
                    'merged_urls': merged_urls
                }
                output_articles.append(primary_article)

        else:
            # KEEP_BOTH - output all articles
            for article in articles:
                article_copy = article.copy()
                article_copy['_merge_metadata'] = {
                    'decision': 'KEPT_SEPARATE',
                    'reason': decision.get('reason', ''),
                    'group_id': group_id
                }
                output_articles.append(article_copy)

    return output_articles


def upload_json(data: Any, gcs_path: str) -> str:
    """
    Upload JSON data to GCS.

    Args:
        data: Data to serialize
        gcs_path: GCS blob path

    Returns:
        GCS URI of uploaded file
    """
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(
            json.dumps(data, ensure_ascii=False, indent=2),
            content_type='application/json'
        )

        gcs_uri = f"gs://{GCS_BUCKET_NAME}/{gcs_path}"
        logger.info(f"Uploaded to {gcs_uri}")
        return gcs_uri

    except Exception as e:
        logger.error(f"Error uploading JSON: {e}")
        raise


def deduplicate_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate articles by article_id.

    When aggregating from multiple prediction files, the same article
    may appear multiple times. This keeps the first occurrence.

    Args:
        articles: List of articles (may contain duplicates)

    Returns:
        Deduplicated list of articles
    """
    seen_ids = set()
    unique_articles = []

    for article in articles:
        article_id = article.get('article_id', '')
        if article_id and article_id not in seen_ids:
            seen_ids.add(article_id)
            unique_articles.append(article)
        elif not article_id:
            # Keep articles without ID (shouldn't happen but be safe)
            unique_articles.append(article)

    if len(articles) != len(unique_articles):
        logger.info(f"Deduplicated: {len(articles)} -> {len(unique_articles)} articles")

    return unique_articles


def process_batch_output(gcs_path: str) -> Dict[str, Any]:
    """
    Main processing function.

    Aggregates results from ALL prediction folders under the source_type,
    not just the single triggered file. This prevents data loss when
    multiple batch jobs create separate prediction folders.

    Args:
        gcs_path: GCS path to predictions.jsonl file (trigger source)

    Returns:
        Processing result metadata
    """
    logger.info(f"Processing batch output: {gcs_path}")

    # Extract path info
    date_str, run_id, job_type, source_type = extract_path_info(gcs_path)
    run_folder = f"ingestion/{date_str}/{run_id}"

    logger.info(f"Date: {date_str}, Run: {run_id}, Job: {job_type}, Source: {source_type}")

    # FIXED: Aggregate from ALL prediction folders, not just the triggered file
    # This prevents overwrite bug when multiple batch jobs create separate folders
    entries = aggregate_all_predictions(run_folder, job_type, source_type)

    if not entries:
        logger.warning("No entries found in any prediction files")
        return {
            'status': 'empty',
            'entries': 0
        }

    # Transform based on job type
    if job_type == 'batch_enrichment':
        articles = transform_enrichment_results(entries)

        # Deduplicate articles by article_id (in case of overlapping batches)
        articles = deduplicate_articles(articles)

        output_filename = f"enriched_{source_type}_articles.json"

        # Upload transformed JSON
        output_path = f"{run_folder}/{output_filename}"
        output_uri = upload_json({'articles': articles}, output_path)

    elif job_type == 'batch_merge':
        # For merge, we need to apply decisions to original groups
        decisions = transform_merge_results(entries)

        # Load original groups to apply decisions
        groups_data = load_groups_data(run_folder, source_type)
        if groups_data:
            articles = apply_merge_decisions(decisions, groups_data)
        else:
            logger.warning("Could not load groups data, outputting raw decisions")
            articles = decisions

        # Load and merge singletons
        singletons = load_singletons(run_folder, source_type)
        if singletons:
            articles.extend(singletons)
            logger.info(f"Added {len(singletons)} singleton articles")

        output_filename = f"decision_{source_type}_articles.json"

        # Upload transformed JSON
        output_path = f"{run_folder}/{output_filename}"
        output_uri = upload_json({'articles': articles}, output_path)

    else:
        logger.error(f"Unknown job type: {job_type}")
        return {
            'status': 'error',
            'error': f'Unknown job type: {job_type}'
        }

    return {
        'status': 'success',
        'job_type': job_type,
        'source_type': source_type,
        'input_entries': len(entries),
        'output_articles': len(articles),
        'output_uri': output_uri
    }


def transform_jsonl(event, context):
    """
    Cloud Function entry point.

    Triggered by GCS Eventarc on predictions.jsonl file creation.

    Args:
        event: CloudEvent data
        context: Cloud Functions context
    """
    logger.info("=== JSONL TRANSFORMER FUNCTION TRIGGERED ===")

    # Extract file info from event
    if isinstance(event, dict):
        bucket = event.get('bucket', GCS_BUCKET_NAME)
        name = event.get('name', '')
    else:
        logger.error(f"Unknown event format: {type(event)}")
        return

    logger.info(f"Triggered by: gs://{bucket}/{name}")

    # Only process predictions.jsonl files
    if not name.endswith('predictions.jsonl') and 'prediction' not in name:
        logger.info(f"Ignoring file: {name} (not a predictions file)")
        return

    try:
        result = process_batch_output(name)
        logger.info(f"Processing result: {result}")

    except Exception as e:
        logger.error(f"Error processing: {e}", exc_info=True)

    logger.info("=== JSONL TRANSFORMER FUNCTION COMPLETED ===")


# HTTP entry point for Cloud Run
def main(request):
    """HTTP entry point for testing."""
    try:
        data = request.get_json() or {}
        gcs_path = data.get('gcs_path', '')

        if not gcs_path:
            return {'error': 'gcs_path required'}, 400

        result = process_batch_output(gcs_path)
        return result

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {'error': str(e)}, 500


if __name__ == "__main__":
    # Local testing
    test_path = "ingestion/2025-12-20/01-01-08/batch_enrichment/complete/predictions.jsonl"
    print(f"Testing with: {test_path}")
    print(extract_path_info(test_path))
