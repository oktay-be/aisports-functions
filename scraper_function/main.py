import os
import json
import base64
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import pubsub_v1, storage
try:
    from journalist import Journalist
    JOURNALIST_AVAILABLE = True
except ImportError:
    JOURNALIST_AVAILABLE = False
    Journalist = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Google Cloud clients
publisher = pubsub_v1.PublisherClient()
storage_client = storage.Client()

# Configuration from environment variables
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
SESSION_DATA_CREATED_TOPIC = os.getenv('SESSION_DATA_CREATED_TOPIC', 'session-data-created')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-news-data')
NEWS_DATA_ROOT_PREFIX = os.getenv('NEWS_DATA_ROOT_PREFIX', 'news_data/')
ARTICLES_SUBFOLDER = os.getenv('ARTICLES_SUBFOLDER', 'articles/')

async def _process_scraping_request(message_data: dict):
    """
    Process a scraping request by extracting content from URLs with keywords.
    
    Args:
        message_data (dict): Dictionary containing 'urls' and 'keywords'
    """
    logger.info(f"Received scraping request: {message_data}")
    urls = message_data.get("urls")
    keywords = message_data.get("keywords")

    if not urls or not keywords:
        logger.error("Missing 'urls' or 'keywords' in the request.")
        return

    if not JOURNALIST_AVAILABLE:
        logger.error("Journalist library is not available. Please ensure journ4list is installed.")
        return
    
    try:
        # Initialize Journalist with configuration similar to legacy code
        journalist = Journalist(persist=True, scrape_depth=2)
        
        # Perform scraping
        source_sessions = await journalist.read(urls=urls, keywords=keywords)

        if not source_sessions:
            logger.warning("No sessions returned from journalist.read()")
            return

        # Process each session
        for session in source_sessions:
            # Extract domain from session or URL
            source_domain = session.get("source_domain", "unknown_source")
            if not source_domain or source_domain == "unknown_source":
                # Try to extract domain from the first URL
                if urls:
                    from urllib.parse import urlparse
                    domain = urlparse(urls[0]).netloc
                    source_domain = domain.replace(".", "_").replace("-", "_").replace("www_", "")
                else:
                    source_domain = "unknown_source"
            else:
                source_domain = source_domain.replace(".", "_").replace("-", "_").replace("www_", "")
            
            # Get session ID or create one
            session_id = session.get("session_metadata", {}).get("session_id", f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
            
            # Construct GCS path based on new structure
            current_date_path = datetime.now(timezone.utc).strftime("%Y-%m")
            
            # Example: news_data/sources/bbc/2025-07/articles/session_data_bbc_com_uk_001.json
            gcs_object_path = f"{NEWS_DATA_ROOT_PREFIX}sources/{source_domain}/{current_date_path}/{ARTICLES_SUBFOLDER}session_data_{source_domain}_{session_id}.json"
            
            filename = f"session_data_{source_domain}_{session_id}.json"
            local_path = Path("/tmp") / filename

            # Save session data locally
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2, ensure_ascii=False)

            # Upload to GCS
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(gcs_object_path)
            blob.upload_from_filename(str(local_path))
            logger.info(f"Uploaded {filename} to GCS path gs://{GCS_BUCKET_NAME}/{gcs_object_path}")

            # Publish success message
            success_message = {
                "status": "success",
                "gcs_path": f"gs://{GCS_BUCKET_NAME}/{gcs_object_path}",
                "source_domain": source_domain,
                "session_id": session_id,
                "date_path": current_date_path,
                "articles_count": session.get("articles_count", 0),
                "keywords": keywords,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
            
            topic_path = publisher.topic_path(PROJECT_ID, SESSION_DATA_CREATED_TOPIC)
            future = publisher.publish(topic_path, json.dumps(success_message).encode("utf-8"))
            future.result()  # Wait for publish to complete
            logger.info(f"Published success message for {filename}")

    except Exception as e:
        logger.error(f"An error occurred during scraping: {e}", exc_info=True)
        
        # Publish error message to the same topic with error status
        error_message = {
            "status": "error",
            "error": str(e),
            "urls": urls,
            "keywords": keywords,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            topic_path = publisher.topic_path(PROJECT_ID, SESSION_DATA_CREATED_TOPIC)
            future = publisher.publish(topic_path, json.dumps(error_message).encode("utf-8"))
            future.result()
            logger.info("Published error message")
        except Exception as pub_error:
            logger.error(f"Failed to publish error message: {pub_error}")

def scrape_and_store(event, context):
    """
    Background Cloud Function to be triggered by Pub/Sub.
    
    Args:
        event (dict): The Pub/Sub message data.
        context (google.cloud.functions.Context): The Cloud Functions event metadata.
    """
    logger.info(f"Function triggered with event: {event}")
    
    if isinstance(event, dict) and "data" in event:
        try:
            message_data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
            logger.info(f"Decoded message data: {message_data}")
            asyncio.run(_process_scraping_request(message_data))
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
    else:
        logger.error("Invalid Pub/Sub message format")
