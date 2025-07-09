#!/usr/bin/env python3
"""
Test script to verify that the JSON schema fixes work correctly.
This tests the AISummarizer with response_mime_type and response_schema.
"""

import asyncio
import json
import logging
from pathlib import Path
from capabilities.ai_summarizer import AISummarizer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample test session data
test_session_data = {
    "session_metadata": {
        "session_id": "test-20250627-001",
        "timestamp": "2025-06-27T20:00:00Z",
        "collection_duration": "00:05:30"
    },
    "source_domain": "test.example.com", 
    "articles": [
        {
            "id": "test-001",
            "url": "https://test.example.com/article-1",
            "title": "Test Article About Football Transfer",
            "published_time": "2025-06-27T19:00:00Z",
            "description": "A test article about a football player transfer.",
            "content": "This is a test article about a football transfer. The player is moving from Club A to Club B for 50 million euros.",
            "keywords": ["football", "transfer", "club"]
        },
        {
            "id": "test-002", 
            "url": "https://test.example.com/article-2",
            "title": "Basketball Championship Results",
            "published_time": "2025-06-27T18:30:00Z",
            "description": "Results from the basketball championship final.",
            "content": "The basketball championship final ended with Team X beating Team Y 95-82.",
            "keywords": ["basketball", "championship", "results"]
        }
    ]
}

async def test_json_schema_response():
    """Test that AISummarizer returns properly formatted JSON with the new schema enforcement."""
    
    logger.info("Testing AISummarizer with JSON schema enforcement...")
    
    # Initialize AISummarizer
    ai_summarizer = AISummarizer()
    
    if not ai_summarizer.client:
        logger.error("AISummarizer client not initialized. Check your Google Cloud credentials.")
        return False
    
    try:
        # Process the test session data
        logger.info("Processing test session data...")
        result = await ai_summarizer.summarize_and_classify_session_data_object(test_session_data)
        
        # Check if we got a valid result
        if "error" in result:
            logger.error(f"Processing failed with error: {result['error']}")
            if "raw_response" in result:
                logger.error(f"Raw response: {result['raw_response'][:200]}...")
            return False
        
        # Validate the structure
        if "processing_summary" not in result or "processed_articles" not in result:
            logger.error(f"Invalid result structure. Keys: {list(result.keys())}")
            return False
        
        # Check processing summary
        processing_summary = result["processing_summary"]
        if "total_input_articles" not in processing_summary:
            logger.error("Missing total_input_articles in processing_summary")
            return False
        
        # Validate articles
        processed_articles = result["processed_articles"]
        if not isinstance(processed_articles, list):
            logger.error("processed_articles is not a list")
            return False
        
        logger.info(f"✅ Success! Processed {len(processed_articles)} articles")
        logger.info(f"Input articles: {processing_summary.get('total_input_articles', 'unknown')}")
        
        # Show first article as example
        if processed_articles:
            first_article = processed_articles[0]
            logger.info(f"First article title: {first_article.get('title', 'No title')}")
            logger.info(f"Categories: {[cat.get('tag') for cat in first_article.get('categories', [])]}")
        
        # Save result for inspection
        output_file = Path(__file__).parent / "test_schema_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"Result saved to: {output_file}")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed with exception: {e}", exc_info=True)
        return False

async def main():
    """Main test function."""
    logger.info("=" * 60)
    logger.info("Testing JSON Schema Enforcement in AISummarizer")
    logger.info("=" * 60)
    
    success = await test_json_schema_response()
    
    if success:
        logger.info("🎉 Test completed successfully!")
        logger.info("The JSON schema enforcement is working correctly.")
    else:
        logger.error("❌ Test failed!")
        logger.error("There may be issues with the JSON schema enforcement.")
    
    return success

if __name__ == "__main__":
    asyncio.run(main())
