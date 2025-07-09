import os
import json
import base64
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import pubsub_v1, storage
from journalist import Journalist

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Google Cloud clients
publisher = pubsub_v1.PublisherClient()
storage_client = storage.Client()

# Configuration from environment variables
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT')
SESSION_DATA_CREATED_TOPIC = os.getenv('SESSION_DATA_CREATED_TOPIC', 'session-data-created')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'your-session-data-bucket')
NEWS_DATA_ROOT_PREFIX = os.getenv('NEWS_DATA_ROOT_PREFIX', 'news_data/')
ARTICLES_SUBFOLDER = os.getenv('ARTICLES_SUBFOLDER', 'articles/')

async def _process_scraping_request(message_data: dict):
    logger.info(f"Received scraping request: {message_data}")
    urls = message_data.get("urls")
    keywords = message_data.get("keywords")

    if not urls or not keywords:
        logger.error("Missing 'urls' or 'keywords' in the request.")
        return

    try:
        journalist = Journalist()
        source_sessions = await journalist.read(urls=urls, keywords=keywords)

        for session in source_sessions:
            source_domain = session.get("source_domain", "unknown_source").replace(".", "_").replace("-", "_")
            session_id = session.get("session_metadata", {}).get("session_id", "no_session_id")
            
            current_date_path = datetime.now(timezone.utc).strftime("%Y-%m")
            
            gcs_object_path = f"{NEWS_DATA_ROOT_PREFIX}sources/{source_domain}/{current_date_path}/{ARTICLES_SUBFOLDER}session_data_{source_domain}_{session_id}.json"
            
            filename = f"session_data_{source_domain}_{session_id}.json"
            local_path = Path("/tmp") / filename

            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2, ensure_ascii=False)

            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(gcs_object_path)
            blob.upload_from_filename(str(local_path))
            logger.info(f"Uploaded {filename} to GCS path gs://{GCS_BUCKET_NAME}/{gcs_object_path}.")

            success_message = {
                "status": "success",
                "gcs_path": f"gs://{GCS_BUCKET_NAME}/{gcs_object_path}",
                "source_domain": source_domain,
                "session_id": session_id,
                "date_path": current_date_path
            }
            future = publisher.publish(
                publisher.topic_path(PROJECT_ID, SESSION_DATA_CREATED_TOPIC),
                json.dumps(success_message).encode("utf-8")
            )
            future.result()
            logger.info(f"Published success message for {filename}.")

    except Exception as e:
        logger.error(f"An error occurred during scraping: {e}", exc_info=True)

def scrape_and_store(event, context):
    """Background Cloud Function to be triggered by Pub/Sub.
    Args:
        event (dict): The Pub/Sub message data.
        context (google.cloud.functions.Context): The Cloud Functions event metadata.
    """
    if isinstance(event, dict) and "data" in event:
        message_data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
        asyncio.run(_process_scraping_request(message_data))
    else:
        logger.error("Invalid Pub/Sub message format.")


