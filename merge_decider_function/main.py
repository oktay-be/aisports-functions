"""
Merge Decider Function - Batch LLM Decision on Article Groups

Stage 3 of the article processing pipeline.
Submits batch job to Vertex AI for merge decisions.
Results are transformed by jsonl_transformer_function.

Flow:
1. Triggered by GCS file creation (grouped_*.json)
2. Creates JSONL batch request with all groups
3. Submits batch job to Vertex AI
4. Exits immediately (no polling)
5. jsonl_transformer_function handles results when batch completes
"""

import os
import json
import logging
import sys
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Tuple

# CET timezone for run timestamps
CET = ZoneInfo("Europe/Berlin")

from google.cloud import storage
from google import genai
from google.genai.types import HttpOptions, CreateBatchJobConfig

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

logger = logging.getLogger(__name__)
logger.info("Merge Decider Function initialized (BATCH MODE)")

# Environment configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIRONMENT != 'local':
    storage_client = storage.Client()
else:
    storage_client = None
    logger.info("Running in local environment")

# Configuration
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
VERTEX_AI_LOCATION = os.getenv('VERTEX_AI_LOCATION', 'us-central1')
VERTEX_AI_MODEL = os.getenv('VERTEX_AI_MODEL', 'gemini-2.0-flash')

# File patterns that trigger this function
TRIGGER_PATTERNS = [
    'grouped_complete_articles.json',
    'grouped_scraped_incomplete_articles.json',
    'grouped_scraped_articles.json',
]

# Merge decision prompt (used in batch request)
MERGE_DECISION_PROMPT = """You are a sports news editor deciding whether similar articles should be merged or kept separate.

## Task
Analyze the following groups of similar articles and decide for each:
- **MERGE**: If they cover the SAME event (same match, same transfer, same announcement)
- **KEEP_BOTH**: If they cover DIFFERENT angles or aspects of the news

## Decision Criteria

### MERGE when:
- Articles report the exact same match result
- Articles announce the same transfer deal
- Articles quote the same press conference
- Articles are essentially duplicates with minor wording differences

### KEEP_BOTH when:
- One is a match report, another is player interview
- One is breaking news, another is in-depth analysis
- Articles cover different aspects of the same broader topic
- Articles have significantly different perspectives or sources

## Output Format
Return ONLY valid JSON with decisions for ALL groups:
```json
{
  "decisions": [
    {
      "group_id": 1,
      "decision": "MERGE" or "KEEP_BOTH",
      "reason": "Brief explanation",
      "primary_article_id": "ID of best article if MERGE, null if KEEP_BOTH",
      "merged_article_ids": ["IDs of merged articles"] or []
    }
  ]
}
```

## Article Groups to Analyze:
"""


def extract_path_info(gcs_path: str) -> Tuple[str, str, str]:
    """Extract date, run_id, and filename from GCS path."""
    pattern = r'(\d{4}-\d{2}-\d{2})/(\d{2}-\d{2}-\d{2})/([^/]+\.json)$'
    match = re.search(pattern, gcs_path)

    if match:
        return match.group(1), match.group(2), match.group(3)

    now = datetime.now(CET)
    return now.strftime('%Y-%m-%d'), now.strftime('%H-%M-%S'), 'unknown.json'


def extract_source_type(filename: str) -> str:
    """Extract source type from filename."""
    if 'complete' in filename and 'incomplete' not in filename:
        return 'complete'
    elif 'scraped_incomplete' in filename:
        return 'scraped_incomplete'
    elif 'scraped' in filename:
        return 'scraped'
    return 'unknown'


