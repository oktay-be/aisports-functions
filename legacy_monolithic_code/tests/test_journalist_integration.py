"""
Integration tests for journ4list library

Tests the journalist library with Turkish football keywords and Fanatik news source.
This module contains pytest tests for the journ4list library integration.
"""

import asyncio
import logging
import pytest
from journalist import Journalist

# Set up logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_journalist_library_integration():
    """
    Test the journalist library with Turkish football keywords.
    
    This function:
    1. Initializes the Journalist with persist=True
    2. Calls the read method with Fanatik URL and football keywords
    3. Displays the extracted results
    """
    
    # Test parameters
    url = "https://www.fanatik.com.tr/"
    keywords = ["fenerbahce", "galatasaray"]
    
    logger.info("Starting journ4list test...")
    logger.info(f"URL: {url}")
    logger.info(f"Keywords: {keywords}")
    logger.info(f"Persist: True")
    
    try:
        # Initialize Journalist with persistence enabled
        journalist = Journalist(persist=True, scrape_depth=1)
        logger.info("Journalist initialized successfully")        # Extract content
        logger.info("Starting content extraction...")
        result = await journalist.read(
            urls=[url],
            keywords=keywords
        )        # Assert that we got some results
        assert result is not None, "Journalist should return results"
        assert isinstance(result, list), "Result should be a list of session results"
        assert len(result) > 0, "Should have at least one session result"
        
        # Check the first session result
        first_session = result[0]
        assert isinstance(first_session, dict), "Each session result should be a dictionary"
        assert 'articles' in first_session, "Session should contain articles"
        assert first_session['articles_count'] > 0, "Should have scraped some articles"
        
        logger.info("Integration test completed successfully")
        
        return result
        
    except Exception as e:
        logger.error(f"Error during integration test: {e}")
        pytest.fail(f"Integration test failed with error: {e}")


async def standalone_test():
    """
    Standalone test function for manual execution.
    This can be run directly when the file is executed as a script.
    """
    return await test_journalist_library_integration()


if __name__ == "__main__":
    asyncio.run(standalone_test())
