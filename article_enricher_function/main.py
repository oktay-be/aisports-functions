"""
Article Enricher Function - Batch LLM Enrichment for Articles

Final stage of the article processing pipeline.
Submits batch job to Vertex AI for enrichment (summaries, X posts, translations).
Results are transformed by jsonl_transformer_function.

Flow:
1. Triggered by GCS file creation (singleton_*.json, decision_*.json)
2. Creates JSONL batch request with all articles
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
from google.genai.types import CreateBatchJobConfig

# Import response schema (following result_merger_function pattern)
try:
    from models import VERTEX_AI_RESPONSE_SCHEMA
    SCHEMA_AVAILABLE = True
except ImportError:
    SCHEMA_AVAILABLE = False
    VERTEX_AI_RESPONSE_SCHEMA = None

# Allow env var override for structured output (default: true if schema available)
STRUCTURED_OUTPUT = os.getenv('STRUCTURED_OUTPUT', 'true').lower() == 'true'
SCHEMA_AVAILABLE = SCHEMA_AVAILABLE and STRUCTURED_OUTPUT

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

logger = logging.getLogger(__name__)
logger.info("Article Enricher Function initialized (BATCH MODE)")

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
    'singleton_complete_articles.json',
    'singleton_scraped_incomplete_articles.json',
    'singleton_scraped_articles.json',
    'decision_complete_articles.json',
    'decision_scraped_incomplete_articles.json',
    'decision_scraped_articles.json',
]

# Enrichment prompt (used in batch request)
ENRICHMENT_PROMPT = """You are a sports news editor enriching articles for a Turkish sports news aggregator.

## Task
For each article provided, generate:
1. **summary** - Comprehensive summary in the ORIGINAL LANGUAGE of the article
2. **x_post** - Twitter/X post in TURKISH (max 280 chars, informative, with hashtags)
3. **summary_translation** - Turkish translation if article is NOT in Turkish (null otherwise)
4. **categories** - List of category tags with confidence scores
5. **key_entities** - Extracted teams, players, amounts, dates, competitions, locations
6. **confidence** - Overall confidence score (0.0-1.0)
7. **content_quality** - "high", "medium", or "low"

## IMPORTANT: Data Preservation
You MUST preserve the following fields exactly as they appear in the input:
- `article_id` (mapped from `url` in input)
- `original_url` (mapped from `url` in input)
- `merged_from_urls` (mapped from `url` in input)
- `publish_date` (from input)
- `source`

## Category Taxonomy (STRICT)

**Sport Tags (for non-football):**
- `basketball`, `volleyball`, `other-sports`

**Football Tags:**
- Transfers: `transfers` (covers confirmed, rumors, negotiations, interest - use this single tag)
- Contracts: `contract-renewals`, `contract-disputes`, `departures`
- Matches: `match-results`, `match-preview`, `match-report`, `match-postponement`
- Analysis: `tactical-analysis`, `performance-analysis`, `league-standings`
- Competitions: `super-lig`, `champions-league`, `european-competitions`, `domestic-cups`, `turkish-cup`
- `international-tournaments`, `youth-competitions`, `womens-football`
- Club: `club-news`, `squad-changes`, `injuries`, `stadium-infrastructure`
- Disciplinary: `disciplinary-actions`, `field-incidents`, `off-field-scandals`, `corruption-allegations`, `legal-issues`
- Politics: `federation-politics`, `elections-management`, `government-sports`, `uefa-fifa-matters`, `policy-changes`
- Fans: `fan-activity`, `fan-rivalry`, `fan-protest`
- Rivalry: `team-rivalry`, `personal-rivalry`, `derby`
- Media: `interviews`, `social-media`, `gossip-entertainment`, `player-statement`, `club-statement`

**Keyword Tags (REQUIRED when article mentions these):**
{formatted_keywords}

## IMPORTANT: Keyword-Based Tagging
For each article, check the `keywords_used` field in the input. If the article content mentions any of these keywords,
you MUST add that keyword as a category tag with confidence 0.8-0.95 based on how prominently it appears.
Example: if keywords_used=["fenerbahce"] and article mentions Fenerbahce → add {{"tag": "fenerbahce", "confidence": 0.9}}

## x_post Rules (CRITICAL)
- ALWAYS in Turkish
- Max 280 characters
- Include relevant hashtags: #FenerbahceSK, #Galatasaray, #Besiktas, #SuperLig etc.
- Be informative, not clickbait

