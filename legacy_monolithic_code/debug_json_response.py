#!/usr/bin/env python3
"""
Debug script to help identify JSON parsing issues with Google GenAI responses.
This script will test both with and without response_schema to see the differences.
"""

import asyncio
import json
import logging
from pathlib import Path
from capabilities.ai_summarizer import AISummarizer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple test data
test_data = {
    "source_domain": "test.example.com",
    "articles": [
        {
            "id": "test-1",
            "url": "https://test.example.com/test",
            "title": "Test Article",
            "content": "This is a test article for debugging."
        }
    ],
    "session_metadata": {
        "session_id": "debug-test"
    }
}

async def test_without_schema():
    """Test without response_schema to see raw response."""
    logger.info("=== Testing WITHOUT response_schema ===")
    
    summarizer = AISummarizer()
    if not summarizer.client:
        logger.error("Cannot initialize AISummarizer")
        return None
    
    try:
        # Create a simple prompt
        simple_prompt = """
Please return the following data as valid JSON:
{
    "status": "success",
    "message": "This is a test response"
}
"""
        
        # Send without schema
        response = await asyncio.to_thread(
            summarizer.client.models.generate_content,
            model=summarizer.model_name,
            contents=[simple_prompt],
            config={
                "response_mime_type": "application/json"
            }
        )
        
        logger.info(f"Raw response text: '{response.text}'")
        logger.info(f"Response length: {len(response.text) if response.text else 0}")
        
        if response.text:
            # Show first 200 characters
            preview = response.text[:200] + "..." if len(response.text) > 200 else response.text
            logger.info(f"Response preview: {preview}")
            
            # Try to parse
            try:
                parsed = json.loads(response.text)
                logger.info(f"Successfully parsed: {parsed}")
                return response.text
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                logger.error(f"Error at position {e.pos}: '{response.text[max(0, e.pos-10):e.pos+10]}'")
                return response.text
        else:
            logger.error("No response text received")
            return None
            
    except Exception as e:
        logger.error(f"Error in test: {e}")
        return None

async def test_with_schema():
    """Test with response_schema to see if it helps."""
    logger.info("=== Testing WITH response_schema ===")
    
    summarizer = AISummarizer()
    if not summarizer.client:
        logger.error("Cannot initialize AISummarizer")
        return None
    
    try:
        # Create a simple prompt
        simple_prompt = """
Please return the following data as valid JSON:
{
    "status": "success", 
    "message": "This is a test response"
}
"""
        
        # Define simple schema
        simple_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "message": {"type": "string"}
            },
            "required": ["status", "message"]
        }
        
        # Send with schema
        response = await asyncio.to_thread(
            summarizer.client.models.generate_content,
            model=summarizer.model_name,
            contents=[simple_prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": simple_schema
            }
        )
        
        logger.info(f"Raw response text: '{response.text}'")
        logger.info(f"Response length: {len(response.text) if response.text else 0}")
        
        if response.text:
            # Show first 200 characters
            preview = response.text[:200] + "..." if len(response.text) > 200 else response.text
            logger.info(f"Response preview: {preview}")
            
            # Try to parse
            try:
                parsed = json.loads(response.text)
                logger.info(f"Successfully parsed: {parsed}")
                return response.text
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                logger.error(f"Error at position {e.pos}: '{response.text[max(0, e.pos-10):e.pos+10]}'")
                return response.text
        else:
            logger.error("No response text received")
            return None
            
    except Exception as e:
        logger.error(f"Error in test: {e}")
        return None

async def test_your_actual_method():
    """Test using your actual summarize method."""
    logger.info("=== Testing YOUR actual method ===")
    
    summarizer = AISummarizer()
    if not summarizer.client:
        logger.error("Cannot initialize AISummarizer")
        return None
    
    try:
        result = await summarizer.summarize_and_classify_session_data_object(test_data)
        
        if "error" in result:
            logger.error(f"Method returned error: {result['error']}")
            if "raw_response" in result:
                raw = result["raw_response"]
                logger.error(f"Raw response: '{raw[:200]}...' (length: {len(raw)})")
                
                # Check if it's empty or whitespace
                if not raw or raw.isspace():
                    logger.error("Raw response is empty or only whitespace!")
                
                # Check for invisible characters
                logger.error(f"Raw response bytes: {raw[:50].encode('utf-8')}")
        else:
            logger.info("Method succeeded!")
            logger.info(f"Processed {len(result.get('processed_articles', []))} articles")
            
        return result
        
    except Exception as e:
        logger.error(f"Error in your method: {e}")
        return None

async def main():
    """Run all tests."""
    logger.info("🔍 Debugging JSON Response Issues")
    logger.info("=" * 50)
    
    # Test 1: Without schema
    result1 = await test_without_schema()
    print()
    
    # Test 2: With schema  
    result2 = await test_with_schema()
    print()
    
    # Test 3: Your actual method
    result3 = await test_your_actual_method()
    print()
    
    # Compare results
    logger.info("=== COMPARISON ===")
    logger.info(f"Without schema: {'Success' if result1 and not result1.startswith('Error') else 'Failed'}")
    logger.info(f"With schema: {'Success' if result2 and not result2.startswith('Error') else 'Failed'}")
    logger.info(f"Your method: {'Success' if result3 and 'error' not in result3 else 'Failed'}")

if __name__ == "__main__":
    asyncio.run(main())
