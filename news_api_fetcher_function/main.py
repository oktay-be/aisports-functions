"""
News API Fetcher Cloud Function

Fetches news from external APIs (NewsAPI, WorldNewsAPI, GNews) and stores them in GCS.
This function is triggered via Pub/Sub and can also be triggered from the frontend.
"""

import os
import sys
import json
import base64
import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# CET timezone for run timestamps
CET = ZoneInfo("Europe/Berlin")
from pathlib import Path

from google.cloud import pubsub_v1, storage, secretmanager

# Import the news aggregator
from news_aggregator import NewsAggregator, is_content_complete

# Enhanced logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

logger = logging.getLogger(__name__)
logger.info("Logging configuration initialized for news_api_fetcher_function")

# Initialize Google Cloud clients (only in cloud environment)
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIRONMENT != 'local':
    storage_client = storage.Client()
    secret_client = secretmanager.SecretManagerServiceClient()
    publisher = pubsub_v1.PublisherClient()
else:
    storage_client = None
    secret_client = None
    publisher = None
    logger.info("Running in local environment - skipping Google Cloud client initialization")

# Configuration from environment variables
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
# GCS path prefix for ingestion data (new structure: ingestion/api/YYYY-MM-DD/HH-MM-SS/)
INGESTION_PREFIX = os.getenv('INGESTION_PREFIX', 'ingestion/')
SESSION_DATA_CREATED_TOPIC = os.getenv('SESSION_DATA_CREATED_TOPIC', 'session-data-created')

# Default keywords (same as scraper config)
DEFAULT_KEYWORDS = ['fenerbahce', 'galatasaray', 'tedesco']


def access_secret(secret_id: str, version_id: str = "latest") -> str:
    """Access a secret from Google Cloud Secret Manager."""
    if ENVIRONMENT == 'local':
        # In local environment, use environment variables
        return os.getenv(secret_id, '').strip()

    try:
        name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
        response = secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Error accessing secret: {e}")
        return ''


def get_api_keys() -> dict:
    """Retrieve API keys from Secret Manager or environment variables."""
    return {
        'newsapi_key': access_secret('NEWSAPI_KEY'),
        'worldnewsapi_key': access_secret('WORLDNEWSAPI_KEY'),
        'gnews_api_key': access_secret('GNEWS_API_KEY'),
    }


def generate_article_id(url: str) -> str:
    """Generate a unique article ID from URL using MD5 hash (first 16 chars)."""
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:16]


def transform_api_article_to_session_schema(article: dict) -> dict:
    """
    Transform API article to match scraper session schema.

    This ensures API articles have the same schema as scraped articles
    so they can be processed by the same batch pipeline.
    """
    url = article.get('original_url') or article.get('url', '')

    # Extract domain from URL
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc

    # Generate article_id
    article_id = generate_article_id(url) if url else ""

    # Get language - check both 'language' (WorldNewsAPI) and 'lang' (GNews)
    language = article.get('language') or article.get('lang')
    
    # Map to region: tr -> tr, everything else -> eu
    region = 'tr' if language == 'tr' else 'eu'

    # Transform to session schema
    transformed = {
        "url": url,
        "scraped_at": article.get('fetched_at', datetime.now(timezone.utc).isoformat()),
        "keywords_used": article.get('keywords_matched', []),
        "title": article.get('title', ''),
        "body": article.get('content', ''),  # Rename content -> body
        "publish_date": article.get('publish_date', ''),
        "source": domain,
        "extraction_method": f"api:{article.get('api_source', 'unknown')}",
        "source_type": "api",  # Standardized source type for UI filtering
        "site": domain,
        "article_id": article_id,
        "language": language,
        "region": region
    }

    return transformed


