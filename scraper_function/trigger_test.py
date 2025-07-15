"""
Test trigger for the scraper function.
This script demonstrates how to trigger the scraping Cloud Function from a local environment.
"""

import json
import base64
import os
from google.cloud import pubsub_v1

# Configuration
PROJECT_ID = "gen-lang-client-0306766464"
TOPIC_ID = "scraping-requests"

def trigger_scraper_function():
    """
    Trigger the scraper function by publishing a message to the Pub/Sub topic.
    """
    # Initialize publisher client
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    
    # Define test scraping request payload
    message_payload = {
        "keywords": ["fenerbahce", "mourinho", "galatasaray"],
        "urls": [
            "https://www.fanatik.com.tr/",
            "https://www.fotomac.com.tr/"
        ],
        "scrape_depth": 1,
        "persist": False,
    }

    print(f"Publishing message to topic: {topic_path}")
    print(f"Message payload: {json.dumps(message_payload, indent=2)}")
    
    # Publish the message
    try:
        # Pub/Sub messages expect bytes, so encode the JSON string
        data = json.dumps(message_payload).encode("utf-8")
        
        # Publish the message
        future = publisher.publish(topic_path, data)
        message_id = future.result()  # This will block until the message is published
        
        print(f"✅ Successfully published message with ID: {message_id}")
        print(f"   Topic: {topic_path}")
        print("   The scraper function should now be triggered!")
        
        return message_id
        
    except Exception as e:
        print(f"❌ Failed to publish message: {e}")
        raise

if __name__ == "__main__":
    print("=== Scraper Function Trigger Test ===")
    print()
    
    # Check if required environment variables are set
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        print("⚠️  Warning: GOOGLE_CLOUD_PROJECT environment variable not set")
        print("   Using default project: gen-lang-client-0306766464")
    
    try:
        print("1. Testing Turkish sources...")
        trigger_scraper_function()
        print()
                
        print("✅ All trigger tests completed successfully!")
        print("Check the Cloud Functions logs to see the execution results.")
        
    except Exception as e:
        print(f"❌ Trigger test failed: {e}")
        exit(1)
