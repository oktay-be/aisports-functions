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
from pathlib import Path

from google.cloud import pubsub_v1, storage, secretmanager

# Import the news aggregator
from news_aggregator import NewsAggregator, is_content_complete, classify_region

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
NEWS_DATA_ROOT_PREFIX = os.getenv('NEWS_DATA_ROOT_PREFIX', 'news_data/')
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

    # Transform to session schema
    transformed = {
        "url": url,
        "scraped_at": article.get('fetched_at', datetime.now(timezone.utc).isoformat()),
        "keywords_used": article.get('keywords_matched', []),
        "title": article.get('title', ''),
        "body": article.get('content', ''),  # Rename content -> body
        "published_at": article.get('published_date', ''),
        "source": domain,
        "extraction_method": f"api:{article.get('api_source', 'unknown')}",
        "site": domain,
        "article_id": article_id
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


def get_existing_articles_for_date(bucket_name: str, date_str: str, year_month: str) -> set:
    """
    Fetch all article URLs from existing runs for a given date.

    Args:
        bucket_name: GCS bucket name
        date_str: Date in YYYY-MM-DD format
        year_month: Year-month in YYYY-MM format

    Returns:
        Set of article URLs that already exist

    Raises:
        Exception: If GCS read fails (caller should abort)
    """
    if not storage_client:
        logger.warning("Storage client not available (local env), skipping deduplication")
        return set()

    existing_urls = set()
    prefix = f"{NEWS_DATA_ROOT_PREFIX}api/{year_month}/{date_str}/"

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


async def wait_for_scraped_files(
    base_path: str,
    regions_triggered: dict,
    timeout_seconds: int = 300
) -> list:
    """
    Wait for scraper to complete and return file paths.
    Polls GCS for articles_scraped_{region}.json files.

    Args:
        base_path: Base GCS path for the run
        regions_triggered: Dict with region info (e.g., {'tr': {...}, 'eu': {...}})
        timeout_seconds: Maximum time to wait (default 5 minutes)

    Returns:
        List of file info dicts with file_path, articles_count, extraction_method
    """
    import asyncio
    import time

    if not storage_client:
        logger.warning("Storage client not available (local env), skipping scraper wait")
        return []

    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    expected_files = []

    # Build list of expected files
    for region in regions_triggered.keys():
        if 'error' not in regions_triggered[region]:
            expected_files.append(f"{base_path}/articles_scraped_{region}.json")

    if not expected_files:
        logger.info("No scraped files expected (no regions triggered successfully)")
        return []

    logger.info(f"Waiting for {len(expected_files)} scraped files: {expected_files}")

    start_time = time.time()
    found_files = []

    while time.time() - start_time < timeout_seconds:
        # Check which files exist
        for file_path in expected_files:
            if file_path in [f['file_path'] for f in found_files]:
                continue  # Already found

            blob = bucket.blob(file_path)
            if blob.exists():
                # Download and count articles
                try:
                    content = blob.download_as_string()
                    data = json.loads(content)
                    articles_count = len(data.get('articles', []))

                    found_files.append({
                        'file_path': file_path,
                        'articles_count': articles_count,
                        'extraction_method': 'journalist'
                    })
                    logger.info(f"Found scraped file: {file_path} ({articles_count} articles)")
                except Exception as e:
                    logger.error(f"Error reading {file_path}: {e}")

        # Check if all expected files found
        if len(found_files) == len(expected_files):
            elapsed = time.time() - start_time
            logger.info(f"All {len(expected_files)} scraped files ready after {elapsed:.1f}s")
            return found_files

        # Wait before next check
        await asyncio.sleep(5)

    # Timeout reached
    elapsed = time.time() - start_time
    logger.warning(f"Timeout waiting for scraped files after {elapsed:.1f}s. Found {len(found_files)}/{len(expected_files)}")
    return found_files


def publish_batch_processing_request(
    session_files: list,
    base_path: str,
    run_id: str,
    triggered_by: str
) -> None:
    """
    Publish batch processing request to session-data-created topic.
    Follows the same pattern as scraper_function (publishes ONE batch message with all files).

    Args:
        session_files: List of file info dicts with file_path, articles_count, extraction_method
        base_path: Base GCS path for the run
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
            'session_file': file_info['file_path'],
            'articles_count': file_info['articles_count'],
            'extraction_method': file_info['extraction_method']
        })
        total_articles += file_info['articles_count']

    # Build batch message (following scraper_function pattern)
    batch_message = {
        "status": "batch_success",
        "run_id": run_id,
        "batch_size": len(success_messages),
        "success_messages": success_messages,
        "batch_processed_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": total_articles,
        "triggered_by": triggered_by,
        "source_type": "api_integration"
    }

    try:
        topic_path = publisher.topic_path(PROJECT_ID, SESSION_DATA_CREATED_TOPIC)
        data = json.dumps(batch_message).encode("utf-8")
        future = publisher.publish(topic_path, data)
        message_id = future.result()

        logger.info(f"Published batch message to {SESSION_DATA_CREATED_TOPIC} (message_id: {message_id})")
        logger.info(f"  - Files: {len(success_messages)}")
        logger.info(f"  - Total articles: {total_articles}")

    except Exception as e:
        logger.error(f"Error publishing batch message: {e}", exc_info=True)


async def trigger_scraper_for_incomplete_articles(
    incomplete_by_region: dict,
    base_path: str,
    keywords: list,
    triggered_by: str
) -> dict:
    """
    Trigger scraper function via Pub/Sub for incomplete articles.

    Args:
        incomplete_by_region: {'tr': [articles], 'eu': [articles]}
        base_path: GCS path for this run
        keywords: Keywords used
        triggered_by: Who triggered this run

    Returns:
        Dict with triggered scraper info
    """
    if not publisher:
        logger.warning("Publisher not available, skipping scraper trigger")
        return {'triggered': False, 'reason': 'Publisher not available'}

    triggered_info = {}

    for region, articles in incomplete_by_region.items():
        if not articles:
            logger.info(f"No incomplete {region} articles to scrape")
            continue

        # Extract URLs
        urls = []
        for article in articles:
            url = article.get('url') or article.get('original_url')
            if url:
                urls.append(url)

        if not urls:
            logger.warning(f"No valid URLs found for {region} incomplete articles")
            continue

        # Prepare Pub/Sub message with region-specific filename
        message_data = {
            "urls": urls,
            "keywords": keywords,
            "scrape_depth": 0,  # No link discovery, just scrape given URLs
            "persist": False,   # Memory-only mode
            "collection_id": region,
            "triggered_by": triggered_by,
            "api_run_path": base_path,  # Tell scraper where to save
            "output_filename": f"articles_scraped_{region}.json"  # Region-specific filename
        }

        try:
            # Publish to scraping-requests topic
            topic_path = publisher.topic_path(PROJECT_ID, 'scraping-requests')
            data = json.dumps(message_data).encode("utf-8")
            future = publisher.publish(topic_path, data)
            message_id = future.result()

            triggered_info[region] = {
                'message_id': message_id,
                'urls_count': len(urls),
                'articles_count': len(articles)
            }

            logger.info(f"Triggered scraper for {len(urls)} {region} articles (message_id: {message_id})")

        except Exception as e:
            logger.error(f"Error triggering scraper for {region}: {e}", exc_info=True)
            triggered_info[region] = {
                'error': str(e),
                'urls_count': len(urls),
                'articles_count': len(articles)
            }

    # Only return triggered=True if at least one region was successfully triggered
    has_success = any('error' not in info for info in triggered_info.values())

    return {
        'triggered': has_success and len(triggered_info) > 0,
        'regions': triggered_info
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
    
    # Generate storage path
    now = datetime.now(timezone.utc)
    date_str = now.strftime('%Y-%m-%d')
    year_month = now.strftime('%Y-%m')
    run_id = now.strftime('%H-%M-%S')

    # Path: news_data/api/{YYYY-MM}/{YYYY-MM-DD}/run_{HH-MM-SS}/
    base_path = f"{NEWS_DATA_ROOT_PREFIX}api/{year_month}/{date_str}/run_{run_id}"

    # Add source_type and dates to each article
    processed_articles = []
    for article in articles:
        article['source_type'] = 'api'
        article['fetched_at'] = date_str  # YYYY-MM-DD format for easy filtering
        article['keywords_matched'] = keywords
        processed_articles.append(article)

    # Fetch existing articles from same day (CRITICAL - will abort on error)
    try:
        existing_urls = get_existing_articles_for_date(GCS_BUCKET_NAME, date_str, year_month)
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

    # Classify articles by completeness and region
    complete_articles = []
    incomplete_articles_by_region = {'tr': [], 'eu': []}

    for article in processed_articles:
        # Determine region first
        api_source = article.get('api_source', 'unknown')
        region = classify_region(article, api_source)
        article['collection_id'] = region

        # Check completeness
        content = article.get('content', '')
        if is_content_complete(content):
            complete_articles.append(article)
        else:
            incomplete_articles_by_region[region].append(article)

    logger.info(f"Complete articles: {len(complete_articles)}")
    logger.info(f"Incomplete TR articles: {len(incomplete_articles_by_region['tr'])}")
    logger.info(f"Incomplete EU articles: {len(incomplete_articles_by_region['eu'])}")

    # Transform complete articles to session schema and group by source
    from collections import defaultdict
    articles_by_source = defaultdict(list)

    for article in complete_articles:
        transformed = transform_api_article_to_session_schema(article)
        source_domain = transformed['source']
        articles_by_source[source_domain].append(transformed)

    # Create session-like structure for complete articles
    # Group all sources into one file for simplicity (can be split later if needed)
    session_data = {
        'source_domain': 'api_combined',
        'source_url': 'https://api-news-aggregator',
        'articles': [],
        'session_metadata': {
            'session_id': f"api_{run_id}",
            'fetched_at': now.isoformat(),
            'collection_id': 'mixed',  # Contains both TR and EU
            'source_count': len(articles_by_source),
            'extraction_method': 'api_aggregation'
        }
    }

    # Add all transformed articles
    for source_domain, source_articles in articles_by_source.items():
        session_data['articles'].extend(source_articles)
        logger.info(f"  - {source_domain}: {len(source_articles)} complete articles")

    # Upload articles (session schema format)
    articles_path = f"{base_path}/articles.json"
    upload_to_gcs(GCS_BUCKET_NAME, articles_path, session_data)

    # Trigger scraper for incomplete articles
    scraper_trigger_info = await trigger_scraper_for_incomplete_articles(
        incomplete_articles_by_region,
        base_path,
        keywords,
        triggered_by
    )

    # Wait for scrapers to complete and collect all file paths (following scraper_function pattern)
    session_files = []

    # Always include articles.json (complete articles)
    session_files.append({
        'file_path': articles_path,
        'articles_count': len(complete_articles),
        'extraction_method': 'api_aggregation'
    })

    # Wait for scraped files if scrapers were triggered
    if scraper_trigger_info.get('triggered'):
        logger.info("Waiting for scrapers to complete...")
        scraped_files = await wait_for_scraped_files(
            base_path,
            scraper_trigger_info.get('regions', {}),
            timeout_seconds=300  # 5 minute timeout
        )
        session_files.extend(scraped_files)

    # Publish batch message to session-data-created (like scraper_function does)
    if session_files:
        publish_batch_processing_request(session_files, base_path, run_id, triggered_by)

    # Upload metadata
    metadata = {
        'triggered_by': triggered_by,
        'keywords': keywords,
        'time_range': time_range,
        'max_results': max_results,
        'articles_count': len(processed_articles),
        'complete_articles_count': len(complete_articles),
        'incomplete_articles_count_tr': len(incomplete_articles_by_region['tr']),
        'incomplete_articles_count_eu': len(incomplete_articles_by_region['eu']),
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

    total_incomplete = len(incomplete_articles_by_region['tr']) + len(incomplete_articles_by_region['eu'])
    logger.info(f"Successfully processed {len(processed_articles)} articles:")
    logger.info(f"  - Complete: {len(complete_articles)} (stored)")
    logger.info(f"  - Incomplete: {total_incomplete} (triggered scraper)")
    logger.info(f"  - Duplicates filtered: {len(duplicate_urls)}")

    return {
        'status': 'success',
        'articles_count': len(processed_articles),
        'complete_articles_count': len(complete_articles),
        'incomplete_articles_count': total_incomplete,
        'duplicates_filtered': len(duplicate_urls),
        'storage_path': base_path,
        'triggered_by': triggered_by,
        'scraper_triggered': scraper_trigger_info,
        'api_sources_used': aggregator.get_available_sources()
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
