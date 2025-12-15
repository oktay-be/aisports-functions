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
        return os.getenv(secret_id, '')
    
    try:
        name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
        response = secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.error(f"Error accessing secret {secret_id}: {e}")
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
    max_results = message_data.get('max_results', 50)
    
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
    
    # Add source_type to each article
    processed_articles = []
    for article in articles:
        article['source_type'] = 'api'
        article['fetched_at'] = now.isoformat()
        article['keywords_matched'] = keywords
        processed_articles.append(article)
    
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
        'api_sources_used': aggregator.get_available_sources(),
        'started_at': now.isoformat(),
        'completed_at': datetime.now(timezone.utc).isoformat()
    }
    metadata_path = f"{base_path}/metadata.json"
    upload_to_gcs(GCS_BUCKET_NAME, metadata_path, metadata)
    
    logger.info(f"Successfully stored {len(processed_articles)} articles to {base_path}")
    
    return {
        'status': 'success',
        'articles_count': len(processed_articles),
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
