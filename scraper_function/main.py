import os
import sys
import json
import base64
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

# CET timezone for run timestamps
CET = ZoneInfo("Europe/Berlin")

from google.cloud import pubsub_v1, storage
try:
    from journalist import Journalist
    JOURNALIST_AVAILABLE = True
except ImportError:
    JOURNALIST_AVAILABLE = False
    Journalist = None

# Import article ID utility (local copy for Cloud Function deployment)
from article_id import generate_article_id

# Enhanced logging configuration to capture all logs including journalist library
# Use dynamic log level from environment variable
JOURNALIST_LOG_LEVEL = os.getenv('JOURNALIST_LOG_LEVEL', 'INFO')

logging.basicConfig(
    level=getattr(logging, JOURNALIST_LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True  # Force reconfiguration of root logger
)

# Application logger
logger = logging.getLogger(__name__)
logger.info("Logging configuration initialized for cloud environment")

# Initialize Google Cloud clients (only in cloud environment)
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIRONMENT != 'local':
    publisher = pubsub_v1.PublisherClient()
    storage_client = storage.Client()
else:
    publisher = None
    storage_client = None
    logger.info("Running in local environment - skipping Google Cloud client initialization")

# Configuration from environment variables
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
SESSION_DATA_CREATED_TOPIC = os.getenv('SESSION_DATA_CREATED_TOPIC', 'session-data-created')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
NEWS_DATA_ROOT_PREFIX = os.getenv('NEWS_DATA_ROOT_PREFIX', 'news_data/')
# JOURNALIST_LOG_LEVEL already defined above for logging configuration

# =============================================================================
# CONSTANTS
# =============================================================================

# Valid regions for scraping
VALID_REGIONS = {'eu', 'tr'}

# Output file names
OUTPUT_FILE_API_TRIGGERED = 'scraped_incomplete_articles.json'
OUTPUT_FILE_STANDALONE = 'scraped_articles.json'


# =============================================================================
# INPUT VALIDATION
# =============================================================================

def validate_scraping_request(message_data: dict) -> tuple:
    """
    Validate Pub/Sub message payload.
    
    Args:
        message_data: The decoded Pub/Sub message
        
    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    # Required fields
    urls = message_data.get('urls', [])
    if not urls or not isinstance(urls, list):
        return False, "Missing or invalid 'urls' field - must be a non-empty list"
    
    # Region validation
    region = message_data.get('region', 'eu')
    if region not in VALID_REGIONS:
        return False, f"Invalid region '{region}'. Must be one of: {VALID_REGIONS}"
    
    # Scrape depth validation
    scrape_depth = message_data.get('scrape_depth', 1)
    if not isinstance(scrape_depth, int) or scrape_depth < 1:
        return False, f"Invalid scrape_depth: {scrape_depth}. Must be a positive integer"
    
    return True, ""


# =============================================================================
# METADATA HELPERS
# =============================================================================

def load_article_metadata_from_gcs(bucket_name: str, api_run_path: str) -> dict:
    """
    Load article metadata from to_scrape.json.
    
    Returns empty dict if file doesn't exist (standalone mode) or on error.
    This allows the same code path for both API-triggered and standalone scenarios.
    
    Args:
        bucket_name: GCS bucket name
        api_run_path: Path to the run folder (e.g., "ingestion/2025-12-22/16-37-43")
        
    Returns:
        Dict mapping URL -> metadata dict with keys: language, region, publish_date, source_type, article_id
    """
    url_metadata = {}
    
    if ENVIRONMENT == 'local' or not storage_client:
        return url_metadata
    
    to_scrape_path = f"{api_run_path}/to_scrape.json"
    
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(to_scrape_path)
        
        if not blob.exists():
            logger.info(f"No to_scrape.json found at {to_scrape_path} (standalone mode)")
            return url_metadata
        
        to_scrape_data = json.loads(blob.download_as_string())
        for article in to_scrape_data.get('articles', []):
            url = article.get('url')
            if url:
                url_metadata[url] = {
                    'language': article.get('language', ''),
                    'region': article.get('region', 'eu'),
                    'publish_date': article.get('publish_date'),
                    'source_type': article.get('source_type', 'api'),
                    'article_id': article.get('article_id'),
                }
        
        logger.info(f"Loaded metadata for {len(url_metadata)} URLs from to_scrape.json")
        
    except Exception as e:
        logger.warning(f"Could not read to_scrape.json: {e}")
    
    return url_metadata


def apply_metadata_to_articles(articles: list, url_metadata: dict, fallback_region: str) -> list:
    """
    Apply preserved metadata to scraped articles.
    
    For API-triggered runs: Uses metadata from to_scrape.json (language, region, article_id, publish_date)
    For standalone runs: Uses fallback_region, generates article_id, language is empty
    
    Args:
        articles: List of scraped article dicts
        url_metadata: Dict mapping URL -> metadata (from load_article_metadata_from_gcs)
        fallback_region: Region to use if not found in metadata (from Pub/Sub message)
        
    Returns:
        Modified articles list with metadata applied
    """
    for article in articles:
        url = article.get('url') or article.get('original_url', '')
        meta = url_metadata.get(url, {})
        
        if meta:
            # API-triggered: preserve original metadata from to_scrape.json
            article['language'] = meta.get('language', '')
            article['region'] = meta.get('region', fallback_region)
            article['article_id'] = meta.get('article_id') or generate_article_id(url)
            # Preserve publish_date from API if scraper didn't extract one
            if not article.get('published_at') and meta.get('publish_date'):
                article['published_at'] = meta.get('publish_date')
            # Preserve source_type from API (should remain 'api' for API-triggered articles)
            article['source_type'] = meta.get('source_type', 'api')
        else:
            # Standalone: use fallbacks
            article['language'] = ''
            article['region'] = fallback_region
            if not article.get('article_id'):
                article['article_id'] = generate_article_id(url) if url else ''
            # Standalone articles are truly scraped (not from API)
            article['source_type'] = 'scraped'
    
    return articles


def normalize_publish_date(date_value) -> str:
    """
    Normalize publish_date to ISO 8601 format.
    Handles various input formats from journalist library.
    
    Args:
        date_value: Date string, datetime object, or None
        
    Returns:
        ISO 8601 formatted string or empty string if invalid/missing
    """
    if not date_value:
        return ''
    
    # Already a datetime object
    if isinstance(date_value, datetime):
        if date_value.tzinfo is None:
            date_value = date_value.replace(tzinfo=timezone.utc)
        return date_value.isoformat()
    
    # String input - try parsing common formats
    if isinstance(date_value, str):
        date_str = date_value.strip()
        if not date_str:
            return ''
        
        # Already in ISO format
        if 'T' in date_str and ('+' in date_str or 'Z' in date_str or date_str.endswith('+00:00')):
            return date_str
        
        # Try parsing various formats
        formats_to_try = [
            '%Y-%m-%dT%H:%M:%S.%f%z',  # ISO with microseconds and tz
            '%Y-%m-%dT%H:%M:%S%z',      # ISO with tz
            '%Y-%m-%dT%H:%M:%S.%f',     # ISO with microseconds, no tz
            '%Y-%m-%dT%H:%M:%S',        # ISO without tz
            '%Y-%m-%d %H:%M:%S',        # Common datetime format
            '%Y-%m-%d',                  # Date only
            '%d/%m/%Y %H:%M:%S',        # European format
            '%d/%m/%Y',                  # European date only
            '%m/%d/%Y %H:%M:%S',        # US format
            '%m/%d/%Y',                  # US date only
        ]
        
        for fmt in formats_to_try:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.isoformat()
            except ValueError:
                continue
        
        # If all parsing fails, return original string (better than losing data)
        logger.warning(f"Could not parse publish_date: {date_str}")
        return date_str
    
    return ''


def normalize_article_for_session_schema(article: dict, region: str, language: str, source_domain: str) -> dict:
    """
    Normalize article fields to match the session schema used by news_api_fetcher.
    Ensures consistency between API-sourced and scraped articles.
    
    Args:
        article: Raw article dict from journalist library
        region: Region from Pub/Sub message ('eu' or 'tr')
        language: Language code or empty string
        source_domain: Source domain for the article
        
    Returns:
        Normalized article dict matching session schema
    """
    from urllib.parse import urlparse
    
    url = article.get('url') or article.get('link') or article.get('original_url', '')
    
    # Extract domain if not provided
    if not source_domain and url:
        parsed = urlparse(url)
        source_domain = parsed.netloc
    
    # Normalize body field (journalist may use 'content' or 'body')
    body = article.get('body') or article.get('content', '')
    
    # Normalize publish_date
    publish_date = normalize_publish_date(
        article.get('publish_date') or article.get('published_at') or article.get('published_date')
    )
    
    # Build normalized article
    normalized = {
        'url': url,
        'scraped_at': article.get('scraped_at', datetime.now(timezone.utc).isoformat()),
        'keywords_used': article.get('keywords_used', article.get('keywords_matched', [])),
        'title': article.get('title', ''),
        'body': body,
        'publish_date': publish_date,
        'source': source_domain,
        'extraction_method': article.get('extraction_method', 'journalist'),
        'source_type': 'scraped',
        'site': source_domain,
        'article_id': article.get('article_id', generate_article_id(url) if url else ''),
        'language': language,
        'region': region,
    }
    
    # Preserve any additional fields from journalist that might be useful
    for key in ['author', 'description', 'image_url', 'meta_description']:
        if key in article and article[key]:
            normalized[key] = article[key]
    
    return normalized


def is_first_run_of_day(storage_client, bucket_name, date_obj, region="eu"):
    """
    Check if this is the first run of the day by checking if the batch_processing folder exists for today.
    Returns True if no batch processing has been done today (first run), False otherwise.
    """
    if not storage_client:
        return False
    
    try:
        current_year_month = date_obj.strftime("%Y-%m")
        current_date = date_obj.strftime("%Y-%m-%d")
        
        # Check batch_processing folder: news_data/batch_processing/{region}/{YYYY-MM}/{YYYY-MM-DD}/
        prefix = f"{NEWS_DATA_ROOT_PREFIX}batch_processing/{region}/{current_year_month}/{current_date}/"
        
        logger.info(f"Checking if first run of day by inspecting: {prefix}")
        
        bucket = storage_client.bucket(bucket_name)
        blobs = list(bucket.list_blobs(prefix=prefix, max_results=1))
        
        is_first_run = len(blobs) == 0
        logger.info(f"First run of the day: {is_first_run}")
        
        return is_first_run
        
    except Exception as e:
        logger.error(f"Error checking first run status: {e}")
        # Default to False (assume not first run) to avoid over-fetching
        return False

def get_processed_urls_last_n_days(storage_client, bucket_name, date_obj, region="eu", days=7):
    """
    Retrieves a set of already processed URLs from source session data for the last N days.
    Used when it's the first run of the day to avoid re-scraping recent articles.
    """
    processed_urls = set()
    if not storage_client:
        return processed_urls
    
    try:
        bucket = storage_client.bucket(bucket_name)
        
        logger.info(f"Fetching processed URLs from last {days} days for collection '{region}'")
        
        # Iterate through the last N days
        for day_offset in range(days):
            check_date = date_obj - timedelta(days=day_offset)
            year_month = check_date.strftime("%Y-%m")
            date_str = check_date.strftime("%Y-%m-%d")
            
            # Prefix: news_data/sources/{region}/{YYYY-MM}/{YYYY-MM-DD}/
            prefix = f"{NEWS_DATA_ROOT_PREFIX}sources/{region}/{year_month}/{date_str}/"
            
            logger.info(f"  Scanning day {day_offset + 1}/{days}: {date_str} (prefix: {prefix})")
            
            blobs = bucket.list_blobs(prefix=prefix)
            
            source_files = []
            for blob in blobs:
                # Check for session_data_*.json files
                if blob.name.endswith(".json") and "session_data_" in blob.name:
                    source_files.append(blob)
            
            logger.info(f"    Found {len(source_files)} source session files for {date_str}")
            
            for blob in source_files:
                try:
                    content = blob.download_as_text()
                    data = json.loads(content)
                    
                    articles = data.get("articles", [])
                    for article in articles:
                        # Check various common fields for URL
                        url = article.get("url") or article.get("link") or article.get("original_url")
                        if url:
                            processed_urls.add(url)
                            
                except Exception as e:
                    logger.warning(f"Error reading/parsing blob {blob.name}: {e}")
        
        logger.info(f"Total unique processed URLs found in last {days} days: {len(processed_urls)}")
        
    except Exception as e:
        logger.error(f"Error fetching processed URLs from last {days} days: {e}")
    
    return processed_urls

def get_processed_urls_for_date(storage_client, bucket_name, date_obj, region="eu"):
    """
    Retrieves a set of already processed URLs from raw source session data for the given date and collection.
    This ensures we don't re-scrape or re-process articles that have already been collected today.
    """
    processed_urls = set()
    if not storage_client:
        return processed_urls

    try:
        current_year_month = date_obj.strftime("%Y-%m")
        current_date = date_obj.strftime("%Y-%m-%d")
        
        # Prefix: news_data/sources/{region}/{YYYY-MM}/{YYYY-MM-DD}/
        prefix = f"{NEWS_DATA_ROOT_PREFIX}sources/{region}/{current_year_month}/{current_date}/"
        
        logger.info(f"Checking for existing processed URLs in source files: {prefix}")
        
        bucket = storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        
        source_files = []
        for blob in blobs:
            # Check for session_data_*.json files
            if blob.name.endswith(".json") and "session_data_" in blob.name:
                source_files.append(blob)
        
        logger.info(f"Found {len(source_files)} source session files to check for duplicates")
        
        for blob in source_files:
            try:
                content = blob.download_as_text()
                data = json.loads(content)
                
                articles = data.get("articles", [])
                for article in articles:
                    # Check various common fields for URL
                    url = article.get("url") or article.get("link") or article.get("original_url")
                    if url:
                        processed_urls.add(url)
                        
            except Exception as e:
                logger.warning(f"Error reading/parsing blob {blob.name}: {e}")
                
        logger.info(f"Total unique processed URLs found for today in source files: {len(processed_urls)}")
        
    except Exception as e:
        logger.error(f"Error fetching processed URLs: {e}")
        
    return processed_urls

async def _process_scraping_request(message_data: dict):
    """
    Process a scraping request by extracting content from URLs with keywords.
    
    Args:
        message_data (dict): Dictionary containing 'urls', 'keywords', and optionally 'scrape_depth', 'persist'
    """
    logger.info(f"Received scraping request: {message_data}")
    
    # ==========================================================================
    # INPUT VALIDATION
    # ==========================================================================
    is_valid, error_msg = validate_scraping_request(message_data)
    if not is_valid:
        logger.error(f"Invalid scraping request: {error_msg}")
        return
    
    # Extract and validate parameters
    urls = message_data.get("urls")
    keywords = message_data.get("keywords")
    scrape_depth = message_data.get("scrape_depth", 1)
    persist = message_data.get("persist", True)
    log_level = message_data.get("log_level", JOURNALIST_LOG_LEVEL)
    region = message_data.get("region", "eu")
    triggered_by = message_data.get("triggered_by", "system")

    # Generate Run ID for this execution (HH-MM-SS format in CET)
    run_id = datetime.now(CET).strftime('%H-%M-%S')
    logger.info(f"Generated Run ID: {run_id}")

    # ==========================================================================
    # DETERMINE MODE: API-TRIGGERED vs STANDALONE
    # ==========================================================================
    api_run_path = message_data.get("api_run_path")  # e.g., "ingestion/2025-12-22/16-37-43"
    
    is_standalone = not api_run_path
    if is_standalone:
        current_date = datetime.now(CET).strftime('%Y-%m-%d')
        api_run_path = f"ingestion/{current_date}/{run_id}"
        logger.info(f"Standalone mode: Generated run path {api_run_path}")
    else:
        logger.info(f"API-triggered mode: Using run path {api_run_path}")

    # Determine output filename based on mode
    output_filename = OUTPUT_FILE_STANDALONE if is_standalone else OUTPUT_FILE_API_TRIGGERED

    if not keywords:
        logger.error("Missing 'keywords' in the request.")
        return

    if not JOURNALIST_AVAILABLE:
        logger.error("Journalist library is not available. Please ensure journ4list is installed.")
        return
    
    try:
        # Initialize Journalist with configuration from message payload
        logger.info(f"Initializing Journalist with persist={persist}, scrape_depth={scrape_depth}, log_level={log_level}")
        logger.info(f"Target URLs: {urls}")
        logger.info(f"Keywords: {keywords}")
        logger.info(f"Triggered by: {triggered_by}")
        
        journalist = Journalist(persist=persist, scrape_depth=scrape_depth)
        
        # Start timing the scraping operation
        start_time = datetime.now(timezone.utc)
        logger.info(f"Scraping started at: {start_time.isoformat()}")

        # Run ID already generated above
        
        # Perform scraping with enhanced logging
        logger.info("Starting scraping operation...")
        logger.info("=== JOURNALIST SCRAPING BEGINS ===")
        
        # List /tmp directory contents
        tmp_contents_before = list(Path("/tmp").iterdir())
        logger.info(f"/tmp contents before: {[str(p) for p in tmp_contents_before]}")
        
        # Create test file
        test_file = Path("/tmp/test")
        test_file.write_text("dummy")
        logger.info(f"Created test file at {test_file}")
        
        # List /tmp directory contents again
        tmp_contents_after = list(Path("/tmp").iterdir())
        logger.info(f"/tmp contents after: {[str(p) for p in tmp_contents_after]}")
        

        source_sessions = await journalist.read(
            urls=urls, 
            keywords=keywords,
            log_level=log_level  # Use the log_level from payload or environment variable
        )
        
        logger.info("=== JOURNALIST SCRAPING COMPLETED ===")
        
        if not source_sessions:
            logger.warning("No sessions returned from journalist.read()")
            return

        logger.info(f"Successfully completed scraping. Found {len(source_sessions)} sessions")

        # Log source_domain for each session after evaluation
        logger.info("=== SOURCE DOMAINS FOR EACH SESSION ===")
        for i, session in enumerate(source_sessions):
            source_domain = session.get("source_domain", "unknown_source")
            logger.info(f"source_sessions[{i}][\"source_domain\"] = {source_domain}")
        logger.info("=== END SOURCE DOMAINS ===")

        # API Integration mode (or Standalone mode mimicking API structure)
        # We now always use this path for unified behavior
        if api_run_path:
            logger.info(f"Saving to {api_run_path} (Standalone: {is_standalone})")

            # ==========================================================================
            # LOAD METADATA FROM to_scrape.json (API-triggered only)
            # ==========================================================================
            # For API-triggered runs, load metadata from to_scrape.json to preserve
            # original API-derived fields (language, region, publish_date, article_id)
            # For standalone runs, this returns empty dict (no to_scrape.json exists)
            url_metadata = load_article_metadata_from_gcs(GCS_BUCKET_NAME, api_run_path) if not is_standalone else {}

            # ==========================================================================
            # MERGE SESSIONS AND APPLY METADATA
            # ==========================================================================
            all_articles = []
            source_domains = []

            for session in source_sessions:
                articles = session.get("articles", [])
                
                # Apply metadata from to_scrape.json (or fallbacks for standalone)
                apply_metadata_to_articles(articles, url_metadata, fallback_region=region)
                        
                all_articles.extend(articles)
                source_domain = session.get("source_domain", "unknown")
                if source_domain not in source_domains:
                    source_domains.append(source_domain)

            # Prepare upload data in session schema format
            upload_data = {
                'source_domain': 'scraped_combined' if is_standalone else 'api_combined',
                'source_url': 'https://scraper-standalone' if is_standalone else 'https://api-news-aggregator',
                'articles': all_articles,
                'session_metadata': {
                    'session_id': f"scraper_{run_id}",
                    'scraped_at': datetime.now(timezone.utc).isoformat(),
                    'source_domains': source_domains,
                    'source_count': len(source_domains),
                    'extraction_method': 'journalist',
                    'triggered_by': triggered_by,
                    'api_integration': not is_standalone
                }
            }

            logger.info(f"Merged {len(all_articles)} articles from {len(source_sessions)} sessions ({len(source_domains)} sources)")

            # For standalone runs, create metadata.json to match API-triggered structure
            if is_standalone and ENVIRONMENT != 'local':
                try:
                    metadata = {
                        'triggered_by': triggered_by,
                        'keywords': keywords,
                        'urls_count': len(urls),
                        'articles_count': len(all_articles),
                        'source_domains': source_domains,
                        'api_sources_used': [],  # Empty for standalone
                        'started_at': start_time.isoformat(),
                        'completed_at': datetime.now(timezone.utc).isoformat(),
                        'is_standalone': True
                    }
                    metadata_path = f"{api_run_path}/metadata.json"
                    bucket = storage_client.bucket(GCS_BUCKET_NAME)
                    blob = bucket.blob(metadata_path)
                    blob.upload_from_string(
                        json.dumps(metadata, indent=2, ensure_ascii=False),
                        content_type='application/json'
                    )
                    logger.info(f"✓ Saved metadata to gs://{GCS_BUCKET_NAME}/{metadata_path}")
                except Exception as e:
                    logger.warning(f"Failed to save metadata.json: {e}")

            # Upload to GCS
            # For standalone, use scraped_articles.json to distinguish from incomplete flow
            filename = "scraped_articles.json" if is_standalone else "scraped_incomplete_articles.json"
            scraped_file_path = f"{api_run_path}/{filename}"

            if ENVIRONMENT != 'local':
                try:
                    bucket = storage_client.bucket(GCS_BUCKET_NAME)
                    blob = bucket.blob(scraped_file_path)
                    blob.upload_from_string(
                        json.dumps(upload_data, indent=2, ensure_ascii=False),
                        content_type='application/json'
                    )
                    logger.info(f"✓ Saved scraped articles to gs://{GCS_BUCKET_NAME}/{scraped_file_path}")
                except Exception as e:
                    logger.error(f"Error uploading to GCS: {e}", exc_info=True)
                    return
            else:
                logger.info(f"Local mode: Would upload to {scraped_file_path}")

            # Extract run_id from api_run_path (e.g., "ingestion/api/2025-12-19/14-15-14" -> "14-15-14")
            api_run_id = api_run_path.split('/')[-1] if '/' in api_run_path else run_id

            # Publish to SESSION_DATA_CREATED_TOPIC
            
            success_messages_list = [
                {
                    'status': 'success',
                    'gcs_path': f"gs://{GCS_BUCKET_NAME}/{scraped_file_path}",
                    'source_domain': 'scraped' if is_standalone else 'api_scraped',
                    'articles_count': len(all_articles),
                    'triggered_by': triggered_by,
                    'processed_at': datetime.now(timezone.utc).isoformat()
                }
            ]
            
            # Only include complete_articles if NOT standalone
            if not is_standalone:
                complete_file_path = f"{api_run_path}/complete_articles.json"
                success_messages_list.append({
                    'status': 'success',
                    'gcs_path': f"gs://{GCS_BUCKET_NAME}/{complete_file_path}",
                    'source_domain': 'api_complete',
                    'triggered_by': triggered_by,
                    'processed_at': datetime.now(timezone.utc).isoformat()
                })

            batch_message = {
                'status': 'batch_success',
                'run_id': api_run_id,
                'batch_size': len(success_messages_list),
                'success_messages': success_messages_list,
                'batch_processed_at': datetime.now(timezone.utc).isoformat(),
                'total_articles': len(all_articles)
            }

            if ENVIRONMENT != 'local':
                try:
                    logger.info(f"Publishing batch message to SESSION_DATA_CREATED_TOPIC with {len(success_messages_list)} files:")
                    for msg in success_messages_list:
                        logger.info(f"  - {msg['gcs_path']}")

                    topic_path = publisher.topic_path(PROJECT_ID, SESSION_DATA_CREATED_TOPIC)
                    future = publisher.publish(topic_path, json.dumps(batch_message).encode("utf-8"))
                    future.result()  # Wait for publish to complete

                    logger.info("✓ Successfully published batch message to SESSION_DATA_CREATED_TOPIC")
                except Exception as pub_error:
                    logger.error(f"Failed to publish batch message: {pub_error}", exc_info=True)
                    return
            else:
                logger.info(f"Local mode: Would publish batch message to SESSION_DATA_CREATED_TOPIC")
                logger.info(f"Message: {json.dumps(batch_message, indent=2)}")

            logger.info("Batch processing completed. Exiting.")
            return

        # NOTE: If we reach here, api_run_path was falsy which shouldn't happen
        # since we generate one for standalone mode. This is a safety net.
        logger.error("Unexpected code path: api_run_path is falsy after initialization")

    except Exception as e:
        logger.error(f"An error occurred during scraping: {e}", exc_info=True)
        
        # Publish error message to the same topic with error status (only in cloud environment)
        error_message = {
            "status": "error",
            "error": str(e),
            "urls": urls,
            "keywords": keywords,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }
        
        if ENVIRONMENT == 'local':
            logger.error(f"Local processing error: {json.dumps(error_message, indent=2)}")
        else:
            try:
                logger.info("Publishing error message")
                topic_path = publisher.topic_path(PROJECT_ID, SESSION_DATA_CREATED_TOPIC)
                future = publisher.publish(topic_path, json.dumps(error_message).encode("utf-8"))
                future.result()
                logger.info("Successfully published error message")
            except Exception as pub_error:
                logger.error(f"Failed to publish error message: {pub_error}")

def scrape_and_store(event, context):
    """
    Background Cloud Function to be triggered by Pub/Sub.
    
    Args:
        event (dict): The Pub/Sub message data.
        context (google.cloud.functions.Context): The Cloud Functions event metadata.
    """
    logger.info(f"=== CLOUD FUNCTION TRIGGERED ===")
    logger.info(f"Function triggered with event: {event}")
    logger.info(f"Context: {context}")
    
    if isinstance(event, dict) and "data" in event:
        try:
            message_data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
            logger.info(f"Decoded message data: {message_data}")
            asyncio.run(_process_scraping_request(message_data))
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
    else:
        logger.error("Invalid Pub/Sub message format")
    
    logger.info(f"=== CLOUD FUNCTION EXECUTION COMPLETED ===")

def get_test_data():
    """
    Load test parameters from search_parameters.json for local execution.
    This replaces all hardcoded test data.
    """
    try:
        # Determine the path to search_parameters.json relative to this file
        current_dir = Path(__file__).parent
        params_file = current_dir.parent / "search_parameters.json"
        
        if not params_file.exists():
            raise FileNotFoundError(f"search_parameters.json not found at {params_file}")
        
        with open(params_file, 'r', encoding='utf-8') as f:
            test_data = json.load(f)
        
        # Ensure required fields are present
        required_fields = ["keywords", "urls", "scrape_depth"]
        for field in required_fields:
            if field not in test_data:
                raise ValueError(f"Required field '{field}' missing from search_parameters.json")
        
        # Set default values for optional fields
        test_data.setdefault("persist", True)  # Enable persist for local testing
        test_data.setdefault("log_level", "INFO")
        
        logger.info(f"Successfully loaded test parameters from {params_file}")
        return test_data
        
    except Exception as e:
        logger.error(f"Failed to load test parameters from search_parameters.json: {e}")
        raise RuntimeError(f"Cannot load test parameters: {e}")

async def main_local():
    """
    Main function for local execution.
    Loads test parameters from search_parameters.json instead of using hardcoded data.
    """
    logger.info("=== STARTING LOCAL EXECUTION ===")
    logger.info(f"Environment: {ENVIRONMENT}")
    
    # Get test data
    test_data = get_test_data()
    logger.info(f"Using test data: {json.dumps(test_data, indent=2)}")
    
    # Process the scraping request
    await _process_scraping_request(test_data)
    
    logger.info("=== LOCAL EXECUTION COMPLETED ===")

if __name__ == "__main__":
    if ENVIRONMENT == 'local':
        logger.info("Running in local mode")
        asyncio.run(main_local())
    else:
        logger.info("Running in cloud mode - use Pub/Sub trigger")
