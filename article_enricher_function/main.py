"""
Article Enricher Function - LLM Enrichment for Articles

Final stage of the article processing pipeline.
Generates summaries, X posts, translations, categories, and entities.

Flow:
1. Triggered by GCS file creation (singleton_*.json, decision_*.json)
2. For each article, generate enrichment using LLM
3. Output enriched_*.json files (consumed by UI)
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
logger.info("Article Enricher Function initialized")

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
BATCH_SIZE = int(os.getenv('ENRICHMENT_BATCH_SIZE', '5'))

# File patterns that trigger this function
TRIGGER_PATTERNS = [
    'singleton_complete_articles.json',
    'singleton_scraped_incomplete_articles.json',
    'singleton_scraped_articles.json',
    'decision_complete_articles.json',
    'decision_scraped_incomplete_articles.json',
    'decision_scraped_articles.json',
]

# Enrichment prompt
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

## Category Taxonomy (STRICT)

**Sport Tags (for non-football):**
- `basketball`, `volleyball`, `other-sports`

**Football Tags:**
- Transfers: `transfers-confirmed`, `transfers-rumors`, `transfers-negotiations`, `transfers-interest`
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

## x_post Rules (CRITICAL)
- ALWAYS in Turkish
- Max 280 characters
- Must contain ACTUAL information (names, scores, facts)
- Include 1-2 relevant hashtags
- NO CLICKBAIT: No "Iste detaylar...", "Bomba iddia!" without content

**BAD:** "Fenerbahce'den flas transfer hamlesi! Iste detaylar... #Fenerbahce"
**GOOD:** "Fenerbahce, Juventus'tan Dusan Vlahovic'i 45M Euro'ya kadrosuna katti. Sirbistanli golcu 4 yillik sozlesme imzaladi. #Fenerbahce #Transfer"

## Input Format
```json
{
  "articles": [
    {
      "article_id": "abc123",
      "title": "Article title",
      "body": "Article body text...",
      "url": "https://...",
      "source": "example.com",
      "published_at": "2025-01-15T12:00:00Z"
    }
  ]
}
```

## Output Format
Return JSON array with enriched articles:
```json
{
  "enriched_articles": [
    {
      "article_id": "abc123",
      "summary": "Comprehensive summary in ORIGINAL language...",
      "x_post": "Turkish tweet with facts and #hashtags",
      "summary_translation": "Turkish translation if non-Turkish, else null",
      "categories": [
        {"tag": "match-results", "confidence": 0.95, "evidence": "Reports final score"}
      ],
      "key_entities": {
        "teams": ["Galatasaray"],
        "players": ["Osimhen"],
        "amounts": [],
        "dates": ["2025-01-15"],
        "competitions": ["Super Lig"],
        "locations": ["Istanbul"]
      },
      "confidence": 0.9,
      "content_quality": "high",
      "language": "turkish"
    }
  ]
}
```

## Articles to Enrich
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


def extract_output_prefix(filename: str) -> str:
    """
    Extract output prefix from input filename.

    singleton_complete_articles.json -> enriched_singleton_complete_articles.json
    decision_complete_articles.json -> enriched_decision_complete_articles.json
    """
    # Remove .json extension and add enriched_ prefix
    base = filename.replace('.json', '')
    return f"enriched_{base}"


class ArticleEnricher:
    """
    LLM-based article enrichment service.
    """

    def __init__(self):
        self.storage_client = storage_client
        self.genai_client = None

        if ENVIRONMENT != 'local':
            try:
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

    def enrich_batch(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich a batch of articles using LLM.

        Args:
            articles: List of articles to enrich

        Returns:
            List of enriched articles
        """
        if not articles:
            return []

        # Prepare input - truncate body for LLM
        llm_input = {
            "articles": [
                {
                    "article_id": a.get('article_id', ''),
                    "title": a.get('title', ''),
                    "body": (a.get('body', '') or '')[:3000],  # Truncate
                    "url": a.get('url', ''),
                    "source": a.get('source', ''),
                    "published_at": a.get('published_at', '')
                }
                for a in articles
            ]
        }

        prompt = ENRICHMENT_PROMPT + f"\n```json\n{json.dumps(llm_input, ensure_ascii=False, indent=2)}\n```"

        try:
            response = self.genai_client.models.generate_content(
                model=VERTEX_AI_MODEL,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=8192,
                    response_mime_type="application/json"
                )
            )

            response_text = response.text.strip()
            result = json.loads(response_text)
            enriched = result.get('enriched_articles', [])

            logger.info(f"Enriched {len(enriched)} articles")
            return enriched

        except Exception as e:
            logger.error(f"LLM enrichment error: {e}")
            # Return empty enrichment on error
            return []

    def merge_enrichment(
        self,
        original: Dict[str, Any],
        enriched: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge enrichment data into original article.

        Preserves original fields and adds enrichment.
        """
        result = original.copy()

        # Add enrichment fields
        result['summary'] = enriched.get('summary', '')
        result['x_post'] = enriched.get('x_post', '')
        result['summary_translation'] = enriched.get('summary_translation')
        result['categories'] = enriched.get('categories', [])
        result['key_entities'] = enriched.get('key_entities', {
            'teams': [],
            'players': [],
            'amounts': [],
            'dates': [],
            'competitions': [],
            'locations': []
        })
        result['confidence'] = enriched.get('confidence', 0.5)
        result['content_quality'] = enriched.get('content_quality', 'medium')
        result['language'] = enriched.get('language', 'turkish')
        result['enriched_at'] = datetime.now(timezone.utc).isoformat()

        return result

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
            gcs_path: GCS path to input file

        Returns:
            Processing metadata
        """
        date_str, run_id, filename = extract_path_info(gcs_path)
        output_prefix = extract_output_prefix(filename)
        run_folder = f"ingestion/{date_str}/{run_id}"

        logger.info(f"Processing: date={date_str}, run={run_id}, file={filename}")

        # Download articles
        articles = self.download_articles(gcs_path)

        if not articles:
            logger.warning("No articles found")
            return {"status": "empty", "articles": 0}

        logger.info(f"Enriching {len(articles)} articles")

        # Create article lookup by ID
        article_map = {a.get('article_id', ''): a for a in articles}

        # Process in batches
        all_enriched = []

        for i in range(0, len(articles), BATCH_SIZE):
            batch = articles[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE

            logger.info(f"Processing batch {batch_num}/{total_batches}")

            enriched_batch = self.enrich_batch(batch)

            # Merge enrichment with original articles
            for enriched in enriched_batch:
                article_id = enriched.get('article_id', '')
                original = article_map.get(article_id)

                if original:
                    merged = self.merge_enrichment(original, enriched)
                    all_enriched.append(merged)
                else:
                    logger.warning(f"No matching article for ID: {article_id}")

        # Handle articles that weren't enriched (LLM errors)
        enriched_ids = {a.get('article_id') for a in all_enriched}
        for article in articles:
            if article.get('article_id') not in enriched_ids:
                # Add with minimal enrichment
                article['summary'] = article.get('title', '')
                article['x_post'] = ''
                article['summary_translation'] = None
                article['categories'] = []
                article['key_entities'] = {
                    'teams': [], 'players': [], 'amounts': [],
                    'dates': [], 'competitions': [], 'locations': []
                }
                article['confidence'] = 0.3
                article['content_quality'] = 'low'
                article['language'] = 'unknown'
                article['enrichment_error'] = True
                article['enriched_at'] = datetime.now(timezone.utc).isoformat()
                all_enriched.append(article)

        # Save output
        output_path = f"{run_folder}/{output_prefix}.json"
        self.save_json_to_gcs({
            'articles': all_enriched,
            'count': len(all_enriched),
            'source_file': gcs_path,
            'created_at': datetime.now(timezone.utc).isoformat()
        }, output_path)

        metadata = {
            "status": "success",
            "date": date_str,
            "run_id": run_id,
            "input_file": gcs_path,
            "input_articles": len(articles),
            "enriched_articles": len(all_enriched),
            "output_file": output_path,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"Complete: {len(all_enriched)} articles enriched")

        return metadata


def enrich_articles(event, context):
    """
    Cloud Function entry point.

    Triggered by GCS Eventarc on singleton_*.json or decision_*.json creation.
    """
    logger.info("=== ARTICLE ENRICHER FUNCTION TRIGGERED ===")

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
        logger.info(f"Result: {result.get('status')}")

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
    test_path = "2025-01-15/12-00-00/singleton_complete_articles.json"
    logger.info(f"Test path: {test_path}")