def upload_to_gcs(bucket_name: str, blob_path: str, data: dict) -> str:
    """Upload JSON data to GCS and return the blob path."""
    if not storage_client:
        logger.warning("Storage client not available, skipping upload")
        return blob_path

    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(data, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        logger.info(f"Uploaded data to gs://{bucket_name}/{blob_path}")
        return blob_path
    except Exception as e:
        logger.error(f"Error uploading to GCS: {e}")
        raise


def get_existing_articles_for_date(bucket_name: str, date_str: str) -> set:
    """
    Fetch all article URLs from existing runs for a given date.

    Args:
        bucket_name: GCS bucket name
        date_str: Date in YYYY-MM-DD format

    Returns:
        Set of article URLs that already exist

    Raises:
        Exception: If GCS read fails (caller should abort)
    """
    if not storage_client:
        logger.warning("Storage client not available (local env), skipping deduplication")
        return set()

    existing_urls = set()
    # Path structure: ingestion/YYYY-MM-DD/
    prefix = f"{INGESTION_PREFIX}{date_str}/"

    try:
        bucket = storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)

        for blob in blobs:
            # Only process articles.json files
            if blob.name.endswith('/articles.json'):
                try:
                    content = blob.download_as_string()
                    data = json.loads(content)
                    articles = data.get('articles', [])

                    for article in articles:
                        url = article.get('original_url') or article.get('url')
                        if url:
                            existing_urls.add(url)

                    logger.info(f"Loaded {len(articles)} articles from {blob.name}")

                except json.JSONDecodeError as e:
                    logger.error(f"Cannot parse {blob.name}: {e}")
                    # Continue with other files
                except Exception as e:
                    logger.error(f"Error reading {blob.name}: {e}")
                    # Continue with other files

        logger.info(f"Found {len(existing_urls)} existing articles for {date_str}")
        return existing_urls

    except Exception as e:
        # CRITICAL: Cannot list blobs or access bucket
        logger.error(f"CRITICAL: GCS error while fetching existing articles: {e}")
        raise  # Re-raise to abort the run


def publish_batch_processing_request(
    session_files: list,
    run_id: str,
    triggered_by: str
) -> None:
    """
    Publish batch processing request to session-data-created topic.
    Follows the same pattern as scraper_function (publishes ONE batch message with all files).

    Args:
        session_files: List of file info dicts with gcs_path, articles_count, source_domain
        run_id: Run ID (timestamp)
        triggered_by: Who triggered this
    """
    if not publisher:
        logger.warning("Pub/Sub publisher not available (local env), skipping batch trigger")
        return

    # Build success_messages array (like scraper_function does)
    success_messages = []
    total_articles = 0

    for file_info in session_files:
        success_messages.append({
            'status': 'success',
            'gcs_path': file_info['gcs_path'],
            'source_domain': file_info.get('source_domain', 'api_complete'),
            'articles_count': file_info.get('articles_count', 0),
            'triggered_by': triggered_by,
            'processed_at': datetime.now(timezone.utc).isoformat()
        })
        total_articles += file_info.get('articles_count', 0)

    # Build batch message (following scraper_function pattern)
    batch_message = {
        "status": "batch_success",
        "run_id": run_id,
        "batch_size": len(success_messages),
        "success_messages": success_messages,
        "batch_processed_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": total_articles
    }

    try:
        topic_path = publisher.topic_path(PROJECT_ID, SESSION_DATA_CREATED_TOPIC)
        data = json.dumps(batch_message).encode("utf-8")
        future = publisher.publish(topic_path, data)
        message_id = future.result()

        logger.info(f"✓ Published batch message to {SESSION_DATA_CREATED_TOPIC} (message_id: {message_id})")
        logger.info(f"  - Files: {len(success_messages)}")
        logger.info(f"  - Total articles: {total_articles}")

    except Exception as e:
        logger.error(f"Error publishing batch message: {e}", exc_info=True)


