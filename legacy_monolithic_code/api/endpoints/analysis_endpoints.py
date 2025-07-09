"""
Analysis endpoints - AI analysis operations separated from scraping.
These endpoints handle AI processing of both scraped data and API-fetched news.
"""

import asyncio
import logging
from quart import Blueprint, request, jsonify, current_app
from typing import Dict, Any

# Import AI capabilities
from capabilities.ai_summarizer import AISummarizer
from capabilities.services.scraping_service import ScrapingService

logger = logging.getLogger(__name__)
analysis_blueprint = Blueprint('analysis', __name__)

@analysis_blueprint.route('/process_scraped_data', methods=['POST'])
async def analyze_scraped_data():
    """
    Analyze scraped data using AI (completely separated from scraping process).
    Supports both persist scenarios (direct data or file path).
    
    POST Body - Option 1 (persist=false):
    {
        "session_data": { ... journ4list session data ... },
        "use_claude4": true
    }
    
    POST Body - Option 2 (persist=true):
    {
        "session_file_path": "/path/to/session_data.json",
        "use_claude4": true
    }
    
    POST Body - Option 3 (convenience):
    {
        "use_latest_session": true,
        "use_claude4": true
    }
    """
    try:
        data = request.get_json() or {}
        
        # Initialize AI summarizer
        google_api_key = current_app.config.get('GOOGLE_API_KEY')
        if not google_api_key:
            return jsonify({"error": "Google API key not configured"}), 500
            
        ai_summarizer = AISummarizer(google_api_key=google_api_key)
        
        session_data = None
        session_source = None
        
        # Option 1: Direct session data (persist=false scenario)
        if 'session_data' in data:
            session_data = data['session_data']
            session_source = "direct_data"
            logger.info("Using direct session data for analysis")
            
        # Option 2: Session file path (persist=true scenario)
        elif 'session_file_path' in data:
            scraping_service = ScrapingService()
            session_data = scraping_service.load_session_data(data['session_file_path'])
            session_source = f"file: {data['session_file_path']}"
            logger.info(f"Loading session data from file: {data['session_file_path']}")
            
        # Option 3: Latest session (convenience)
        elif data.get('use_latest_session', False):
            scraping_service = ScrapingService()
            latest_path = scraping_service.find_latest_session()
            if latest_path:
                session_data = scraping_service.load_session_data(latest_path)
                session_source = f"latest: {latest_path}"
                logger.info(f"Using latest session: {latest_path}")
            else:
                return jsonify({"error": "No latest session found"}), 404
        
        if not session_data:
            return jsonify({"error": "No session data provided or found"}), 400
        
        # Validate session data structure
        if not isinstance(session_data, dict) or 'articles' not in session_data:
            return jsonify({"error": "Invalid session data format"}), 400
        
        # Run AI analysis
        use_claude4 = data.get('use_claude4', True)
        
        logger.info(f"Starting AI analysis: {len(session_data.get('articles', []))} articles, use_claude4: {use_claude4}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            if session_source.startswith("file:"):
                # Use persist=true scenario
                result = loop.run_until_complete(
                    ai_summarizer.process_news_with_claude4_prompt(
                        session_file_path=session_source.replace("file: ", ""),
                        use_claude4=use_claude4
                    )
                )
            else:
                # Use persist=false scenario
                result = loop.run_until_complete(
                    ai_summarizer.process_news_with_claude4_prompt(
                        session_data=session_data,
                        use_claude4=use_claude4
                    )
                )
        finally:
            loop.close()
        
        logger.info(f"AI analysis completed. Source: {session_source}, "
                   f"Articles processed: {len(result.get('processed_articles', []))}")
        
        return jsonify({
            "analysis_result": result,
            "session_source": session_source,
            "use_claude4": use_claude4,
            "input_articles": len(session_data.get('articles', [])),
            "processed_articles": len(result.get('processed_articles', []))
        }), 200
        
    except Exception as e:
        logger.error(f"Error in analysis endpoint: {e}", exc_info=True)
        return jsonify({"error": f"Analysis error: {str(e)}"}), 500

@analysis_blueprint.route('/auto_process', methods=['POST'])
async def auto_process_latest():
    """
    Convenience endpoint: automatically find latest session and process it.
    
    POST Body:
    {
        "use_claude4": true  // optional, default true
    }
    """
    try:
        data = request.get_json() or {}
        use_claude4 = data.get('use_claude4', True)
        
        # Initialize services
        google_api_key = current_app.config.get('GOOGLE_API_KEY')
        if not google_api_key:
            return jsonify({"error": "Google API key not configured"}), 500
            
        ai_summarizer = AISummarizer(google_api_key=google_api_key)
        
        # Use the convenience method
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                ai_summarizer.process_latest_journ4list_session(use_claude4=use_claude4)
            )
        finally:
            loop.close()
        
        if "error" in result:
            return jsonify(result), 404
        
        return jsonify({
            "analysis_result": result,
            "auto_processed": True,
            "use_claude4": use_claude4
        }), 200
        
    except Exception as e:
        logger.error(f"Error in auto process endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@analysis_blueprint.route('/test_ai', methods=['POST'])
async def test_ai_connection():
    """
    Test AI connection and capability.
    
    POST Body:
    {
        "test_data": "optional test text"
    }
    """
    try:
        data = request.get_json() or {}
        
        # Initialize AI summarizer
        google_api_key = current_app.config.get('GOOGLE_API_KEY')
        if not google_api_key:
            return jsonify({"error": "Google API key not configured"}), 500
            
        ai_summarizer = AISummarizer(google_api_key=google_api_key)
        
        if not ai_summarizer.model:
            return jsonify({"error": "AI model not initialized"}), 500
        
        # Test with sample data
        test_text = data.get('test_data', 'Fenerbahçe futbol takımı transfer haberleri')
        
        # Create minimal test session data
        test_session_data = {
            "articles": [
                {
                    "title": "Test Article",
                    "body": test_text,
                    "url": "https://test.example.com",
                    "published_at": "2025-06-21T10:00:00Z",
                    "source": "test_source"
                }
            ],
            "session_metadata": {
                "session_id": "test_session",
                "start_time": "2025-06-21T10:00:00Z",
                "end_time": "2025-06-21T10:01:00Z",
                "articles_scraped": 1
            }
        }
        
        # Test AI processing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                ai_summarizer.process_news_with_claude4_prompt(
                    session_data=test_session_data,
                    use_claude4=True
                )
            )
        finally:
            loop.close()
        
        return jsonify({
            "ai_test": "success",
            "model_available": True,
            "test_result": result,
            "test_input": test_text
        }), 200
        
    except Exception as e:
        logger.error(f"Error testing AI: {e}")
        return jsonify({
            "ai_test": "failed",
            "model_available": False,
            "error": str(e)
        }), 500