## Output Format
Return JSON with format:
```json
{{
    "enriched_articles": [
        {{
            "article_id": "original_id",
            "original_url": "http://...",
            "merged_from_urls": ["http://...", "http://..."],
            "title": "original_title",
            "summary": "...",
            "x_post": "Turkish X post with #hashtags",
            "summary_translation": "Turkish translation or null",
            "categories": [{{"tag": "transfers-confirmed", "confidence": 0.9}}],
            "key_entities": {{
                "teams": ["Fenerbahce"],
                "players": ["Player Name"],
                "amounts": ["10M EUR"],
                "dates": ["2025-01-15"],
                "competitions": ["Super Lig"],
                "locations": ["Istanbul"]
            }},
            "confidence": 0.85,
            "content_quality": "high"
        }}
    ]
}}

## Input
The articles to process are provided in the attached JSON file with this structure:
```json
{{
    "articles": [
        {{
            "article_id": "unique_id",
            "title": "Article title",
            "body": "Full article body...",
            "url": "https://...",
            "merged_from_urls": ["https://..."],
            "source": "example.com",
            "publish_date": "2025-01-15T10:00:00Z",
            "keywords_used": ["kw1", "kw2", ...]
        }}
    ]
}}
```

## CRITICAL INSTRUCTIONS
1. Process **EVERY SINGLE article** in the attached file - do NOT skip any
2. Return **EXACTLY the same number of articles** as provided in the input
3. Do NOT merge, deduplicate, or combine similar articles - each article must be enriched separately
4. Even if articles cover the same topic, treat each as a unique item requiring its own enrichment
5. The input has already been deduplicated - your job is ONLY to enrich, not to filter

Process ALL articles and return enriched versions for EACH ONE.
"""


def extract_path_info(gcs_path: str) -> Tuple[str, str, str]:
    """Extract date, run_id, and filename from GCS path."""
    pattern = r'(\d{4}-\d{2}-\d{2})/(\d{2}-\d{2}-\d{2})/([^/]+\.json)$'
    match = re.search(pattern, gcs_path)

    if match:
        return match.group(1), match.group(2), match.group(3)

    now = datetime.now(CET)
    return now.strftime('%Y-%m-%d'), now.strftime('%H-%M-%S'), 'unknown.json'


def extract_output_prefix(filename: str) -> str:
    """
    Extract output prefix from filename.
    singleton_complete_articles.json -> enriched_singleton_complete_articles
    decision_complete_articles.json -> enriched_decision_complete_articles
    """
    base = filename.replace('.json', '')
    return f"enriched_{base}"


def extract_source_type(filename: str) -> str:
    """Extract source type for batch output path."""
    if 'complete' in filename and 'incomplete' not in filename:
        return 'complete'
    elif 'scraped_incomplete' in filename:
        return 'scraped_incomplete'
    elif 'scraped' in filename:
        return 'scraped'
    return 'unknown'


def extract_branch_type(filename: str) -> str:
    """
    Extract branch type from filename to prevent path collisions.
    
    singleton_complete_articles.json -> 'singleton'
    decision_complete_articles.json -> 'merged'
    """
    if filename.startswith('singleton_'):
        return 'singleton'
    elif filename.startswith('decision_'):
        return 'merged'
    return 'unknown'


class ArticleEnricher:
    """
    Batch-based article enrichment service.
    Submits batch jobs to Vertex AI and exits immediately.
    """

    def __init__(self):
        self.storage_client = storage_client
        self.genai_client = None

        if ENVIRONMENT != 'local':
            try:
                self.genai_client = genai.Client(
                    vertexai=True,
                    project=PROJECT_ID,
                    location=VERTEX_AI_LOCATION
                )
                logger.info(f"Vertex AI client initialized for batch: model={VERTEX_AI_MODEL}")

            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI: {e}")

    def download_articles(self, gcs_path: str) -> List[Dict[str, Any]]:
        """Download articles from GCS."""
        try:
            bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(gcs_path)
            content = blob.download_as_text()
            data = json.loads(content)
            return data.get('articles', [])
        except Exception as e:
            logger.error(f"Error downloading {gcs_path}: {e}")
            return []

    def upload_batch_input(self, articles: List[Dict[str, Any]], run_folder: str, 
                            source_type: str, branch_type: str, batch_index: int) -> str:
        """
        Upload a batch of articles to GCS for fileData reference.
        
        Args:
            articles: List of articles for this batch
            run_folder: Run folder path
            source_type: Source type (complete, scraped, etc.)
            branch_type: Branch type (singleton or merged) to prevent path collisions
            batch_index: Index of this batch
            
        Returns:
            GCS URI of uploaded file
        """
        # Prepare input data - passthrough fields stored for recovery by jsonl_transformer (not sent to LLM)
        llm_input = {
            "articles": [
                {
                    "article_id": a.get('article_id', ''),
                    "title": a.get('title', ''),
                    "body": (a.get('body', '') or '')[:8000],
                    "url": a.get('original_url', a.get('url', '')),
                    "merged_from_urls": a.get('merged_from_urls', []),
                    "source": a.get('source', ''),
                    "publish_date": a.get('publish_date', ''),
                    # Keywords that matched this article - LLM should add these as tags
                    "keywords_used": a.get('keywords_used', a.get('keywords_matched', [])),
                    # Passthrough fields preserved in input file for recovery during transform
                    # (not included in LLM prompt/schema - restored after enrichment)
                    "language": a.get('language') or a.get('lang') or '',
                    "region": a.get('region') or '',
                    "source_type": a.get('source_type', 'api')  # Preserve original source_type
                }
                for a in articles
            ]
        }
        
        # Upload path: stage input folder (include branch_type to prevent collisions)
        blob_path = f"{run_folder}/batch_enrichment/{source_type}/{branch_type}/input/batch_{batch_index}.json"
        
        bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(llm_input, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        
        gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_path}"
        logger.info(f"Uploaded batch {batch_index} input to {gcs_uri} ({len(articles)} articles)")
        
        return gcs_uri

    def create_batch_request(self, articles: List[Dict[str, Any]],
                              run_folder: str, source_type: str, branch_type: str) -> List[Dict[str, Any]]:
        """
        Create batch request entries for all articles using fileData pattern.
        Uploads article batches to GCS and references them via fileData.

        Args:
            articles: List of articles to enrich
            run_folder: Run folder path for staging files
            source_type: Source type for organizing staged files
            branch_type: Branch type (singleton or merged) to prevent path collisions

        Returns:
            List of batch request entries (one per article batch)
        """
        batch_requests = []

        # Collect all unique keywords from articles for prompt formatting
        all_keywords = set()
        for article in articles:
            keywords = article.get('keywords_used', article.get('keywords_matched', []))
            if keywords:
                all_keywords.update(k.lower() for k in keywords if isinstance(k, str))

        # Format keywords as tag list for the prompt
        if all_keywords:
            formatted_keywords = "- " + ", ".join(f"`{kw}`" for kw in sorted(all_keywords))
        else:
            formatted_keywords = "- (none specified)"

        # Format the prompt with actual keywords
        formatted_prompt = ENRICHMENT_PROMPT.format(formatted_keywords=formatted_keywords)
        logger.info(f"Formatted prompt with keywords: {sorted(all_keywords)}")

        # Group articles into batches of 10 for efficient processing
        batch_size = 10

        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            batch_index = i // batch_size

            # Upload batch input to GCS
            batch_gcs_uri = self.upload_batch_input(batch, run_folder, source_type, branch_type, batch_index)

            # Create batch request entry with fileData reference (like result_merger_function)
            request_entry = {
                "request": {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": formatted_prompt},
                                {
                                    "fileData": {
                                        "fileUri": batch_gcs_uri,
                                        "mimeType": "text/plain"
                                    }
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "candidateCount": 1,
                        "temperature": 0.2,
                        "topP": 0.9,
                        "maxOutputTokens": 65535,
                        "responseMimeType": "application/json"
                    }
                }
            }

            # Add structured output schema if available (same pattern as result_merger_function)
            if SCHEMA_AVAILABLE:
                request_entry["request"]["generationConfig"]["responseSchema"] = VERTEX_AI_RESPONSE_SCHEMA

            batch_requests.append(request_entry)

        return batch_requests

    def upload_batch_request(self, requests: List[Dict], run_folder: str, source_type: str, branch_type: str) -> str:
        """
        Upload batch request JSONL to GCS.

        Args:
            requests: List of batch request entries
            run_folder: Run folder path
            source_type: Source type (complete, scraped_incomplete, etc.)
            branch_type: Branch type (singleton or merged) to prevent path collisions

        Returns:
            GCS URI of uploaded file
        """
        # Create JSONL content
        jsonl_content = '\n'.join(json.dumps(r, ensure_ascii=False) for r in requests)

        # Upload path (include branch_type to prevent collisions)
        blob_path = f"{run_folder}/batch_enrichment/{source_type}/{branch_type}/request.jsonl"

        bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(jsonl_content, content_type='application/x-ndjson')

        gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_path}"
        logger.info(f"Uploaded batch request to {gcs_uri}")

        return gcs_uri

    def submit_batch_job(self, request_uri: str, run_folder: str, source_type: str, branch_type: str) -> Tuple[str, str]:
        """
        Submit batch job to Vertex AI.

        Args:
            request_uri: GCS URI of batch request JSONL
            run_folder: Run folder path
            source_type: Source type for output path
            branch_type: Branch type (singleton or merged) to prevent path collisions

        Returns:
            Tuple of (job_name, output_uri)
        """
        # Output path - jsonl_transformer will be triggered here (include branch_type)
        output_uri = f"gs://{GCS_BUCKET_NAME}/{run_folder}/batch_enrichment/{source_type}/{branch_type}/"

        try:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            display_name = f"article-enricher-{source_type}-{branch_type}-{timestamp}"
            batch_config = CreateBatchJobConfig(dest=output_uri, display_name=display_name)

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

    def save_batch_metadata(self, run_folder: str, source_type: str, branch_type: str,
                           job_name: str, output_uri: str,
                           article_count: int) -> str:
        """Save batch job metadata for tracking."""
        metadata = {
            "job_name": job_name,
            "output_uri": output_uri,
            "source_type": source_type,
            "branch_type": branch_type,
            "article_count": article_count,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "status": "submitted"
        }

        blob_path = f"{run_folder}/batch_enrichment/{source_type}/{branch_type}/metadata.json"
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
            gcs_path: GCS path to input file

        Returns:
            Processing metadata
        """
        date_str, run_id, filename = extract_path_info(gcs_path)
        source_type = extract_source_type(filename)
        branch_type = extract_branch_type(filename)
        run_folder = f"ingestion/{date_str}/{run_id}"

        logger.info(f"Processing: date={date_str}, run={run_id}, source={source_type}, branch={branch_type}")

        # Download articles
        articles = self.download_articles(gcs_path)

        if not articles:
            logger.warning("No articles found")
            return {"status": "empty", "articles": 0}

        logger.info(f"Creating batch request for {len(articles)} articles")

        # Create batch request (uploads article batches to GCS with fileData pattern)
        batch_requests = self.create_batch_request(articles, run_folder, source_type, branch_type)
        logger.info(f"Created {len(batch_requests)} batch request entries (using fileData pattern)")

        # Upload batch request to GCS
        request_uri = self.upload_batch_request(batch_requests, run_folder, source_type, branch_type)

        # Submit batch job
        job_name, output_uri = self.submit_batch_job(request_uri, run_folder, source_type, branch_type)

        # Save metadata
        self.save_batch_metadata(run_folder, source_type, branch_type, job_name, output_uri, len(articles))

        return {
            "status": "batch_submitted",
            "date": date_str,
            "run_id": run_id,
            "source_type": source_type,
            "branch_type": branch_type,
            "input_file": gcs_path,
            "article_count": len(articles),
            "batch_requests": len(batch_requests),
            "job_name": job_name,
            "output_uri": output_uri
        }


def enrich_articles(event, context):
    """
    Cloud Function entry point.
    Triggered by GCS Eventarc on singleton_*.json or decision_*.json creation.
    """
    logger.info("=== ARTICLE ENRICHER FUNCTION TRIGGERED (BATCH MODE) ===")

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
        enricher = ArticleEnricher()

        if not enricher.genai_client and ENVIRONMENT != 'local':
            logger.error("Vertex AI client not available")
            return

        result = enricher.process(name)
        logger.info(f"Result: {result}")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

    logger.info("=== ARTICLE ENRICHER FUNCTION COMPLETED ===")


def main(request):
    """HTTP entry point for Cloud Run."""
    logger.info("=== ARTICLE ENRICHER HTTP TRIGGERED ===")

    try:
        data = request.get_json() if request.is_json else {}
        gcs_path = data.get('gcs_path', '')

        if not gcs_path:
            return {"error": "gcs_path required"}, 400

        enricher = ArticleEnricher()
        result = enricher.process(gcs_path)

        return result, 200

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"error": str(e)}, 500


if __name__ == "__main__":
    logger.info("Running in local mode")
    test_path = "ingestion/2025-01-15/12-00-00/singleton_complete_articles.json"
    logger.info(f"Test path: {test_path}")