class MergeDecider:
    """
    Batch-based merge decision maker for article groups.
    Submits batch jobs to Vertex AI and exits immediately.
    """

    def __init__(self):
        self.storage_client = storage_client
        self.genai_client = None

        if ENVIRONMENT != 'local':
            try:
                # Use regional endpoint for batch processing
                regional_endpoint = f"https://{VERTEX_AI_LOCATION}-aiplatform.googleapis.com/"

                http_options = HttpOptions(
                    api_version="v1",
                    base_url=regional_endpoint
                )

                self.genai_client = genai.Client(
                    vertexai=True,
                    project=PROJECT_ID,
                    location=VERTEX_AI_LOCATION,
                    http_options=http_options
                )
                logger.info(f"Vertex AI client initialized for batch: model={VERTEX_AI_MODEL}")

            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI: {e}")

    def download_groups(self, gcs_path: str) -> Dict[str, Any]:
        """Download grouped articles from GCS."""
        try:
            bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(gcs_path)
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            logger.error(f"Error downloading {gcs_path}: {e}")
            return {}

    def create_batch_request(self, groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create batch request entries for groups.

        Args:
            groups: List of article groups to process

        Returns:
            List of batch request entries
        """
        batch_requests = []

        # Group into batches of 5 groups per request (smaller batches for merge decisions)
        batch_size = 5

        for i in range(0, len(groups), batch_size):
            batch = groups[i:i + batch_size]

            # Prepare input for this batch
            llm_input = {
                "groups": [
                    {
                        "group_id": g.get('group_id', idx),
                        "max_similarity": g.get('max_similarity', 0),
                        "articles": [
                            {
                                "article_id": a.get('article_id', ''),
                                "title": a.get('title', ''),
                                "body": (a.get('body', '') or '')[:1000],
                                "source": a.get('source', '')
                            }
                            for a in g.get('articles', [])
                        ]
                    }
                    for idx, g in enumerate(batch, start=i)
                ]
            }

            prompt = MERGE_DECISION_PROMPT + f"\n```json\n{json.dumps(llm_input, ensure_ascii=False, indent=2)}\n```"

            # Create batch request entry
            request_entry = {
                "request": {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": prompt}]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 4096,
                        "responseMimeType": "application/json"
                    }
                }
            }

            batch_requests.append(request_entry)

        return batch_requests

    def upload_batch_request(self, requests: List[Dict], run_folder: str, source_type: str) -> str:
        """
        Upload batch request JSONL to GCS.

        Args:
            requests: List of batch request entries
            run_folder: Run folder path
            source_type: Source type (complete, scraped_incomplete, etc.)

        Returns:
            GCS URI of uploaded file
        """
        # Create JSONL content
        jsonl_content = '\n'.join(json.dumps(r, ensure_ascii=False) for r in requests)

        # Upload path
        blob_path = f"{run_folder}/batch_merge/{source_type}/request.jsonl"

        bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(jsonl_content, content_type='application/x-ndjson')

        gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_path}"
        logger.info(f"Uploaded batch request to {gcs_uri}")

        return gcs_uri

    def submit_batch_job(self, request_uri: str, run_folder: str, source_type: str) -> Tuple[str, str]:
        """
        Submit batch job to Vertex AI.

        Args:
            request_uri: GCS URI of batch request JSONL
            run_folder: Run folder path
            source_type: Source type for output path

        Returns:
            Tuple of (job_name, output_uri)
        """
        # Output path - jsonl_transformer will be triggered here
        output_uri = f"gs://{GCS_BUCKET_NAME}/{run_folder}/batch_merge/{source_type}/"

        try:
            batch_config = CreateBatchJobConfig(dest=output_uri)

            logger.info(f"Submitting batch job...")
            logger.info(f"  Model: {VERTEX_AI_MODEL}")
            logger.info(f"  Source: {request_uri}")
            logger.info(f"  Output: {output_uri}")

            job = self.genai_client.batches.create(
                model=VERTEX_AI_MODEL,
                src=request_uri,
                config=batch_config
            )

            logger.info(f"Batch job submitted successfully!")
            logger.info(f"  Job name: {job.name}")
            logger.info(f"  Job state: {job.state}")

            return job.name, output_uri

        except Exception as e:
            logger.error(f"Error submitting batch job: {e}")
            raise

    def save_batch_metadata(self, run_folder: str, source_type: str,
                           job_name: str, output_uri: str,
                           group_count: int) -> str:
        """Save batch job metadata for tracking."""
        metadata = {
            "job_name": job_name,
            "output_uri": output_uri,
            "source_type": source_type,
            "group_count": group_count,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "status": "submitted"
        }

        blob_path = f"{run_folder}/batch_merge/{source_type}/metadata.json"
        bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(metadata, indent=2),
            content_type='application/json'
        )

        logger.info(f"Saved batch metadata to {blob_path}")
        return blob_path

    def process(self, gcs_path: str) -> Dict[str, Any]:
        """
        Main processing pipeline.
        Creates batch request and submits job, then exits.

        Args:
            gcs_path: GCS path to grouped_*.json file

        Returns:
            Processing metadata
        """
        date_str, run_id, filename = extract_path_info(gcs_path)
        source_type = extract_source_type(filename)
        run_folder = f"ingestion/{date_str}/{run_id}"

        logger.info(f"Processing: date={date_str}, run={run_id}, source={source_type}")

        # Download groups
        data = self.download_groups(gcs_path)
        groups = data.get('groups', [])

        if not groups:
            logger.warning("No groups found")
            return {"status": "empty", "groups": 0}

        # Filter to only groups with 2+ articles (single articles don't need merge decisions)
        groups_to_process = [g for g in groups if len(g.get('articles', [])) >= 2]
        singleton_groups = [g for g in groups if len(g.get('articles', [])) < 2]

        logger.info(f"Groups: {len(groups)} total, {len(groups_to_process)} need decisions, {len(singleton_groups)} singletons")

        if not groups_to_process:
            # All singletons - create output directly without LLM
            output_articles = []
            for group in singleton_groups:
                for article in group.get('articles', []):
                    article_copy = article.copy()
                    article_copy['_merge_metadata'] = {
                        'decision': 'SINGLETON',
                        'reason': 'Single article in group',
                        'group_id': group.get('group_id', 0)
                    }
                    output_articles.append(article_copy)

            # Save directly (skip batch)
            output_path = f"{run_folder}/singleton_{source_type}_articles.json"
            bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(output_path)
            blob.upload_from_string(
                json.dumps({'articles': output_articles}, ensure_ascii=False, indent=2),
                content_type='application/json'
            )
            logger.info(f"All singletons - saved directly to {output_path}")

            return {
                "status": "singletons_only",
                "date": date_str,
                "run_id": run_id,
                "source_type": source_type,
                "singleton_count": len(singleton_groups),
                "output_articles": len(output_articles),
                "output_file": output_path
            }

        # Save singletons for later merge (they'll be combined with batch results)
        if singleton_groups:
            singleton_articles = []
            for group in singleton_groups:
                for article in group.get('articles', []):
                    article_copy = article.copy()
                    article_copy['_merge_metadata'] = {
                        'decision': 'SINGLETON',
                        'reason': 'Single article in group',
                        'group_id': group.get('group_id', 0)
                    }
                    singleton_articles.append(article_copy)

            singleton_path = f"{run_folder}/batch_merge/{source_type}/singletons.json"
            bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(singleton_path)
            blob.upload_from_string(
                json.dumps({'articles': singleton_articles}, ensure_ascii=False, indent=2),
                content_type='application/json'
            )
            logger.info(f"Saved {len(singleton_articles)} singleton articles")

        # Create batch request for groups needing decisions
        batch_requests = self.create_batch_request(groups_to_process)
        logger.info(f"Created {len(batch_requests)} batch request entries")

        # Upload batch request to GCS
        request_uri = self.upload_batch_request(batch_requests, run_folder, source_type)

        # Submit batch job
        job_name, output_uri = self.submit_batch_job(request_uri, run_folder, source_type)

        # Save metadata
        self.save_batch_metadata(run_folder, source_type, job_name, output_uri, len(groups_to_process))

        return {
            "status": "batch_submitted",
            "date": date_str,
            "run_id": run_id,
            "source_type": source_type,
            "input_file": gcs_path,
            "total_groups": len(groups),
            "groups_for_decision": len(groups_to_process),
            "singleton_groups": len(singleton_groups),
            "batch_requests": len(batch_requests),
            "job_name": job_name,
            "output_uri": output_uri
        }


def process_groups(event, context):
    """
    Cloud Function entry point.
    Triggered by GCS Eventarc on grouped_*.json creation.
    """
    logger.info("=== MERGE DECIDER FUNCTION TRIGGERED (BATCH MODE) ===")

    if isinstance(event, dict):
        bucket = event.get('bucket', GCS_BUCKET_NAME)
        name = event.get('name', '')
    else:
        logger.error(f"Unknown event format: {type(event)}")
        return

    logger.info(f"Triggered by: gs://{bucket}/{name}")

    filename = name.split('/')[-1] if name else ''
    if filename not in TRIGGER_PATTERNS:
        logger.info(f"Ignoring file: {filename}")
        return

    try:
        decider = MergeDecider()

        if not decider.genai_client and ENVIRONMENT != 'local':
            logger.error("Vertex AI client not available")
            return

        result = decider.process(name)
        logger.info(f"Result: {result}")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

    logger.info("=== MERGE DECIDER FUNCTION COMPLETED ===")


def main(request):
    """HTTP entry point for Cloud Run."""
    logger.info("=== MERGE DECIDER HTTP TRIGGERED ===")

    try:
        data = request.get_json() if request.is_json else {}
        gcs_path = data.get('gcs_path', '')

        if not gcs_path:
            return {"error": "gcs_path required"}, 400

        decider = MergeDecider()
        result = decider.process(gcs_path)

        return result, 200

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"error": str(e)}, 500


if __name__ == "__main__":
    logger.info("Running in local mode")
    test_path = "ingestion/2025-01-15/12-00-00/grouped_complete_articles.json"
    logger.info(f"Test path: {test_path}")
