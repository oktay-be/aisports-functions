"""
Article API Cloud Function

Serves processed articles from GCS with API key authentication.
Reads from: ingestion/{YYYY-MM-DD}/*/enriched_*_articles.json
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import functions_framework
from flask import Request, jsonify

from google.cloud import storage, secretmanager

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

# Environment Configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
API_KEY_SECRET_ID = os.getenv('API_KEY_SECRET_ID', 'ARTICLE_API_KEY')

# Initialize Clients
if ENVIRONMENT != 'local':
    storage_client = storage.Client()
    secret_client = secretmanager.SecretManagerServiceClient()
else:
    storage_client = None
    secret_client = None

# In-memory cache with 10-minute TTL
CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 10 * 60  # 10 minutes


def access_secret(secret_id: str, version_id: str = "latest") -> str:
    """Access a secret from Google Cloud Secret Manager."""
    if ENVIRONMENT == 'local':
        return os.getenv(secret_id, '').strip()

    try:
        name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
        response = secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Error accessing secret {secret_id}: {e}")
        return ''


def validate_api_key(request: Request) -> bool:
    """Validate the API key from request headers."""
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return False

    expected_key = access_secret(API_KEY_SECRET_ID)
    if not expected_key:
        logger.error("Could not retrieve API key from Secret Manager")
        return False

    return api_key == expected_key


def get_cache_key(region: str, date: str) -> str:
    """Generate cache key for region and date."""
    return f"{region}_{date}"


def get_cached_articles(region: str, date: str) -> Optional[List[Dict[str, Any]]]:
    """Get cached articles if still valid."""
    cache_key = get_cache_key(region, date)
    entry = CACHE.get(cache_key)

    if not entry:
        return None

    # Check TTL
    if datetime.now().timestamp() - entry['timestamp'] >= CACHE_TTL_SECONDS:
        del CACHE[cache_key]
        return None

    return entry['articles']


def set_cached_articles(region: str, date: str, articles: List[Dict[str, Any]]) -> None:
    """Cache articles with timestamp."""
    cache_key = get_cache_key(region, date)
    CACHE[cache_key] = {
        'articles': articles,
        'timestamp': datetime.now().timestamp()
    }


def get_date_range(start_date: str, end_date: str) -> List[str]:
    """Generate list of dates between start and end (inclusive)."""
    dates = []
    current = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    return dates


def get_today_date() -> str:
    """Get today's date in YYYY-MM-DD format."""
    return datetime.now().strftime('%Y-%m-%d')


def normalize_article(article: Dict[str, Any], content_map: Dict[str, str] = None) -> Dict[str, Any]:
    """Normalize article to consistent schema."""
    article_id = article.get('article_id')
    
    # Get content from content_map if available
    content = article.get('body') or article.get('content') or ''
    if content_map and article_id and article_id in content_map:
        content = content_map[article_id]
    
    return {
        'article_id': article_id,
        'original_url': article.get('original_url'),
        'merged_from_urls': article.get('merged_from_urls'),
        'title': article.get('title'),
        'summary': article.get('summary'),
        'content': content,  # Full article body
        'source': article.get('source'),
        'published_date': article.get('published_date'),
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
        'language': article.get('language'),
        'region': article.get('region'),
        'summary_translation': article.get('summary_translation'),
        'x_post': article.get('x_post'),
        '_grouping_metadata': article.get('_grouping_metadata'),
        '_merge_metadata': article.get('_merge_metadata'),
        '_processing_metadata': article.get('_processing_metadata'),
        'source_type': article.get('source_type', 'scraped')  # Use stored value, default to 'scraped'
    }


def load_content_map(date: str) -> Dict[str, str]:
    """
    Load article content (body) from batch input files.
    These are the most reliable source as they contain the exact
    articles sent to the LLM for enrichment.
    
    Folder patterns:
    - batch_enrichment/{source_type}/merged/input/*.json
    - batch_enrichment/{source_type}/singleton/input/*.json
    
    Returns a map of article_id -> body content.
    """
    content_map = {}
    
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        
        # Search all run folders for the date
        date_prefix = f"ingestion/{date}/"
        date_blobs = list(bucket.list_blobs(prefix=date_prefix, delimiter='/'))
        
        # Find all batch_enrichment input folders across all runs
        all_blobs = list(bucket.list_blobs(prefix=date_prefix))
        
        # Filter for batch input JSON files
        input_files = [
            b for b in all_blobs
            if '/batch_enrichment/' in b.name
            and '/input/' in b.name
            and b.name.endswith('.json')
        ]
        
        for blob in input_files:
            try:
                data = json.loads(blob.download_as_text())
                articles = data.get('articles', [])
                
                for article in articles:
                    article_id = article.get('article_id')
                    body = article.get('body') or article.get('content') or ''
                    if article_id and body:
                        content_map[article_id] = body
                
                logger.info(f"  Content from {blob.name}: {len(articles)} articles")
                
            except Exception as e:
                logger.error(f"  Error loading content from {blob.name}: {e}")
                
    except Exception as e:
        logger.error(f"Error loading content map for {date}: {e}")
    
    logger.info(f"Loaded content for {len(content_map)} articles from batch inputs")
    return content_map


