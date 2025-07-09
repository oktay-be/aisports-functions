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
        "urls": [
            "https://www.fanatik.com.tr/",
            "https://www.fotomac.com.tr/"
        ],
        "keywords": [
            "fenerbahce",
            "galatasaray",
            "mourinho"
        ]
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

def trigger_scraper_with_eu_sources():
    """
    Trigger the scraper function with EU sources.
    """
    # Initialize publisher client
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    
    # Define EU sources scraping request payload
    message_payload = {
        "urls": [
            "https://www.bbc.com/sport/football",
            "https://www.goal.com/en"
        ],
        "keywords": [
            "football",
            "transfer",
            "premier league"
        ]
    }
    
    print(f"Publishing EU sources message to topic: {topic_path}")
    print(f"Message payload: {json.dumps(message_payload, indent=2)}")
    
    # Publish the message
    try:
        # Pub/Sub messages expect bytes, so encode the JSON string
        data = json.dumps(message_payload).encode("utf-8")
        
        # Publish the message
        future = publisher.publish(topic_path, data)
        message_id = future.result()  # This will block until the message is published
        
        print(f"✅ Successfully published EU sources message with ID: {message_id}")
        print(f"   Topic: {topic_path}")
        print("   The scraper function should now be triggered!")
        
        return message_id
        
    except Exception as e:
        print(f"❌ Failed to publish EU sources message: {e}")
        raise

def trigger_single_source_test():
    """
    Trigger the scraper function with a single source for testing.
    """
    # Initialize publisher client
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    
    # Define single source test payload
    message_payload = {
        "urls": [
            "https://www.fanatik.com.tr/"
        ],
        "keywords": [
            "fenerbahce"
        ]
    }
    
    print(f"Publishing single source test message to topic: {topic_path}")
    print(f"Message payload: {json.dumps(message_payload, indent=2)}")
    
    # Publish the message
    try:
        # Pub/Sub messages expect bytes, so encode the JSON string
        data = json.dumps(message_payload).encode("utf-8")
        
        # Publish the message
        future = publisher.publish(topic_path, data)
        message_id = future.result()  # This will block until the message is published
        
        print(f"✅ Successfully published single source test message with ID: {message_id}")
        print(f"   Topic: {topic_path}")
        print("   The scraper function should now be triggered!")
        
        return message_id
        
    except Exception as e:
        print(f"❌ Failed to publish single source test message: {e}")
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
        
        print("2. Testing EU sources...")
        trigger_scraper_with_eu_sources()
        print()
        
        print("3. Testing single source...")
        trigger_single_source_test()
        print()
        
        print("✅ All trigger tests completed successfully!")
        print("Check the Cloud Functions logs to see the execution results.")
        
    except Exception as e:
        print(f"❌ Trigger test failed: {e}")
        exit(1)
