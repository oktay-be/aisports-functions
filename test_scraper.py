"""
Simple journalist tester for the scraper function.
Tests the journalist library with configurable parameters.
"""

import asyncio
import logging
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Configure logging with better formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

# Import journalist
try:
    from journalist import Journalist
    JOURNALIST_AVAILABLE = True
    logger.info("✅ Journalist library imported successfully")
except ImportError as e:
    JOURNALIST_AVAILABLE = False
    Journalist = None
    logger.error(f"❌ Failed to import journalist library: {e}")


async def test_journalist_configurable():
    """
    Test journalist with configurable parameters (similar to cloud function payload).
    """
    if not JOURNALIST_AVAILABLE:
        logger.error("Journalist library not available. Cannot run test.")
        return None
    
    # Test payload similar to cloud function
    test_payload = {
        "keywords": ["fenerbahce", "mourinho", "galatasaray"],
        "urls": [
            "https://www.fanatik.com.tr",
            "https://www.ntvspor.net/"
        ],
        "scrape_depth": 1,
        "persist": True,
        "description": "Turkish sports websites for local football coverage"
    }
    
    try:
        logger.info("=== Testing Configurable Journalist Parameters ===")
        logger.info(f"Test payload: {json.dumps(test_payload, indent=2)}")
        
        # Extract parameters
        urls = test_payload["urls"]
        keywords = test_payload["keywords"]
        scrape_depth = test_payload.get("scrape_depth", 2)
        persist = test_payload.get("persist", True)
        
        # Initialize Journalist with payload parameters
        logger.info(f"Initializing with persist={persist}, scrape_depth={scrape_depth}")
        journalist = Journalist(persist=persist, scrape_depth=scrape_depth)
        
        # Perform scraping
        logger.info("Starting configurable scraping operation...")
        source_sessions = await journalist.read(urls=urls, keywords=keywords)
        
        if source_sessions:
            logger.info(f"✅ Configurable scraping completed. Found {len(source_sessions)} sessions")
            
            # Process and save results
            results_summary = {
                "test_config": test_payload,
                "execution_time": datetime.now(timezone.utc).isoformat(),
                "sessions_found": len(source_sessions),
                "sessions": []
            }
            
            for i, session in enumerate(source_sessions):
                session_summary = {
                    "index": i+1,
                    "source_domain": session.get('source_domain', 'unknown'),
                    "articles_count": session.get('articles_count', 0),
                    "session_id": session.get('session_metadata', {}).get('session_id', 'no_id')
                }
                results_summary["sessions"].append(session_summary)
                logger.info(f"Session {i+1}: {session_summary}")
            
            # Save summary
            summary_file = f"test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(results_summary, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Test summary saved to: {summary_file}")
            
        else:
            logger.warning("⚠️ No sessions returned from configurable test")
            
        return source_sessions
        
    except Exception as e:
        logger.error(f"❌ Configurable test failed: {e}", exc_info=True)
        raise

async def main():
    """
    Main test function following example.py architecture.
    """
    logger.info("🚀 Starting Journalist Library Tests")
    
    if not JOURNALIST_AVAILABLE:
        logger.error("❌ Journalist library not available. Please install journ4list")
        return
    
    try:        
        # Test 2: Configurable parameters
        logger.info("\n" + "="*50)
        config_result = await test_journalist_configurable()
        
        # Summary
        logger.info("\n" + "="*50)
        logger.info("✅ All journalist tests completed successfully!")
        logger.info(f"Configurable test sessions: {len(config_result) if config_result else 0}")
        
    except Exception as e:
        logger.error(f"❌ Journalist tests failed: {e}")
    
    logger.info("🏁 Test completed!")

if __name__ == "__main__":
    # Check if we're in the right directory
    if not Path("scraper_function").exists():
        logger.warning("⚠️ scraper_function directory not found. Make sure you're in the project root.")
    
    # Run the tests
    asyncio.run(main())