def fetch_articles_for_date(date: str) -> List[Dict[str, Any]]:
    """Fetch enriched articles from GCS for a specific date."""
    articles = []
    prefix = f"ingestion/{date}/"

    logger.info(f"Fetching enriched articles for {date}: {prefix}")

    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix=prefix))

        # First, load content map from singleton/decision files
        content_map = load_content_map(date)

        # Filter for enriched article files
        enriched_files = [
            b for b in blobs
            if 'enriched_' in b.name and b.name.endswith('_articles.json')
        ]

        logger.info(f"Found {len(enriched_files)} enriched files (from {len(blobs)} total)")

        for blob in enriched_files:
            try:
                content = blob.download_as_text()
                data = json.loads(content)

                # Handle both direct array and wrapped formats
                article_list = []
                if isinstance(data, list):
                    article_list = data
                elif isinstance(data, dict):
                    if 'processed_articles' in data:
                        article_list = data['processed_articles']
                    elif 'articles' in data:
                        article_list = data['articles']

                for article in article_list:
                    articles.append(normalize_article(article, content_map))

                logger.info(f"  {blob.name}: {len(article_list)} articles")

            except Exception as e:
                logger.error(f"  Error processing {blob.name}: {e}")

            except Exception as e:
                logger.error(f"  Error processing {blob.name}: {e}")

    except Exception as e:
        logger.error(f"Error fetching files for {date}: {e}")

    return articles


def filter_by_search(articles: List[Dict[str, Any]], search: str) -> List[Dict[str, Any]]:
    """Filter articles by search term in title or summary."""
    if not search:
        return articles

    search_lower = search.lower()
    return [
        a for a in articles
        if search_lower in (a.get('title', '') or '').lower()
        or search_lower in (a.get('summary', '') or '').lower()
        or search_lower in (a.get('source', '') or '').lower()
    ]


def deduplicate_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate articles by URL."""
    seen_urls = set()
    unique = []

    for article in articles:
        url = article.get('original_url') or article.get('article_id')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(article)

    return unique


def cors_preflight_response():
    """Return CORS preflight response."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-API-Key',
        'Access-Control-Max-Age': '3600'
    }
    return ('', 204, headers)


def cors_headers() -> Dict[str, str]:
    """Return CORS headers for responses."""
    return {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
    }


@functions_framework.http
def main(request: Request):
    """HTTP Cloud Function entry point for serving articles."""

    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return cors_preflight_response()

    # Validate API key
    if not validate_api_key(request):
        return (
            json.dumps({'error': 'Invalid or missing API key'}),
            401,
            cors_headers()
        )

    # Parse query parameters
    region = request.args.get('region', 'all')
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    last_n_days = request.args.get('last_n_days', type=int)
    search = request.args.get('search', '')
    no_cache = request.args.get('no_cache', 'false').lower() == 'true'

    # Determine dates to fetch
    if start_date and end_date:
        dates_to_fetch = get_date_range(start_date, end_date)
    elif last_n_days and last_n_days > 0:
        end = datetime.now()
        start = end - timedelta(days=last_n_days - 1)
        dates_to_fetch = get_date_range(
            start.strftime('%Y-%m-%d'),
            end.strftime('%Y-%m-%d')
        )
    else:
        # Default: today only
        dates_to_fetch = [get_today_date()]

    logger.info(f"Requested dates: {', '.join(dates_to_fetch)}")

    all_articles = []

    for date in dates_to_fetch:
        # Check cache first
        cached = get_cached_articles(region, date)
        if cached is not None and not no_cache:
            logger.info(f"Cache HIT for {date} ({len(cached)} articles)")
            all_articles.extend(cached)
        else:
            if no_cache:
                logger.info(f"Cache BYPASS for {date}")
            else:
                logger.info(f"Cache MISS for {date} - fetching from GCS")
            
            date_articles = fetch_articles_for_date(date)

            # Cache the results
            set_cached_articles(region, date, date_articles)
            logger.info(f"Cached {len(date_articles)} articles for {date}")

            all_articles.extend(date_articles)

    logger.info(f"Total articles: {len(all_articles)}")

    # Deduplicate by URL
    unique_articles = deduplicate_articles(all_articles)
    logger.info(f"After dedup: {len(unique_articles)} unique articles")

    # Filter by region
    if region and region != 'all':
        unique_articles = [a for a in unique_articles if a.get('region') == region]
        logger.info(f"After region filter ({region}): {len(unique_articles)} articles")

    # Apply search filter
    if search:
        unique_articles = filter_by_search(unique_articles, search)
        logger.info(f"After search filter: {len(unique_articles)} articles")

    if not unique_articles:
        return (
            json.dumps({'error': f'No data found for region: {region}'}),
            404,
            cors_headers()
        )

    return (
        json.dumps(unique_articles, ensure_ascii=False),
        200,
        cors_headers()
    )


# Local testing
if __name__ == "__main__":
    ENVIRONMENT = 'local'

    # Mock request for testing
    class MockRequest:
        method = 'GET'
        args = {'region': 'tr', 'startDate': '2025-12-20', 'endDate': '2025-12-20'}
        headers = {'X-API-Key': 'test-key'}

    # Set up local credentials
    os.environ['ARTICLE_API_KEY'] = 'test-key'

    result = main(MockRequest())
    print(result)