async def trigger_scraper_for_incomplete_articles(
    incomplete_articles: list,
    base_path: str,
    keywords: list,
    triggered_by: str
) -> dict:
    """
    Trigger scraper function via Pub/Sub for incomplete articles.

    Args:
        incomplete_articles: List of articles needing scraping
        base_path: GCS path for this run
        keywords: Keywords used
        triggered_by: Who triggered this run

    Returns:
        Dict with triggered scraper info
    """
    if not publisher:
        logger.warning("Publisher not available, skipping scraper trigger")
        return {'triggered': False, 'reason': 'Publisher not available'}

    if not incomplete_articles:
        logger.info("No incomplete articles to scrape")
        return {'triggered': False, 'reason': 'No incomplete articles'}

    # Extract URLs
    urls = []
    for article in incomplete_articles:
        url = article.get('url') or article.get('original_url')
        if url:
            urls.append(url)

    if not urls:
        logger.warning("No valid URLs found for incomplete articles")
        return {'triggered': False, 'reason': 'No valid URLs'}

    # Prepare Pub/Sub message (simplified - no region distinction)
    # Scraper should save to: {base_path}/scraped/articles.json
    message_data = {
        "urls": urls,
        "keywords": keywords,
        "scrape_depth": 0,  # No link discovery, just scrape given URLs
        "persist": False,   # Memory-only mode
        "triggered_by": triggered_by,
        "api_run_path": base_path,  # Base path for this API run
        "scraped_output_path": f"{base_path}/scraped"  # Scraper output subfolder
    }

    try:
        # Publish to scraping-requests topic
        topic_path = publisher.topic_path(PROJECT_ID, 'scraping-requests')
        data = json.dumps(message_data).encode("utf-8")
        future = publisher.publish(topic_path, data)
        message_id = future.result()

        logger.info(f"Triggered scraper for {len(urls)} incomplete articles (message_id: {message_id})")

        return {
            'triggered': True,
            'message_id': message_id,
            'urls_count': len(urls),
            'articles_count': len(incomplete_articles)
        }

    except Exception as e:
        logger.error(f"Error triggering scraper: {e}", exc_info=True)
        return {
            'triggered': False,
            'error': str(e),
            'urls_count': len(urls),
            'articles_count': len(incomplete_articles)
        }