@analysis_blueprint.route('/status', methods=['GET'])
async def get_analysis_status():
    """Get analysis service status and configuration."""
    try:
        # Check AI configuration
        google_api_key = current_app.config.get('GOOGLE_API_KEY')
        ai_available = bool(google_api_key)
        
        # Try to initialize AI
        ai_model_ready = False
        if ai_available:
            try:
                ai_summarizer = AISummarizer(google_api_key=google_api_key)
                ai_model_ready = bool(ai_summarizer.model)
            except Exception as e:
                logger.warning(f"AI model initialization failed: {e}")
        
        # Check Claude 4 prompt
        claude4_prompt_available = False
        try:
            from capabilities.ai_summarizer import load_claude4_prompt
            prompt = load_claude4_prompt()
            claude4_prompt_available = not prompt.startswith("Error:")
        except Exception as e:
            logger.warning(f"Claude 4 prompt check failed: {e}")
        
        return jsonify({
            "service": "AnalysisService with AI",
            "status": "available" if ai_model_ready else "limited",
            "google_api_configured": ai_available,
            "ai_model_ready": ai_model_ready,
            "claude4_prompt_available": claude4_prompt_available,
            "supported_scenarios": [
                "persist=true (file-based)",
                "persist=false (direct data)",
                "auto-discovery (latest session)"
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting analysis status: {e}")
        return jsonify({
            "service": "AnalysisService",
            "status": "error",
            "error": str(e)
        }), 500
