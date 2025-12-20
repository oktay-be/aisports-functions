"""
Merge Decider Function - LLM Decision on Article Groups

Stage 3 of the article processing pipeline.
Takes grouped articles and decides: MERGE (same event) or KEEP_BOTH (different angles).

Flow:
1. Triggered by GCS file creation (grouped_*.json)
2. For each group, send to LLM for merge decision
3. Output decision_*.json with merge decisions applied
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
from google.genai.types import HttpOptions, GenerateContentConfig

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

logger = logging.getLogger(__name__)
logger.info("Merge Decider Function initialized")

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

# Merge decision prompt
MERGE_DECISION_PROMPT = """You are a sports news editor deciding whether similar articles should be merged or kept separate.

## Task
Analyze the following group of similar articles and decide:
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

## Input Format
```json
{
  "group_id": 1,
  "max_similarity": 0.85,
  "articles": [
    {"article_id": "...", "title": "...", "body": "...", "source": "..."},
    {"article_id": "...", "title": "...", "body": "...", "source": "..."}
  ]
}
```

## Output Format
Return ONLY valid JSON:
```json
{
  "decision": "MERGE" or "KEEP_BOTH",
  "reason": "Brief explanation",
  "primary_article_id": "ID of best article if MERGE, null if KEEP_BOTH",
  "merged_article_ids": ["IDs of merged articles"] or []
}
```

## Article Group to Analyze
"""


def extract_path_info(gcs_path: str) -> Tuple[str, str, str]:
    """Extract date, run_id, and filename from GCS path."""
    pattern = r'(\d{4}-\d{2}-\d{2})/(\d{2}-\d{2}-\d{2})/([^/]+\.json)$'
    match = re.search(pattern, gcs_path)

    if match:
        return match.group(1), match.group(2), match.group(3)

    # Fallback to current time (CET for run timestamps)
    now = datetime.now(CET)
    return now.strftime('%Y-%m-%d'), now.strftime('%H-%M-%S'), 'unknown.json'


def extract_source_type(filename: str) -> str:
    """Extract source type from filename."""
    if 'complete' in filename:
        return 'complete'
    elif 'scraped_incomplete' in filename:
        return 'scraped_incomplete'
    elif 'scraped' in filename:
        return 'scraped'
    return 'unknown'


class MergeDecider:
    """
    LLM-based merge decision maker for article groups.
    """

    def __init__(self):
        self.storage_client = storage_client
        self.genai_client = None

        if ENVIRONMENT != 'local':
            try:
                # Determine location based on model
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
                logger.info(f"Vertex AI client initialized: model={VERTEX_AI_MODEL}")

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

    def decide_merge(self, group: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make merge decision for a single group using LLM.

        Args:
            group: Group data with articles

        Returns:
            Decision result
        """
        group_id = group.get('group_id', 0)
        articles = group.get('articles', [])

        if len(articles) < 2:
            # Single article - no merge needed
            return {
                "decision": "KEEP_BOTH",
                "reason": "Single article in group",
                "primary_article_id": None,
                "merged_article_ids": []
            }

        # Prepare input for LLM
        llm_input = {
            "group_id": group_id,
            "max_similarity": group.get('max_similarity', 0),
            "articles": [
                {
                    "article_id": a.get('article_id', ''),
                    "title": a.get('title', ''),
                    "body": (a.get('body', '') or '')[:1000],  # Truncate for LLM
                    "source": a.get('source', '')
                }
                for a in articles
            ]
        }

        prompt = MERGE_DECISION_PROMPT + f"\n```json\n{json.dumps(llm_input, ensure_ascii=False, indent=2)}\n```"

        try:
            response = self.genai_client.models.generate_content(
                model=VERTEX_AI_MODEL,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=1024,
                    response_mime_type="application/json"
                )
            )

            # Parse response
            response_text = response.text.strip()
            decision = json.loads(response_text)

            logger.info(f"Group {group_id}: {decision.get('decision')} - {decision.get('reason', '')[:50]}")
            return decision

        except Exception as e:
            logger.error(f"LLM error for group {group_id}: {e}")
            # Default to KEEP_BOTH on error
            return {
                "decision": "KEEP_BOTH",
                "reason": f"LLM error: {str(e)[:100]}",
                "primary_article_id": None,
                "merged_article_ids": []
            }

    def apply_decisions(
        self,
        groups: List[Dict[str, Any]],
        decisions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Apply merge decisions to produce output articles.

        Args:
            groups: Original groups with articles
            decisions: LLM decisions for each group

        Returns:
            List of articles with merge decisions applied
        """
        output_articles = []

        for group, decision in zip(groups, decisions):
            articles = group.get('articles', [])
            group_id = group.get('group_id', 0)

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
                    # Fallback to first article
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
                        'group_id': group_id,
                        'group_size': len(articles)
                    }
                    output_articles.append(article_copy)

        return output_articles

    def save_json_to_gcs(self, data: Any, blob_path: str) -> str:
        """Save JSON data to GCS."""
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

        logger.info(f"Processing {len(groups)} groups")

        # Make decisions for each group
        decisions = []
        merge_count = 0
        keep_count = 0

        for group in groups:
            decision = self.decide_merge(group)
            decisions.append(decision)

            if decision.get('decision') == 'MERGE':
                merge_count += 1
            else:
                keep_count += 1

        # Apply decisions
        output_articles = self.apply_decisions(groups, decisions)

        # Save output
        output_path = f"{run_folder}/decision_{source_type}_articles.json"
        self.save_json_to_gcs({
            'articles': output_articles,
            'count': len(output_articles),
            'source_type': source_type,
            'decisions_summary': {
                'total_groups': len(groups),
                'merged': merge_count,
                'kept_separate': keep_count
            },
            'created_at': datetime.now(timezone.utc).isoformat()
        }, output_path)

        # Save detailed decision log
        decision_log_path = f"{run_folder}/decision_log_{source_type}.json"
        self.save_json_to_gcs({
            'decisions': [
                {
                    'group_id': g.get('group_id'),
                    'article_count': len(g.get('articles', [])),
                    'decision': d
                }
                for g, d in zip(groups, decisions)
            ],
            'created_at': datetime.now(timezone.utc).isoformat()
        }, decision_log_path)

        metadata = {
            "status": "success",
            "source_type": source_type,
            "date": date_str,
            "run_id": run_id,
            "input_file": gcs_path,
            "groups_processed": len(groups),
            "merge_decisions": merge_count,
            "keep_separate_decisions": keep_count,
            "output_articles": len(output_articles),
            "output_file": output_path,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"Complete: {merge_count} merged, {keep_count} kept separate, {len(output_articles)} output articles")

        return metadata


def process_groups(event, context):
    """
    Cloud Function entry point.

    Triggered by GCS Eventarc on grouped_*.json creation.
    """
    logger.info("=== MERGE DECIDER FUNCTION TRIGGERED ===")

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
        logger.info(f"Result: {result.get('status')}")

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
    test_path = "2025-01-15/12-00-00/grouped_complete_articles.json"
    logger.info(f"Test path: {test_path}")
