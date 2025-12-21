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
    urls = message_data.get("urls")
    keywords = message_data.get("keywords")
    scrape_depth = message_data.get("scrape_depth", 1)  # Default to 1 if not provided
    persist = message_data.get("persist", True)  # Default to True if not provided
    log_level = message_data.get("log_level", JOURNALIST_LOG_LEVEL)  # Use payload log_level or env var
    region = message_data.get("region", "eu")  # Default to "eu" if not provided
    triggered_by = message_data.get("triggered_by", "system")  # Track who triggered the scrape

    # API Integration mode (for News API incomplete articles)
    api_run_path = message_data.get("api_run_path")  # e.g., "news_data/api/2025-12/2025-12-17/run_10-59-06"
    output_filename = message_data.get("output_filename", "articles_scraped.json")  # e.g., "articles_scraped_tr.json"

    if not urls or not keywords:
        logger.error("Missing 'urls' or 'keywords' in the request.")
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

        # Generate Run ID for this execution (HH-MM-SS format in CET)
        run_id = datetime.now(CET).strftime('%H-%M-%S')
        logger.info(f"Generated Run ID: {run_id}")
        
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

        # API Integration mode: Save scraped articles
        if api_run_path:
            logger.info(f"API integration mode detected: saving to {api_run_path}/scraped_incomplete_articles.json")

            # Read to_scrape.json to get original language/region for each URL
            url_metadata = {}  # url -> {language, region}
            to_scrape_path = f"{api_run_path}/to_scrape.json"
            
            if ENVIRONMENT != 'local' and storage_client:
                try:
                    bucket = storage_client.bucket(GCS_BUCKET_NAME)
                    blob = bucket.blob(to_scrape_path)
                    if blob.exists():
                        to_scrape_data = json.loads(blob.download_as_string())
                        for article in to_scrape_data.get('articles', []):
                            url = article.get('url')
                            if url:
                                url_metadata[url] = {
                                    'language': article.get('language', ''),
                                    'region': article.get('region', 'eu')
                                }
                        logger.info(f"Loaded language/region metadata for {len(url_metadata)} URLs from to_scrape.json")
                    else:
                        logger.warning(f"to_scrape.json not found at {to_scrape_path}")
                except Exception as e:
                    logger.warning(f"Could not read to_scrape.json: {e}")

            # Merge all sessions into single list of articles
            all_articles = []
            source_domains = []

            for session in source_sessions:
                articles = session.get("articles", [])
                # Add language and region to each article from original to_scrape.json data
                for article in articles:
                    url = article.get('url') or article.get('original_url', '')
                    original_meta = url_metadata.get(url, {})
                    
                    if 'language' not in article or not article.get('language'):
                        article['language'] = original_meta.get('language', '')
                    if 'region' not in article or not article.get('region'):
                        article['region'] = original_meta.get('region', 'eu')
                all_articles.extend(articles)
                source_domain = session.get("source_domain", "unknown")
                if source_domain not in source_domains:
                    source_domains.append(source_domain)

            # Prepare upload data in session schema format
            upload_data = {
                'source_domain': 'api_combined',
                'source_url': 'https://api-news-aggregator',
                'articles': all_articles,
                'session_metadata': {
                    'session_id': f"api_scraper_{run_id}",
                    'scraped_at': datetime.now(timezone.utc).isoformat(),
                    'source_domains': source_domains,
                    'source_count': len(source_domains),
                    'extraction_method': 'journalist',
                    'triggered_by': triggered_by,
                    'api_integration': True
                }
            }

            logger.info(f"Merged {len(all_articles)} articles from {len(source_sessions)} sessions ({len(source_domains)} sources)")

            # Upload to GCS (same level as complete_articles.json)
            scraped_file_path = f"{api_run_path}/scraped_incomplete_articles.json"

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

            # Publish to SESSION_DATA_CREATED_TOPIC with both scraped and complete articles
            complete_file_path = f"{api_run_path}/complete_articles.json"

            batch_message = {
                'status': 'batch_success',
                'run_id': api_run_id,
                'batch_size': 2,
                'success_messages': [
                    {
                        'status': 'success',
                        'gcs_path': f"gs://{GCS_BUCKET_NAME}/{scraped_file_path}",
                        'source_domain': 'api_scraped',
                        'articles_count': len(all_articles),
                        'triggered_by': triggered_by,
                        'processed_at': datetime.now(timezone.utc).isoformat()
                    },
                    {
                        'status': 'success',
                        'gcs_path': f"gs://{GCS_BUCKET_NAME}/{complete_file_path}",
                        'source_domain': 'api_complete',
                        'triggered_by': triggered_by,
                        'processed_at': datetime.now(timezone.utc).isoformat()
                    }
                ],
                'batch_processed_at': datetime.now(timezone.utc).isoformat(),
                'total_articles': len(all_articles)
            }

            if ENVIRONMENT != 'local':
                try:
                    logger.info(f"Publishing batch message to SESSION_DATA_CREATED_TOPIC with 2 files:")
                    logger.info(f"  1. {scraped_file_path} ({len(all_articles)} articles)")
                    logger.info(f"  2. {complete_file_path}")

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

            logger.info("API integration mode: Batch processing triggered. Exiting.")
            return

        # Initialize list to accumulate success messages for batch publishing
        success_messages = []
        
        # Fetch processed URLs for deduplication
        processed_urls = set()
        if ENVIRONMENT != 'local':
            # Check if this is the first run of the day
            first_run = is_first_run_of_day(storage_client, GCS_BUCKET_NAME, start_time, region)
            
            if first_run:
                logger.info("First run of the day detected - scanning last 7 days for deduplication")
                processed_urls = get_processed_urls_last_n_days(storage_client, GCS_BUCKET_NAME, start_time, region, days=7)
            else:
                logger.info("Subsequent run - scanning only today's data for deduplication")
                processed_urls = get_processed_urls_for_date(storage_client, GCS_BUCKET_NAME, start_time, region)

        # Process each session
        # In non-API mode (direct scraper trigger), use the region parameter
        # language is set based on region: 'tr' -> 'tr', others -> empty
        language_for_region = 'tr' if region == 'tr' else ''
        
        for i, session in enumerate(source_sessions):
            logger.info(f"Processing session {i+1}/{len(source_sessions)}")
            
            # Deduplicate articles
            articles = session.get("articles", [])
            unique_articles = []
            dropped_articles = []
            
            for article in articles:
                # Check various common fields for URL
                url = article.get("url") or article.get("link") or article.get("original_url")
                if url and url in processed_urls:
                    dropped_articles.append(article)
                else:
                    # Generate unique article ID based on URL
                    if url:
                        article["article_id"] = generate_article_id(url)
                    # Add language and region based on the scraper's region parameter
                    if 'language' not in article or not article.get('language'):
                        article['language'] = language_for_region
                    if 'region' not in article or not article.get('region'):
                        article['region'] = region
                    unique_articles.append(article)
                    if url:
                        processed_urls.add(url)
            
            if dropped_articles:
                logger.info(f"Dropped {len(dropped_articles)} duplicate articles for session {i+1}")
                session["articles"] = unique_articles
                # We do not store the dropped articles to keep the file size small
                session["articles_count"] = len(unique_articles)
                session["dropped_articles_count"] = len(dropped_articles)
            
            # Check if there are any articles left after deduplication
            if not session.get("articles"):
                logger.warning(f"No articles found for session {i+1} (source: {session.get('source_domain', 'unknown')}) after deduplication. Skipping storage.")
                continue

            # Extract domain from session or URL and make it filesystem-safe
            from werkzeug.utils import secure_filename
            source_domain = session.get("source_domain", "unknown_source")
            if not source_domain or source_domain == "unknown_source":
                logger.error(f"No valid source_domain found for session {i+1}")
                continue  # Skip this session
            else:
                # Make it filesystem-safe and convert dots to underscores
                source_domain = secure_filename(source_domain).replace(".", "_") or "unknown_source"
            
            # Get session ID or create one
            session_id = session.get("session_metadata", {}).get("session_id", f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
            
            # Log session details
            articles_count = session.get("articles_count", 0)
            logger.info(f"Session {i+1} details:")
            logger.info(f"  - Source domain: {source_domain}")
            logger.info(f"  - Session ID: {session_id}")
            logger.info(f"  - Articles count: {articles_count}")
            
            # Construct GCS path based on new structure
            current_year_month = start_time.strftime("%Y-%m")
            current_date = start_time.strftime("%Y-%m-%d")
            
            # New structure: news_data/sources/{region}/{YYYY-MM}/{YYYY-MM-DD}/{source_domain}/session_data_{source_domain}_{session_id}.json
            gcs_object_path = f"{NEWS_DATA_ROOT_PREFIX}sources/{region}/{current_year_month}/{current_date}/{source_domain}/session_data_{source_domain}_{session_id}.json"

            if ENVIRONMENT == 'local':                
                # Create success message for batch processing
                success_message = {
                    "status": "success",
                    "run_id": run_id,
                    "source_domain": source_domain,
                    "session_id": session_id,
                    "date_path": current_date,
                    "articles_count": articles_count,
                    "keywords": keywords,
                    "scrape_depth": scrape_depth,
                    "persist": persist,
                    "triggered_by": triggered_by,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }
                success_messages.append(success_message)
                logger.info(f"Local processing success message added to batch: {json.dumps(success_message, indent=2)}")
                
            else:                    
                # Cloud environment: Upload to GCS and publish message
                logger.info(f"Uploading to GCS: gs://{GCS_BUCKET_NAME}/{gcs_object_path}")
                bucket = storage_client.bucket(GCS_BUCKET_NAME)
                blob = bucket.blob(gcs_object_path)
                # blob.upload_from_string(json.dumps(session, indent=2, ensure_ascii=False), content_type='application/json')

                # Write session data to tmp file
                tmp_file_path = Path(f"/tmp/session_data_{source_domain}_{session_id}.json")
                with open(tmp_file_path, 'w', encoding='utf-8') as f:
                    json.dump(session, f, indent=2, ensure_ascii=False)
                logger.info(f"Session data written to {tmp_file_path}")
                  # Upload from file
                blob.upload_from_filename(str(tmp_file_path), content_type='application/json')
                logger.info(f"Successfully uploaded to GCS")
                logger.info(f"File persisted at: ")
                
                # Create success message for batch processing
                success_message = {
                    "status": "success",
                    "run_id": run_id,
                    "gcs_path": f"gs://{GCS_BUCKET_NAME}/{gcs_object_path}",
                    "source_domain": source_domain,
                    "session_id": session_id,
                    "date_path": current_date,
                    "articles_count": articles_count,
                    "keywords": keywords,
                    "scrape_depth": scrape_depth,
                    "persist": persist,
                    "triggered_by": triggered_by,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }
                success_messages.append(success_message)
                logger.info(f"Cloud processing success message added to batch for session {session_id}")

        # After processing all sessions, publish accumulated success messages as a batch
        if success_messages:
            logger.info(f"=== BATCH PUBLISHING {len(success_messages)} SUCCESS MESSAGES ===")
            
            if ENVIRONMENT == 'local':
                logger.info("Local environment: Batch success messages summary:")
                for i, msg in enumerate(success_messages):
                    logger.info(f"  Message {i+1}: {msg['source_domain']} - {msg['session_id']} ({msg['articles_count']} articles)")
                logger.info(f"Total success messages in batch: {len(success_messages)}")
            else:
                try:
                    # Create batch message containing all success messages
                    batch_message = {
                        "status": "batch_success",
                        "run_id": run_id,
                        "batch_size": len(success_messages),
                        "success_messages": success_messages,
                        "batch_processed_at": datetime.now(timezone.utc).isoformat(),
                        "total_articles": sum(msg.get("articles_count", 0) for msg in success_messages)
                    }
                    
                    logger.info(f"Publishing batch success message with {len(success_messages)} individual messages")
                    topic_path = publisher.topic_path(PROJECT_ID, SESSION_DATA_CREATED_TOPIC)
                    future = publisher.publish(topic_path, json.dumps(batch_message).encode("utf-8"))
                    future.result()  # Wait for publish to complete
                    logger.info(f"Successfully published batch message with {len(success_messages)} success messages")
                    logger.info(f"Total articles in batch: {batch_message['total_articles']}")
                    
                except Exception as pub_error:
                    logger.error(f"Failed to publish batch success message: {pub_error}")
        else:
            logger.warning("No success messages to publish in batch")

        logger.info(f"=== SCRAPING PROCESS COMPLETED SUCCESSFULLY ===")
        logger.info(f"Total sessions processed: {len(source_sessions)}")        
        # Log total elapsed time for the entire process
        total_elapsed_time = datetime.now(timezone.utc) - start_time
        logger.info(f"Total elapsed time: {total_elapsed_time.total_seconds():.2f} seconds")

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
