"""
Test file for the full collection pipeline using the orchestrator's run_full_collection method.
Tests the complete workflow and session-related functionality.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from integrations.collection_orchestrator import CollectionOrchestrator

# Import journalist for direct usage
try:
    from journalist import Journalist
    JOURNALIST_AVAILABLE = True
except ImportError:
    JOURNALIST_AVAILABLE = False
    Journalist = None

# Configure logging with better formatting
import sys
import os

# Simple console width fix for Windows
if os.name == 'nt':  # Windows
    try:
        # Try to set a reasonable console size
        os.system('mode con: cols=120 lines=40 >nul 2>&1')
        os.system('chcp 65001 >nul 2>&1')  # Set UTF-8 encoding
    except:
        pass

# Configure simple logging to avoid formatting issues
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',  # Simplified format
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

async def test_run_full_collection():
    """
    Test the full collection pipeline using run_full_collection method
    and session-related functionality.
    """
      # Configuration
    google_api_key = os.getenv('GOOGLE_API_KEY')
    newsapi_key = os.getenv('NEWSAPI_KEY')  # Optional, can be None
    
    if not google_api_key:
        logger.error("GOOGLE_API_KEY environment variable is required")
        return
    
    # Simple test keywords
    test_keywords = ["fenerbahce", "mourinho"]
    
    try:
        logger.info("=== Testing Full Collection Pipeline ===")
          # Initialize orchestrator
        orchestrator = CollectionOrchestrator(
            google_api_key=google_api_key,
            newsapi_key=newsapi_key
        )
        
        # Initialize services
        logger.info("Initializing orchestrator services...")
        await orchestrator.initialize()
          # Run the full collection workflow
        logger.info("Starting run_full_collection...")
        result = await orchestrator.run_full_collection(keywords=test_keywords)
        
        logger.info(f"✅ run_full_collection completed: {result}")
        
        # Session-related checks
        if result and 'run_id' in result:
            run_id = result['run_id']
            logger.info(f"Checking session status for run_id: {run_id}")
            
            # Get collection status (session-related)
            status = await orchestrator.get_collection_status(run_id)
            if status:
                logger.info(f"✅ Session status: {status.get('status')}")
                logger.info(f"  Created at: {status.get('created_at')}")
                logger.info(f"  Metadata: {status.get('metadata', {})}")
            else:
                logger.warning("⚠️ No session status found")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}", exc_info=True)
        raise
    
    finally:
        # Cleanup
        logger.info("Cleaning up orchestrator...")
        await orchestrator.cleanup()

async def main():
    """
    Main test function.
    """
    
    logger.info("🚀 Starting Collection Orchestrator Tests - Full Collection Pipeline")
    
    try:
        result = await test_run_full_collection()
        logger.info(f"✅ Full collection test completed: {result}")
    except Exception as e:
        logger.error(f"❌ Full collection test failed: {e}")
    
    logger.info("🏁 Test completed!")

if __name__ == "__main__":
    # Check required environment variables
    required_env_vars = ['GOOGLE_API_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        logger.error("Please set GOOGLE_API_KEY environment variable")
        sys.exit(1)
    
    # Set default MongoDB URI if not provided
    if not os.getenv('MONGODB_URI'):
        os.environ['MONGODB_URI'] = 'mongodb://localhost:27017'
        logger.info("Using default MongoDB URI: mongodb://localhost:27017")
      # Run the test
    asyncio.run(main())
