"""
API routes for the refactored AISports API.
Simplified architecture with separated scraping and analysis services.
"""

import logging
import time
import asyncio
import json
import os
from quart import Blueprint, jsonify, current_app
from api.endpoints.scraping_endpoints import scraping_blueprint
from api.endpoints.analysis_endpoints import analysis_blueprint

logger = logging.getLogger(__name__)

# Create main API blueprint
api_blueprint = Blueprint('api', __name__)

# Register sub-blueprints with URL prefixes
api_blueprint.register_blueprint(scraping_blueprint, url_prefix='/scraping')
api_blueprint.register_blueprint(analysis_blueprint, url_prefix='/analysis')

@api_blueprint.route('/health', methods=['GET'])
async def health_check():
    """Health check endpoint for the refactored API."""
    return jsonify({
        "status": "healthy",
        "version": "2.0.0-refactored",
        "architecture": "service-oriented",
        "services": {
            "scraping": "journ4list",
            "analysis": "google_genai + claude4"
        },
        "endpoints": {
            "scraping": "/api/scraping/*",
            "analysis": "/api/analysis/*"
        }
    }), 200

@api_blueprint.route('/status', methods=['GET'])
async def get_overall_status():
    """Get overall system status for all services."""
    try:
        from capabilities.services.scraping_service import ScrapingService
        from capabilities.ai_summarizer import AISummarizer
        
        # Check scraping service
        scraping_service = ScrapingService()
        latest_session = scraping_service.find_latest_session()
        scraping_status = {
            "available": True,
            "latest_session_available": latest_session is not None,
            "workspace_dir": scraping_service.workspace_dir,
            "total_sessions": len(scraping_service.list_all_sessions())
        }
        
        # Check AI service
        google_api_key = current_app.config.get('GOOGLE_API_KEY')
        ai_status = {
            "google_api_configured": bool(google_api_key),
            "model_available": False
        }
        
        if google_api_key:
            try:
                ai_summarizer = AISummarizer(google_api_key=google_api_key)
                ai_status["model_available"] = bool(ai_summarizer.model)
            except Exception as e:
                ai_status["error"] = str(e)
        
        return jsonify({
            "overall_status": "healthy",
            "timestamp": "2025-06-21T00:00:00Z",
            "services": {
                "scraping": scraping_status,
                "analysis": ai_status
            },
            "architecture_info": {
                "pipeline_removed": True,
                "orchestrator_removed": True,
                "service_separation": "complete"
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Status check error: {e}")
        return jsonify({
            "overall_status": "error",
            "error": str(e)
        }), 500

@api_blueprint.route('/migration_info', methods=['GET'])
async def get_migration_info():
    """Get information about the migration from old to new architecture."""
    return jsonify({
        "migration": {
            "status": "completed",
            "from": "custom scraping + pipeline orchestration",
            "to": "journ4list + service-oriented architecture",
            "breaking_changes": False,
            "deprecated_endpoints": [
                "/api/analysis/start_job (use /api/scraping/start + /api/analysis/process_scraped_data)",
                "/api/analysis/get_job_status (use /api/scraping/status + /api/analysis/status)"
            ]
        },
        "new_workflow": {
            "step_1": "POST /api/scraping/start - Start scraping with journ4list",
            "step_2": "GET /api/scraping/latest - Check scraping results", 
            "step_3": "POST /api/analysis/process_scraped_data - Analyze scraped data",
            "alternative": "POST /api/analysis/auto_process - One-step auto analysis"
        },
        "benefits": [
            "Separated concerns (scraping vs analysis)",
            "No blocking pipeline operations", 
            "Battle-tested journ4list library",
            "Independent service scaling",
            "Better error handling",
            "Simplified codebase"
        ]
    }), 200

@api_blueprint.route('/diff', methods=['POST'])
async def diff_scraping():
    """
    Compound endpoint that runs journalist.read in parallel for EU and TR sources.
    This is an orchestration operation that coordinates multiple scraping tasks.
    """
    start_time = time.time()
    logger.info("Starting diff scraping operation")
    
    try:
        from journalist import Journalist
        
        # Load search parameters
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        eu_params_path = os.path.join(base_dir, 'search_parameters_eu.json')
        tr_params_path = os.path.join(base_dir, 'search_parameters_tr.json')
        
        with open(eu_params_path, 'r', encoding='utf-8') as f:
            eu_params = json.load(f)
        
        with open(tr_params_path, 'r', encoding='utf-8') as f:
            tr_params = json.load(f)
        
        logger.info(f"Loaded EU params: {len(eu_params.get('urls', []))} URLs, keywords: {eu_params.get('keywords', [])}")
        logger.info(f"Loaded TR params: {len(tr_params.get('urls', []))} URLs, keywords: {tr_params.get('keywords', [])}")
        
        # Create async tasks for parallel execution
        async def scrape_eu():
            try:
                logger.info("Starting EU scraping task")
                eu_journalist = Journalist()
                eu_result = eu_journalist.read(
                    sources=eu_params['urls'],
                    keywords=eu_params['keywords'],
                    persist=True
                )
                logger.info(f"EU scraping completed: {len(eu_result) if eu_result else 0} articles")
                return eu_result, eu_journalist
            except Exception as e:
                logger.error(f"EU scraping error: {e}")
                return [], None
        
        async def scrape_tr():
            try:
                logger.info("Starting TR scraping task")
                tr_journalist = Journalist()
                tr_result = tr_journalist.read(
                    sources=tr_params['urls'],
                    keywords=tr_params['keywords'],
                    persist=True
                )
                logger.info(f"TR scraping completed: {len(tr_result) if tr_result else 0} articles")
                return tr_result, tr_journalist
            except Exception as e:
                logger.error(f"TR scraping error: {e}")
                return [], None
        
        # Run both scraping tasks in parallel
        logger.info("Running EU and TR scraping tasks in parallel...")
        (eu_result, eu_journalist), (tr_result, tr_journalist) = await asyncio.gather(
            scrape_eu(),
            scrape_tr()
        )
        
        end_time = time.time()
        
        # Extract articles (journalist.read returns a list)
        eu_articles = eu_result if eu_result else []
        tr_articles = tr_result if tr_result else []
        
        # Get session IDs for persistence tracking
        eu_session_id = getattr(eu_journalist, 'session_id', None) if eu_journalist else None
        tr_session_id = getattr(tr_journalist, 'session_id', None) if tr_journalist else None
        
        # Prepare response
        response_data = {
            "message": "Diff scraping completed",
            "execution_time_seconds": round(end_time - start_time, 2),
            "results": {
                "eu_sources": {
                    "session_id": eu_session_id,
                    "articles_count": len(eu_articles),
                    "urls_scraped": len(eu_params.get('urls', [])),
                    "keywords_used": eu_params.get('keywords', []),
                    "articles": eu_articles[:5] if len(eu_articles) > 5 else eu_articles,
                    "has_more": len(eu_articles) > 5
                },
                "tr_sources": {
                    "session_id": tr_session_id,
                    "articles_count": len(tr_articles),
                    "urls_scraped": len(tr_params.get('urls', [])),
                    "keywords_used": tr_params.get('keywords', []),
                    "articles": tr_articles[:5] if len(tr_articles) > 5 else tr_articles,
                    "has_more": len(tr_articles) > 5
                }
            },
            "summary": {
                "total_articles": len(eu_articles) + len(tr_articles),
                "eu_articles": len(eu_articles),
                "tr_articles": len(tr_articles),
                "eu_session_saved": eu_session_id is not None,
                "tr_session_saved": tr_session_id is not None
            }
        }
        
        logger.info(f"Diff scraping completed: EU={len(eu_articles)} articles, TR={len(tr_articles)} articles")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error in diff scraping endpoint: {str(e)}", exc_info=True)
        from api.models import ErrorResponse
        return jsonify(ErrorResponse(
            error="Diff Scraping Error",
            details=str(e),
            code=500
        ).__dict__), 500

# Remove all complex pipeline orchestration code
# Remove threading logic  
# Remove AnalysisOrchestrator usage
# Remove start_analysis_job endpoint (replaced by separated endpoints)
