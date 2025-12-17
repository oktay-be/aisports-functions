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
from news_aggregator import NewsAggregator

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
else:
    storage_client = None
    secret_client = None
    logger.info("Running in local environment - skipping Google Cloud client initialization")

# Configuration from environment variables
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
NEWS_DATA_ROOT_PREFIX = os.getenv('NEWS_DATA_ROOT_PREFIX', 'news_data/')

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

    # Upload articles
    articles_path = f"{base_path}/articles.json"
    upload_to_gcs(GCS_BUCKET_NAME, articles_path, {
        'articles': processed_articles,
        'count': len(processed_articles),
        'fetched_at': now.isoformat()
    })

    # Upload metadata
    metadata = {
        'triggered_by': triggered_by,
        'keywords': keywords,
        'time_range': time_range,
        'max_results': max_results,
        'articles_count': len(processed_articles),
        'duplicates_filtered': len(duplicate_urls),
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

    logger.info(f"Successfully stored {len(processed_articles)} unique articles to {base_path} ({len(duplicate_urls)} duplicates filtered)")

    return {
        'status': 'success',
        'articles_count': len(processed_articles),
        'duplicates_filtered': len(duplicate_urls),
        'storage_path': base_path,
        'triggered_by': triggered_by,
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
