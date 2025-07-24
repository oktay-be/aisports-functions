import os
import json
import base64
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import pubsub_v1, storage
try:
    from journalist import Journalist
    JOURNALIST_AVAILABLE = True
except ImportError:
    JOURNALIST_AVAILABLE = False
    Journalist = None

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
ARTICLES_SUBFOLDER = os.getenv('ARTICLES_SUBFOLDER', 'articles/')
# JOURNALIST_LOG_LEVEL already defined above for logging configuration

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
        
        journalist = Journalist(persist=persist, scrape_depth=scrape_depth)
        
        # Start timing the scraping operation
        start_time = datetime.now(timezone.utc)
        logger.info(f"Scraping started at: {start_time.isoformat()}")
        
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
        
        # List /tmp directory contents again
        tmp_contents_after = list(Path("/tmp").iterdir())
        logger.info(f"/tmp contents after: {[str(p) for p in tmp_contents_after]}")

        # Log elapsed time after scraping
        elapsed_time = datetime.now(timezone.utc) - start_time
        logger.info(f"Scraping operation completed in: {elapsed_time.total_seconds():.2f} seconds")

        # # Log working directory and filesystem state after scraping
        # current_dir = os.getcwd()
        # logger.info(f"Current working directory: {current_dir}")
        
        # List contents of /tmp/.journalist_workspace directory
        try:
            journalist_workspace = Path("/tmp/.journalist_workspace")
            if journalist_workspace.exists():
                workspace_contents = list(journalist_workspace.iterdir())
                logger.info(f"/tmp/.journalist_workspace contents: {[str(p) for p in workspace_contents]}")
            else:
                logger.info("/tmp/.journalist_workspace does not exist")
        except Exception as e:
            logger.error(f"Error listing /tmp/.journalist_workspace contents: {e}")
           

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

        # Process each session
        for i, session in enumerate(source_sessions):
            logger.info(f"Processing session {i+1}/{len(source_sessions)}")
            
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
            
            # Log session details
            articles_count = session.get("articles_count", 0)
            logger.info(f"Session {i+1} details:")
            logger.info(f"  - Source domain: {source_domain}")
            logger.info(f"  - Session ID: {session_id}")
            logger.info(f"  - Articles count: {articles_count}")
            
            # Construct GCS path based on new structure
            current_date_path = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            # Example: news_data/sources/bbc/2025-07-19/articles/session_data_bbc_com_uk_001.json
            gcs_object_path = f"{NEWS_DATA_ROOT_PREFIX}sources/{source_domain}/{current_date_path}/{ARTICLES_SUBFOLDER}session_data_{source_domain}_{session_id}.json"
              # When persist=True, journalist saves the file. Get the path from the session metadata.
            local_path_str = session.get("session_metadata", {}).get("file_path")
            if not local_path_str:
                logger.error(f"Could not find file_path in session metadata for session {session_id}")
                # Log available metadata keys for debugging
                session_metadata = session.get("session_metadata", {})
                logger.info(f"Available session metadata keys: {list(session_metadata.keys())}")
                continue  # Skip to the next session

            local_path = Path(local_path_str)
            if not local_path.exists():
                logger.error(f"File provided by journalist does not exist: {local_path}")
                continue # Skip to the next session

            if ENVIRONMENT == 'local':
                # In local environment, just keep the file and log its location
                logger.info(f"Local environment: File saved at {local_path}")
                logger.info(f"File size: {local_path.stat().st_size} bytes")
                
                # Log success message (without publishing)
                success_message = {
                    "status": "success",
                    "local_path": str(local_path),
                    "source_domain": source_domain,
                    "session_id": session_id,
                    "date_path": current_date_path,
                    "articles_count": articles_count,
                    "keywords": keywords,
                    "scrape_depth": scrape_depth,
                    "persist": persist,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }
                logger.info(f"Local processing success: {json.dumps(success_message, indent=2)}")
                
            else:
                # Cloud environment: Upload to GCS and publish message
                logger.info(f"Uploading file from {local_path} to GCS: gs://{GCS_BUCKET_NAME}/{gcs_object_path}")
                bucket = storage_client.bucket(GCS_BUCKET_NAME)
                blob = bucket.blob(gcs_object_path)
                blob.upload_from_filename(str(local_path))
                logger.info(f"Successfully uploaded {local_path.name} to GCS")
                logger.info(f"File persisted at: {local_path}")
                
                # Publish success message
                success_message = {
                    "status": "success",
                    "gcs_path": f"gs://{GCS_BUCKET_NAME}/{gcs_object_path}",
                    "source_domain": source_domain,
                    "session_id": session_id,
                    "date_path": current_date_path,
                    "articles_count": articles_count,
                    "keywords": keywords,
                    "scrape_depth": scrape_depth,
                    "persist": persist,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }
                
                logger.info(f"Publishing success message for session {session_id}")
                topic_path = publisher.topic_path(PROJECT_ID, SESSION_DATA_CREATED_TOPIC)
                future = publisher.publish(topic_path, json.dumps(success_message).encode("utf-8"))
                future.result()  # Wait for publish to complete
                logger.info(f"Successfully published message for {local_path.name}")

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
    Get test data similar to what's defined in trigger_test.py
    """
    try:
        # Try to import test data from trigger_test.py
        from trigger_test import get_test_message_payload
        test_data = get_test_message_payload()
        # Override persist to True for local testing to see file creation
        test_data["persist"] = True
        return test_data
    except ImportError:
        # Fallback test data if trigger_test.py is not available
        logger.warning("Could not import trigger_test.py, using fallback test data")
        return {
            "keywords": ["fenerbahce", "mourinho", "galatasaray"],
            "urls": [
                "https://www.fanatik.com.tr",
                "https://www.ntvspor.net/"
            ],
            "scrape_depth": 1,
            "persist": True,  # Enable persist for local testing to see file creation
            "log_level": "INFO"
        }

async def main_local():
    """
    Main function for local execution
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
