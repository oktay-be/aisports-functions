"""
Test trigger for the batch builder function.
This script demonstrates how to trigger the batch builder by publishing a mock batch_success message.
"""

import json
import os
from datetime import datetime, timezone
from google.cloud import pubsub_v1
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
PROJECT_ID = "gen-lang-client-0306766464"
TOPIC_ID = os.getenv('SESSION_DATA_CREATED_TOPIC', 'session-data-created')
GCS_BUCKET_NAME = "aisports-news-data"

def get_test_batch_message():
    """
    Get a test batch_success message similar to what the scraper function publishes.
    """
    return {
        "status": "batch_success",
        "batch_size": 3,
        "success_messages": [
            {
                "status": "success",
                "gcs_path": f"gs://{GCS_BUCKET_NAME}/news_data/sources/fanatik_com_tr/2025-07/articles/session_data_fanatik_com_tr_20250726_001.json",
                "source_domain": "fanatik_com_tr",
                "session_id": "20250726_001",
                "date_path": "2025-07",
                "articles_count": 15,
                "keywords": ["fenerbahce", "galatasaray", "mourinho"],
                "scrape_depth": 1,
                "persist": True,
                "processed_at": datetime.now(timezone.utc).isoformat()
            },
            {
                "status": "success", 
                "gcs_path": f"gs://{GCS_BUCKET_NAME}/news_data/sources/fotomac_com_tr/2025-07/articles/session_data_fotomac_com_tr_20250726_002.json",
                "source_domain": "fotomac_com_tr",
                "session_id": "20250726_002",
                "date_path": "2025-07",
                "articles_count": 12,
                "keywords": ["fenerbahce", "galatasaray", "mourinho"],
                "scrape_depth": 1,
                "persist": True,
                "processed_at": datetime.now(timezone.utc).isoformat()
            },
            {
                "status": "success",
                "gcs_path": f"gs://{GCS_BUCKET_NAME}/news_data/sources/ntvspor_net/2025-07/articles/session_data_ntvspor_net_20250726_003.json",
                "source_domain": "ntvspor_net",
                "session_id": "20250726_003", 
                "date_path": "2025-07",
                "articles_count": 18,
                "keywords": ["fenerbahce", "galatasaray", "mourinho"],
                "scrape_depth": 1,
                "persist": True,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
        ],
        "batch_processed_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": 45
    }

def trigger_batch_builder():
    """
    Trigger the batch builder function by publishing a batch_success message to the session-data-created topic.
    """
    # Initialize publisher client
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    
    # Get test message payload
    message_payload = get_test_batch_message()

    print(f"Publishing batch_success message to topic: {topic_path}")
    print(f"Message payload summary:")
    print(f"  - Status: {message_payload['status']}")
    print(f"  - Batch size: {message_payload['batch_size']}")
    print(f"  - Total articles: {message_payload['total_articles']}")
    print(f"  - GCS files:")
    for i, msg in enumerate(message_payload['success_messages'], 1):
        print(f"    {i}. {msg['source_domain']} ({msg['articles_count']} articles)")
        print(f"       {msg['gcs_path']}")
    
    # Publish the message
    try:
        # Pub/Sub messages expect bytes, so encode the JSON string
        data = json.dumps(message_payload).encode("utf-8")
        
        # Publish the message
        future = publisher.publish(topic_path, data)
        message_id = future.result()  # This will block until the message is published
        
        print(f"\n✅ Successfully published message with ID: {message_id}")
        print(f"   Topic: {topic_path}")
        print("   The batch builder function should now be triggered!")
        
        return message_id
        
    except Exception as e:
        print(f"❌ Failed to publish message: {e}")
        raise

if __name__ == "__main__":
    print("=== Batch Builder Function Trigger Test ===")
    print()
    
    # Check if required environment variables are set
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        print("⚠️  Warning: GOOGLE_CLOUD_PROJECT environment variable not set")
        print("   Using default project: gen-lang-client-0306766464")
    
    try:
        print("Triggering batch builder with mock scraper batch_success message...")
        trigger_batch_builder()
        print()
        
        print("✅ Batch builder trigger test completed successfully!")
        print("Check the Cloud Functions logs to see the execution results.")
        print()
        print("Expected behavior:")
        print("1. Batch builder receives the batch_success message")
        print("2. Extracts 3 GCS file paths from success_messages")  
        print("3. Creates batch request JSONL file")
        print("4. Uploads request to GCS batch_processing folder")
        print("5. Submits batch job to Vertex AI")
        print("6. Saves metadata to GCS")
        print("7. Publishes batch_job_created message")
        
    except Exception as e:
        print(f"❌ Batch builder trigger test failed: {e}")
        exit(1)