async def fetch_and_store_news(message_data: dict) -> dict:
    """
    Main processing function to fetch news from APIs and store in GCS.
    
    Args:
        message_data: Dict containing:
            - keywords: List of keywords to search for
            - triggered_by: Email of user who triggered (or 'scheduler')
            - time_range: Optional time range (default: 'last_24_hours')
            - max_results: Optional max results per API (default: 50)
    
    Returns:
        Dict with status and statistics
    """
    keywords = message_data.get('keywords', DEFAULT_KEYWORDS)
    triggered_by = message_data.get('triggered_by', 'scheduler')
    time_range = message_data.get('time_range', 'last_24_hours')
    max_results = message_data.get('max_results', 100)
    
    logger.info(f"Starting news API fetch - Keywords: {keywords}, Triggered by: {triggered_by}")
    
    # Get API keys
    api_keys = get_api_keys()
    
    if not any(api_keys.values()):
        logger.error("No API keys available")
        return {
            'status': 'error',
            'error': 'No API keys configured',
            'triggered_by': triggered_by
        }
    
    # Initialize aggregator
    aggregator = NewsAggregator(
        newsapi_key=api_keys['newsapi_key'],
        worldnewsapi_key=api_keys['worldnewsapi_key'],
        gnews_api_key=api_keys['gnews_api_key'],
        enable_cache=False  # No local cache in cloud function
    )
    
    # Configure aggregator
    aggregator.configure(
        languages=['tr', 'en'],
        max_results=max_results,
        time_range=time_range
    )
    
    # Fetch news
    try:
        articles = await aggregator.get_news(keywords=keywords)
        logger.info(f"Fetched {len(articles)} articles from APIs")
    except Exception as e:
        logger.error(f"Error fetching news: {e}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e),
            'triggered_by': triggered_by
        }
    
    if not articles:
        logger.info("No articles found from APIs")
        return {
            'status': 'success',
            'articles_count': 0,
            'triggered_by': triggered_by
        }
    
    # Generate storage path (using CET timezone for run timestamps)
    now = datetime.now(CET)
    date_str = now.strftime('%Y-%m-%d')
    run_id = now.strftime('%H-%M-%S')

    # Path structure: ingestion/YYYY-MM-DD/HH-MM-SS/
    base_path = f"{INGESTION_PREFIX}{date_str}/{run_id}"

    # Add source_type and dates to each article
    processed_articles = []
    for article in articles:
        article['source_type'] = 'api'
        article['fetched_at'] = date_str  # YYYY-MM-DD format for easy filtering
        article['keywords_matched'] = keywords
        processed_articles.append(article)

    # Fetch existing articles from same day (CRITICAL - will abort on error)
    try:
        existing_urls = get_existing_articles_for_date(GCS_BUCKET_NAME, date_str)
    except Exception as e:
        logger.error(f"CRITICAL: Cannot fetch existing articles for deduplication: {e}")
        return {
            'status': 'error',
            'error': f'Deduplication check failed: {str(e)}',
            'triggered_by': triggered_by
        }

    # Filter duplicates
    unique_articles = []
    duplicate_urls = []
    for article in processed_articles:
        url = article.get('original_url') or article.get('url')
        if url and url not in existing_urls:
            unique_articles.append(article)
            existing_urls.add(url)  # Track for this run too
        elif url:
            duplicate_urls.append(url)
            logger.debug(f"Duplicate URL: {url}")

    logger.info(f"Deduplication: {len(processed_articles)} fetched, {len(unique_articles)} unique, {len(duplicate_urls)} duplicates")

    if duplicate_urls:
        logger.info(f"Duplicate URLs:\n" + "\n".join(f"  - {url}" for url in duplicate_urls))

    # Skip upload if all duplicates
    if len(unique_articles) == 0:
        logger.info(f"All {len(processed_articles)} articles were duplicates. Skipping upload.")
        return {
            'status': 'success',
            'articles_count': 0,
            'duplicates_filtered': len(duplicate_urls),
            'message': 'All articles were duplicates from previous runs today',
            'triggered_by': triggered_by
        }

    processed_articles = unique_articles

    # Classify articles by completeness (no region distinction)
    complete_articles = []
    incomplete_articles = []

    for article in processed_articles:
        # Check completeness
        content = article.get('content', '')
        if is_content_complete(content):
            complete_articles.append(article)
        else:
            incomplete_articles.append(article)

    logger.info(f"Complete articles: {len(complete_articles)}")
    logger.info(f"Incomplete articles: {len(incomplete_articles)}")

    # Transform complete articles to session schema and group by source
    from collections import defaultdict
    articles_by_source = defaultdict(list)

    for article in complete_articles:
        transformed = transform_api_article_to_session_schema(article)
        source_domain = transformed['source']
        articles_by_source[source_domain].append(transformed)

    # Create session-like structure for complete articles
    session_data = {
        'source_domain': 'api_combined',
        'source_url': 'https://api-news-aggregator',
        'articles': [],
        'session_metadata': {
            'session_id': f"api_{run_id}",
            'fetched_at': now.isoformat(),
            'source_count': len(articles_by_source),
            'extraction_method': 'api_aggregation'
        }
    }

    # Add all transformed articles
    for source_domain, source_articles in articles_by_source.items():
        session_data['articles'].extend(source_articles)
        logger.info(f"  - {source_domain}: {len(source_articles)} complete articles")

    # Upload complete articles to complete_articles.json
    complete_articles_path = f"{base_path}/complete_articles.json"
    upload_to_gcs(GCS_BUCKET_NAME, complete_articles_path, session_data)

    # Decide next action based on incomplete articles
    if incomplete_articles:
        # Upload incomplete articles to to_scrape.json (name avoids triggering article_processor)
        incomplete_session_data = {
            'source_domain': 'api_incomplete',
            'source_url': 'https://api-news-aggregator',
            'articles': [transform_api_article_to_session_schema(a) for a in incomplete_articles],
            'session_metadata': {
                'session_id': f"api_incomplete_{run_id}",
                'fetched_at': now.isoformat(),
                'extraction_method': 'api_aggregation',
                'needs_scraping': True
            }
        }
        to_scrape_path = f"{base_path}/to_scrape.json"
        upload_to_gcs(GCS_BUCKET_NAME, to_scrape_path, incomplete_session_data)

        # Trigger scraper and exit (scraper will handle batch trigger)
        logger.info(f"Triggering scraper for {len(incomplete_articles)} incomplete articles")
        scraper_trigger_info = await trigger_scraper_for_incomplete_articles(
            incomplete_articles,
            base_path,
            keywords,
            triggered_by
        )

        # Upload metadata
        metadata = {
            'triggered_by': triggered_by,
            'keywords': keywords,
            'time_range': time_range,
            'max_results': max_results,
            'articles_count': len(processed_articles),
            'complete_articles_count': len(complete_articles),
            'incomplete_articles_count': len(incomplete_articles),
            'duplicates_filtered': len(duplicate_urls),
            'scraper_triggered': scraper_trigger_info,
            'api_sources_used': aggregator.get_available_sources(),
            'started_at': now.isoformat(),
            'completed_at': datetime.now(timezone.utc).isoformat()
        }
        metadata_path = f"{base_path}/metadata.json"
        upload_to_gcs(GCS_BUCKET_NAME, metadata_path, metadata)

        # Upload raw API responses
        raw_responses = aggregator.get_raw_responses()
        if raw_responses:
            for api_name, response_data in raw_responses.items():
                response_path = f"{base_path}/responses/{api_name}.json"
                upload_to_gcs(GCS_BUCKET_NAME, response_path, response_data)
                logger.info(f"Uploaded raw {api_name} response to {response_path}")

        logger.info("Scraper triggered. Exiting. Scraper will handle batch processing.")
        return {
            'status': 'success',
            'articles_count': len(processed_articles),
            'complete_articles_count': len(complete_articles),
            'incomplete_articles_count': len(incomplete_articles),
            'duplicates_filtered': len(duplicate_urls),
            'scraper_triggered': True,
            'triggered_by': triggered_by
        }
    else:
        # No incomplete articles - trigger batch processing immediately
        logger.info("No incomplete articles. Triggering batch processing immediately.")

        session_files = [{
            'gcs_path': f"gs://{GCS_BUCKET_NAME}/{complete_articles_path}",
            'source_domain': 'api_complete',
            'articles_count': len(complete_articles)
        }]

        publish_batch_processing_request(session_files, run_id, triggered_by)

        # Upload metadata
        metadata = {
            'triggered_by': triggered_by,
            'keywords': keywords,
            'time_range': time_range,
            'max_results': max_results,
            'articles_count': len(processed_articles),
            'complete_articles_count': len(complete_articles),
            'incomplete_articles_count': 0,
            'duplicates_filtered': len(duplicate_urls),
            'scraper_triggered': {'triggered': False, 'reason': 'No incomplete articles'},
            'api_sources_used': aggregator.get_available_sources(),
            'started_at': now.isoformat(),
            'completed_at': datetime.now(timezone.utc).isoformat()
        }
        metadata_path = f"{base_path}/metadata.json"
        upload_to_gcs(GCS_BUCKET_NAME, metadata_path, metadata)

        # Upload raw API responses
        raw_responses = aggregator.get_raw_responses()
        if raw_responses:
            for api_name, response_data in raw_responses.items():
                response_path = f"{base_path}/responses/{api_name}.json"
                upload_to_gcs(GCS_BUCKET_NAME, response_path, response_data)
                logger.info(f"Uploaded raw {api_name} response to {response_path}")

        logger.info(f"Successfully processed {len(processed_articles)} articles:")
        logger.info(f"  - Complete: {len(complete_articles)} (stored)")
        logger.info(f"  - Incomplete: 0")
        logger.info(f"  - Duplicates filtered: {len(duplicate_urls)}")
        logger.info("Batch processing triggered.")

        return {
            'status': 'success',
            'articles_count': len(processed_articles),
            'complete_articles_count': len(complete_articles),
            'incomplete_articles_count': 0,
            'duplicates_filtered': len(duplicate_urls),
            'batch_triggered': True,
            'storage_path': base_path,
            'triggered_by': triggered_by
        }


def news_api_fetch(event, context):
    """
    Background Cloud Function to be triggered by Pub/Sub.
    
    Args:
        event (dict): The Pub/Sub message data.
        context (google.cloud.functions.Context): The Cloud Functions event metadata.
    """
    logger.info(f"Function triggered by context: {context}")
    
    message_data = {}
    
    if isinstance(event, dict) and "data" in event:
        try:
            message_data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
            logger.info(f"Received message data: {message_data}")
        except Exception as e:
            logger.error(f"Error decoding Pub/Sub message: {e}")
            message_data = {}
    
    # Run the async function
    try:
        result = asyncio.run(fetch_and_store_news(message_data))
        logger.info(f"Function completed with result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in news_api_fetch: {e}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }


# Local testing
async def main_local():
    """Main function for local execution."""
    test_data = {
        'keywords': DEFAULT_KEYWORDS,
        'triggered_by': 'local_test',
        'time_range': 'last_24_hours',
        'max_results': 10
    }
    result = await fetch_and_store_news(test_data)
    print(f"Result: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    if ENVIRONMENT == 'local':
        asyncio.run(main_local())
