"""
Test file for AI Summarizer and AI Aggregator functionality using existing session data files.
Tests the summarize_and_classify_session_data_object method with real session data.

NOTE: This test now uses Vertex AI with Application Default Credentials (ADC) for all AI adapters.
Both AISummarizer and AIAggregator automatically load credentials from GOOGLE_APPLICATION_CREDENTIALS
environment variable defined in .env file.

The test processes sessions sequentially (one at a time) to avoid Vertex AI rate limits.
This ensures reliable processing without hitting concurrent request limits.

Required environment variables:
- GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464
- GOOGLE_APPLICATION_CREDENTIALS=./gen-lang-client-0306766464-13fc9c9298ba.json
- GOOGLE_CLOUD_LOCATION=global

This test validates:
1. Vertex AI authentication for both AISummarizer and AIAggregator
2. Session data processing with the new SESSION_DATA_MODEL
3. End-to-end AI summarization workflow using real scraped data
4. Sequential processing to avoid API rate limits
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables for Vertex AI configuration
from dotenv import load_dotenv
load_dotenv()

from capabilities.ai_summarizer import AISummarizer
from api.models import SESSION_DATA_MODEL

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
    handlers=[logging.StreamHandler(sys.stdout)],
    encoding='utf-8'  # Force UTF-8 encoding to handle special characters
)

logger = logging.getLogger(__name__)

def load_session_data_files(session_dir: str) -> List[Dict[str, Any]]:
    """
    Load all session data files from the specified directory and return as a list
    that mimics the tr_sessions format.
    
    Extracts only the fields defined in SESSION_DATA_MODEL:
    - source_domain: Domain of the source website
    - source_url: URL of the source website  
    - articles: List of scraped articles
    - articles_count: Number of articles
    - session_metadata: Metadata about the scraping session
    
    Args:
        session_dir: Path to the journalist session directory
        
    Returns:
        List of session data objects following SESSION_DATA_MODEL structure
    """
    session_path = Path(session_dir)
    if not session_path.exists():
        logger.error(f"Session directory does not exist: {session_dir}")
        return []
    
    # Find all session data files
    session_files = list(session_path.glob("session_data_*.json"))
    logger.info(f"Found {len(session_files)} session data files")
    
    tr_sessions = []
    
    for session_file in session_files:
        try:
            logger.info(f"Loading session data from: {session_file.name}")
            
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # Extract only SESSION_DATA_MODEL fields directly
            filtered_session_data = {
                "source_domain": session_data.get("source_domain"),
                "source_url": session_data.get("source_url"),
                "articles": session_data.get("articles", []),
                "articles_count": session_data.get("articles_count", 0),
                "session_metadata": session_data.get("session_metadata", {})
            }
            
            source_domain = filtered_session_data["source_domain"]
            articles_count = filtered_session_data["articles_count"]
            logger.info(f"  - {source_domain}: {articles_count} articles")
            
            tr_sessions.append(filtered_session_data)
            
        except Exception as e:
            logger.error(f"Failed to load {session_file}: {e}")
            continue
    
    return tr_sessions

async def test_vertex_ai_connection():
    """
    Test Vertex AI connection for both AI adapters before running the full test.
    Returns True if connection is successful, False otherwise.
    """
    logger.info("🔍 Testing Vertex AI connection for all AI adapters...")
    
    try:
        # Test AISummarizer
        logger.info("  - Testing AISummarizer...")
        summarizer = AISummarizer()
        
        if not summarizer.client:
            logger.error("❌ Failed to initialize AISummarizer with Vertex AI")
            return False
        
        logger.info("  ✅ AISummarizer Vertex AI client initialized successfully")
        
        # Test AIAggregator
        logger.info("  - Testing AIAggregator...")
        from capabilities.ai_aggregator import AIAggregator
        aggregator = AIAggregator()
        
        if not aggregator.client:
            logger.error("❌ Failed to initialize AIAggregator with Vertex AI")
            return False
        
        logger.info("  ✅ AIAggregator Vertex AI client initialized successfully")
        logger.info("✅ All AI adapters ready with Vertex AI - can proceed with full test")
        return True
            
    except Exception as e:
        logger.error(f"❌ Error testing Vertex AI: {e}")
        return False

async def test_ai_summarizer_with_session_data():
    """
    Test the AI summarizer functionality using existing session data files.
    Uses Vertex AI with ADC (Application Default Credentials) instead of API key.
    """
    # Configuration - Check Vertex AI environment variables
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT environment variable is required for Vertex AI")
        logger.error("Set it in your .env file: GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464")
        return
    
    if not credentials_path:
        logger.error("GOOGLE_APPLICATION_CREDENTIALS environment variable is required for Vertex AI")
        logger.error("Set it in your .env file: GOOGLE_APPLICATION_CREDENTIALS=./gen-lang-client-0306766464-13fc9c9298ba.json")
        return
    
    logger.info(f"Using Vertex AI with project: {project_id}")
    logger.info(f"Using credentials file: {credentials_path}")
    
    # Pre-test: Verify Vertex AI connection
    logger.info("=" * 60)
    vertex_ai_working = await test_vertex_ai_connection()
    logger.info("=" * 60)
    
    if not vertex_ai_working:
        logger.error("FAIL: Vertex AI connection test failed. Cannot proceed with full test.")
        logger.error("   Check your .env file and service account credentials.")
        return None
    
    # Load session data files
    session_dir = ".journalist_workspace/20250626_190323_694649"
    tr_sessions = load_session_data_files(session_dir)
    
    if not tr_sessions:
        logger.error("No session data loaded, exiting test")
        return
    
    logger.info(f"Loaded {len(tr_sessions)} session data objects for testing")
    
    # Validate session data structure (SESSION_DATA_MODEL compliance)
    logger.info("🔍 Validating session data structure...")
    for i, session in enumerate(tr_sessions):
        required_fields = ["source_domain", "source_url", "articles", "articles_count", "session_metadata"]
        for field in required_fields:
            if field not in session:
                logger.warning(f"  Session {i+1} missing required field: {field}")
            else:
                logger.info(f"  ✅ Session {i+1} ({session['source_domain']}): {len(session.get('articles', []))} articles")      # Test AI Summarizer directly with Vertex AI
    logger.info("Testing AI summarization directly with session data...")
    
    # Initialize AISummarizer directly (no orchestrator needed)
    ai_summarizer = AISummarizer()
    
    if not ai_summarizer.client:
        logger.error("Failed to initialize AISummarizer. Cannot proceed with test.")
        return None
    
    # Process sessions sequentially to avoid rate limits
    logger.info(f"🚀 Starting sequential processing of {len(tr_sessions)} sessions...")
    logger.info("Note: Using sequential processing to avoid Vertex AI rate limits")
    start_time = asyncio.get_event_loop().time()
    
    processed_results = []
    
    for i, session_data in enumerate(tr_sessions):
        source_domain = session_data.get('source_domain', f'session_{i}')
        articles_count = len(session_data.get('articles', []))
        
        # Log session start
        logger.info(f"📝 Processing session {i+1}/{len(tr_sessions)}: {source_domain} ({articles_count} articles)")
        session_start_time = asyncio.get_event_loop().time()
        
        try:
            # Process session without timeout wrapper (let Vertex AI handle its own timeouts)
            result = await ai_summarizer.summarize_and_classify_session_data_object(session_data)
            
            session_end_time = asyncio.get_event_loop().time()
            session_duration = session_end_time - session_start_time
            
            if result.get("error"):
                logger.error(f"AI processing failed for {source_domain} after {session_duration:.1f}s: {result['error']}")
            else:
                processed_articles = len(result.get('processed_articles', []))
                logger.info(f"✅ Successfully processed {source_domain} after {session_duration:.1f}s: {processed_articles} articles processed")
                processed_results.append({
                    'source_domain': source_domain,
                    'result': result,
                    'session_index': i
                })
                
        except Exception as e:
            session_end_time = asyncio.get_event_loop().time()
            session_duration = session_end_time - session_start_time
            logger.error(f"❌ Exception processing {source_domain} after {session_duration:.1f}s: {str(e)}", exc_info=True)
            continue
        
        # Add 1-minute delay between sessions to avoid rate limiting (except for the last session)
        if i < len(tr_sessions) - 1:
            logger.info(f"⏳ Waiting 60 seconds before processing next session ({i+2}/{len(tr_sessions)})...")
            await asyncio.sleep(60)
    
    end_time = asyncio.get_event_loop().time()
    total_duration = end_time - start_time
    
    # Log final results
    logger.info(f"Sequential processing completed after {total_duration:.1f}s total")
    logger.info(f"Successfully processed {len(processed_results)} out of {len(tr_sessions)} sessions")
    
    for processed in processed_results:
        source_domain = processed['source_domain']
        result = processed['result']
        processing_summary = result.get('processing_summary', {})
        articles_processed = processing_summary.get('articles_after_cleaning', 0)
        logger.info(f"  - Session {processed['session_index']+1}: {source_domain} -> {articles_processed} articles processed")
    
    logger.info("✅ AI summarizer test completed successfully!")
    return processed_results

async def main():
    """Main function to run the test."""
    try:
        logger.info("🧪 Starting AI Summarizer Test with Session Data")
        logger.info("=" * 60)
        
        result = await test_ai_summarizer_with_session_data()
        
        logger.info("=" * 60)
        logger.info("🏁 Test completed!")
        
    except Exception as e:
        logger.error(f"FAIL: Test failed: {e}")
        
if __name__ == "__main__":
    asyncio.run(main())
