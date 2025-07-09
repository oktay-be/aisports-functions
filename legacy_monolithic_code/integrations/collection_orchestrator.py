"""
Collection Orchestrator for AISports application.
Orchestrates full and targeted collection workflows as defined in the implementation plan.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import uuid
from pathlib import Path

# Import core services
from database.mongodb_client import MongoDBClient
from capabilities.ai_aggregator import AIAggregator
from capabilities.ai_summarizer import AISummarizer
from capabilities.news_aggregator import NewsAggregator
from capabilities.content_scraping_service import Journalist, JOURNALIST_AVAILABLE

logger = logging.getLogger(__name__)

class CollectionOrchestrator:
    """
    Orchestrates the full news collection and analysis workflow.
    
    Implements both UseCase 1 (Automated Full Collection) and 
    UseCase 2 (Targeted Re-scraping) from the implementation plan.
    """
    
    def __init__(self, google_api_key: str, newsapi_key: str = None):
        """
        Initialize Collection Orchestrator.
        
        Args:
            google_api_key: Google API key for AI operations
            newsapi_key: NewsAPI key for data integration
        """
        self.google_api_key = google_api_key
        self.newsapi_key = newsapi_key
        
        # Initialize core services
        self.db_client = None
        self.ai_aggregator = None
        self.ai_summarizer = None
        self.news_aggregator = None
        self.newsapi_service = None
        
        # Workflow configuration
        self.temp_data_persist = False  # Memory-only by default
        self.cache_dir = Path("./tmp_cache_orchestrator")
        self.cache_dir.mkdir(exist_ok=True)
        
        # Source configuration - based on existing config files
        self.tr_sources = [
            "https://www.fanatik.com.tr",
            "https://www.fotomac.com.tr",
            "https://www.milliyet.com.tr/skorer",
            "https://www.sabah.com.tr/spor"
        ]
        
        self.eu_sources = [
            "https://www.bbc.com/sport",
            "https://www.espn.com/soccer",
            "https://www.fourfourtwo.com",
            "https://www.goal.com"        ]
    
    async def initialize(self):
        """Initialize all services and database connections."""
        try:
            # Initialize database
            self.db_client = MongoDBClient()
            try:
                await self.db_client.connect()
                logger.info("Database connection established successfully")
            except Exception as db_error:
                logger.warning(f"Database connection failed: {db_error}")
                logger.warning("Continuing without database - some features will be disabled")
                self.db_client = None
            
            # Initialize AI services
            self.ai_aggregator = AIAggregator()
            try:
                await self.ai_aggregator.initialize()
                logger.info("AI Aggregator initialized successfully")
            except Exception as agg_error:
                logger.warning(f"AI Aggregator initialization failed: {agg_error}")
                # Continue without aggregator for testing
            
            # Initialize AI Summarizer with Vertex AI (uses ADC from .env)
            self.ai_summarizer = AISummarizer()
            
            # Initialize news aggregator with NewsAPI key
            self.news_aggregator = NewsAggregator(
                newsapi_key=self.newsapi_key,
                cache_dir=str(self.cache_dir / "news_aggregator")
            )
            
            logger.info("Collection Orchestrator initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Collection Orchestrator: {e}")
            raise
    
    async def cleanup(self):
        """Cleanup resources and connections."""
        try:
            if self.db_client:
                await self.db_client.disconnect()
                logger.info("Database connection closed")
            else:
                logger.info("No database connection to close")
            
            # Cleanup temp data if not persisted
            if not self.temp_data_persist:
                await self._cleanup_temp_data([])
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    async def run_full_collection(self, keywords: List[str]) -> str:
        """
        UseCase 1: Automated Full Collection
        
        Workflow:
        1. Create collection run in MongoDB
        2. Trigger parallel scraping (TR + EU sources)
        3. Process each source with AI → save to MongoDB
        4. Aggregate by region → save to MongoDB  
        5. Extend EU with NewsAPI → save to MongoDB
        6. Generate diff analysis → save to MongoDB
        7. Update run status to completed
        
        Args:
            keywords: List of keywords for the collection
            
        Returns:
            str: Run ID for tracking the collection
        """
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        
        try:
            logger.info(f"Starting full collection workflow: {run_id}")
            
            # Step 1: Create collection run in MongoDB
            await self._create_collection_run(run_id, keywords, "full")            # Step 2: Parallel scraping of TR and EU sources
            logger.info("Starting parallel scraping of TR and EU sources...")
            
            # Use journalist directly for parallel scraping
            async def scrape_tr():
                if not JOURNALIST_AVAILABLE:
                    raise RuntimeError("Journalist library not available for scraping")
                journalist = Journalist()
                source_sessions = await journalist.read(urls=self.tr_sources, keywords=keywords)
                return journalist, source_sessions
            
            async def scrape_eu():
                if not JOURNALIST_AVAILABLE:
                    raise RuntimeError("Journalist library not available for scraping")
                journalist = Journalist()
                source_sessions = await journalist.read(urls=self.eu_sources, keywords=keywords)
                return journalist, source_sessions
              # Execute only TR scraping (EU disabled for debugging)
            tr_result = await asyncio.gather(
                scrape_tr(),
                return_exceptions=True
            )
            tr_result = tr_result[0]  # Extract single result from gather
            eu_result = None
              # Handle scraping errors
            if isinstance(tr_result, Exception):
                logger.error(f"TR scraping failed: {tr_result}")
                tr_journalist, tr_sessions = None, []
            else:
                tr_journalist, tr_sessions = tr_result
                
            # EU scraping is disabled for debugging
            eu_journalist, eu_sessions = None, []
            logger.info("EU scraping disabled - focusing on TR sources only")# Step 3: Process session data with AI using AISummarizer (in parallel)
            logger.info("Processing session data with AI...")
            
            # Create tasks for parallel processing
            tasks = []
            
            if tr_sessions:
                tr_task = self._process_session_data_list(tr_sessions, run_id, "TR")
                tasks.append(('TR', tr_task))
            
            if eu_sessions:
                eu_task = self._process_session_data_list(eu_sessions, run_id, "EU")
                tasks.append(('EU', eu_task))
            
            # Execute both TR and EU processing simultaneously
            tr_summary_ids = []
            eu_summary_ids = []
            
            if tasks:
                logger.info(f"Processing {len(tasks)} regions in parallel...")
                results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
                
                for i, (region, _) in enumerate(tasks):
                    result = results[i]
                    if isinstance(result, Exception):
                        logger.error(f"{region} processing failed: {result}")
                        if region == "TR":
                            tr_summary_ids = []
                        else:
                            eu_summary_ids = []
                    else:
                        if region == "TR":
                            tr_summary_ids = result
                        else:
                            eu_summary_ids = result
            
            # Step 4: Aggregate by region and save to MongoDB
            logger.info("Aggregating results by region...")
            tr_aggregation = await self.ai_aggregator.aggregate_sources_by_region(run_id, "TR")
            eu_aggregation = await self.ai_aggregator.aggregate_sources_by_region(run_id, "EU")            # Step 5: Extend EU with NewsAPI
            if self.newsapi_key and self.news_aggregator:
                logger.info("Extending EU data with NewsAPI...")
                # Use existing news_aggregator to fetch NewsAPI data
                self.news_aggregator.update_keywords(keywords)
                newsapi_articles = await self.news_aggregator.fetch_newsapi_articles()
                
                if newsapi_articles:
                    # Create NewsAPI data structure for MongoDB
                    newsapi_data = {
                        "run_id": run_id,
                        "fetch_timestamp": datetime.now(timezone.utc),
                        "keywords_used": keywords,
                        "raw_articles": newsapi_articles,
                        "article_count": len(newsapi_articles)
                    }
                    
                    # Save to MongoDB and extend EU
                    await self.db_client.save_newsapi_data(newsapi_data)
                    eu_extended = await self.ai_aggregator.extend_eu_with_newsapi(
                        run_id, eu_aggregation, newsapi_data
                    )
                    logger.info(f"Extended EU data with {len(newsapi_articles)} NewsAPI articles")
                else:
                    eu_extended = eu_aggregation
                    logger.info("No NewsAPI articles found, using original EU aggregation")
            else:
                logger.warning("NewsAPI key not available, skipping EU extension")
                eu_extended = eu_aggregation
            
            # Step 6: Generate diff analysis
            logger.info("Generating diff analysis...")
            diff_result = await self.ai_aggregator.generate_ai_diff(run_id)
              # Step 7: Update run status to completed
            await self._update_collection_run_status(run_id, "completed", {
                "tr_sources_processed": len(tr_summary_ids),
                "eu_sources_processed": len(eu_summary_ids),
                "newsapi_integrated": bool(self.newsapi_key and newsapi_data),
                "diff_analysis_completed": bool(diff_result)
            })
            
            logger.info(f"Full collection workflow completed: {run_id}")
            return run_id
            
        except Exception as e:
            logger.error(f"Full collection workflow failed: {e}")
            await self._update_collection_run_status(run_id, "failed", {"error": str(e)})
            raise
    
    async def run_targeted_scraping(self, target_keywords: List[str], region: str = "EU") -> str:
        """
        UseCase 2: Targeted Re-scraping
        
        Workflow:
        1. Create targeted run in MongoDB
        2. Scrape only specified region with new keywords
        3. Process with AI → save to MongoDB
        4. Return results for frontend display
        
        Args:
            target_keywords: List of keywords for targeted scraping
            region: Region to target ("TR" or "EU")
            
        Returns:
            str: Run ID for tracking the targeted collection
        """
        run_id = f"targeted_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        
        try:
            logger.info(f"Starting targeted scraping workflow: {run_id}")
              # Step 1: Create targeted run in MongoDB
            await self._create_collection_run(run_id, target_keywords, "targeted", region)            # Step 2: Scrape only specified region
            logger.info(f"Scraping {region} sources with targeted keywords...")
            
            if not JOURNALIST_AVAILABLE:
                raise RuntimeError("Journalist library not available for scraping")
            
            sources = self.tr_sources if region == "TR" else self.eu_sources
            logger.info(f"Scraping {len(sources)} sources for region {region} with keywords: {target_keywords}")
            
            # Create journalist instance and scrape
            journalist = Journalist()
            source_sessions = await journalist.read(
                urls=sources,
                keywords=target_keywords
            )
            
            logger.info(f"Scraping completed for {region}, session path: {journalist.session_path}")
              # Step 3: Process session data with AI using AISummarizer
            logger.info("Processing session data with AI...")
            summary_ids = []
            if source_sessions:
                summary_ids = await self._process_session_data_list(
                    source_sessions, run_id, region
                )
            
            # Update run status
            await self._update_collection_run_status(run_id, "completed", {
                "sources_processed": len(summary_ids),
                "region": region
            })
            
            logger.info(f"Targeted scraping workflow completed: {run_id}")
            return run_id
            
        except Exception as e:
            logger.error(f"Targeted scraping workflow failed: {e}")
            await self._update_collection_run_status(run_id, "failed", {"error": str(e)})
            raise
  
    
    async def _process_session_data(self, session_data: List[Dict], run_id: str, region: str) -> List[str]:
        """
        Process scraped session data with AI and save to MongoDB.
        
        Args:
            session_data: Raw scraped article data
            run_id: Collection run identifier
            region: Region identifier
              Returns:
            List[str]: List of summary IDs created
        """
        if not session_data:
            logger.warning(f"No session data to process for region {region}")
            return []
        
        # Group articles by source
        sources_data = {}
        for article in session_data:
            source = article.get("source_domain")
            if source not in sources_data:
                sources_data[source] = []
            sources_data[source].append(article)
        
        summary_ids = []
        
        for source_domain, articles in sources_data.items():
            try:
                logger.info(f"Processing {len(articles)} articles from {source_domain}")
                
                # Process source with AI using AI summarizer directly
                processed_result = await self._process_source_with_ai(
                    articles, source_domain, region
                )
                  # Save to MongoDB
                summary_doc = {
                    "run_id": run_id,
                    "source_domain": source_domain,
                    "source_url": articles[0].get("source_url", ""),
                    "region": region,
                    "summary_data": processed_result,
                    "created_at": datetime.now(timezone.utc)
                }
                
                result = await self.db_client.save_ai_summary_per_source(summary_doc)
                summary_ids.append(str(result.inserted_id))
                
                logger.info(f"Saved AI summary for {source_domain}: {result.inserted_id}")
                
            except Exception as e:
                logger.error(f"Failed to process source {source_domain}: {e}")
                continue
        
        return summary_ids
    
    async def _process_session_data_files(self, session_path: str, run_id: str, region: str) -> List[str]:
        """
        Process journalist session data files with AI using AISummarizer.summarize_and_classify_session_data_object
        
        Args:
            session_path: Path to the journalist session workspace directory
            run_id: Collection run identifier
            region: Region identifier ("TR" or "EU")
            
        Returns:
            List[str]: List of summary IDs created
        """
        if not session_path or not Path(session_path).exists():
            logger.warning(f"Session path does not exist: {session_path}")
            return []
        
        # Find all session data files in the session path
        session_data_files = list(Path(session_path).glob("session_data_*.json"))
        
        if not session_data_files:
            logger.warning(f"No session data files found in {session_path}")
            return []
        
        logger.info(f"Found {len(session_data_files)} session data files for region {region}")
        
        # Process each session data file in parallel
        async def process_single_session_file(session_file_path: Path) -> Optional[str]:
            """Process a single session data file and return summary ID if successful"""
            try:
                logger.info(f"Processing session data file: {session_file_path}")
                
                # Use AISummarizer to process the session data file
                result = await self.ai_summarizer.summarize_and_classify_session_data_object(
                    str(session_file_path)
                )
                
                if result.get("error"):
                    logger.error(f"AI processing failed for {session_file_path}: {result['error']}")
                    return None
                
                # Extract source domain from filename (e.g., "session_data_fanatik_com_tr.json" -> "fanatik.com.tr")
                filename = session_file_path.name
                if filename.startswith("session_data_") and filename.endswith(".json"):
                    source_domain = filename[len("session_data_"):-len(".json")].replace("_", ".")
                else:
                    source_domain = filename
                
                # Save to MongoDB
                summary_doc = {
                    "run_id": run_id,
                    "source_domain": source_domain,
                    "source_url": f"https://{source_domain}",
                    "region": region,
                    "summary_data": result,
                    "created_at": datetime.now(timezone.utc),
                    "session_file_path": str(session_file_path)
                }
                
                db_result = await self.db_client.save_ai_summary_per_source(summary_doc)
                summary_id = str(db_result.inserted_id)
                
                logger.info(f"Successfully processed {session_file_path} -> {summary_id}")
                return summary_id
                
            except Exception as e:
                logger.error(f"Failed to process session file {session_file_path}: {e}", exc_info=True)
                return None
        
        # Process all session data files in parallel
        tasks = [process_single_session_file(file_path) for file_path in session_data_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect successful summary IDs
        summary_ids = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing {session_data_files[i]}: {result}")
            elif result:  # result is a summary ID
                summary_ids.append(result)
        
        logger.info(f"Successfully processed {len(summary_ids)} out of {len(session_data_files)} session files for region {region}")
        return summary_ids
    
    async def _process_session_data_list(self, sessions: List[Dict[str, Any]], run_id: str, region: str) -> List[str]:
        """
        Process journalist session data list with AI using AISummarizer.summarize_and_classify_session_data_object
        
        Args:
            sessions: List of session data objects (e.g., tr_sessions or eu_sessions)
            run_id: Collection run identifier
            region: Region identifier ("TR" or "EU")
            
        Returns:
            List[str]: List of summary IDs created
        """
        if not sessions:
            logger.warning(f"No session data provided for region {region}")
            return []
        
        logger.info(f"Processing {len(sessions)} session data objects for region {region}")
        
        # Process each session data object in parallel
        async def process_single_session(session_index: int, session_data: Dict[str, Any]) -> Optional[str]:
            """Process a single session data object and return summary ID if successful"""
            try:
                source_domain = session_data.get('source_domain', f'unknown_source_{session_index}')
                articles_count = len(session_data.get('articles', []))
                logger.info(f"Processing session {session_index}: {source_domain} with {articles_count} articles")
                
                # Use AISummarizer to process the session data object
                result = await self.ai_summarizer.summarize_and_classify_session_data_object(session_data)
                
                if result.get("error"):
                    logger.error(f"AI processing failed for session {session_index} ({source_domain}): {result['error']}")
                    return None
                  # Save to MongoDB (if database is available)
                if self.db_client:
                    summary_doc = {
                        "run_id": run_id,
                        "source_domain": source_domain,
                        "source_url": session_data.get('url', f"https://{source_domain}"),
                        "region": region,
                        "summary_data": result,
                        "created_at": datetime.now(timezone.utc),
                        "session_index": session_index
                    }
                    
                    try:
                        db_result = await self.db_client.save_ai_summary_per_source(summary_doc)
                        summary_id = str(db_result.inserted_id)
                        logger.info(f"Successfully processed session {session_index} ({source_domain}) -> {summary_id}")
                    except Exception as db_error:
                        logger.warning(f"Database save failed for session {session_index}: {db_error}")
                        # Generate a mock summary ID for testing
                        summary_id = f"mock_summary_{session_index}_{source_domain}"
                        logger.info(f"Generated mock summary ID: {summary_id}")
                else:
                    # Generate a mock summary ID when database is not available (for testing)
                    summary_id = f"mock_summary_{session_index}_{source_domain}"
                    logger.info(f"Database not available - generated mock summary ID: {summary_id}")
                
                return summary_id
                
            except Exception as e:
                logger.error(f"Failed to process session {session_index}: {e}", exc_info=True)
                return None
        
        # Process all session data objects in parallel
        tasks = [
            process_single_session(i, session_data) 
            for i, session_data in enumerate(sessions)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect successful summary IDs
        summary_ids = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing session {i}: {result}")
            elif result:  # result is a summary ID
                summary_ids.append(result)
        
        logger.info(f"Successfully processed {len(summary_ids)} out of {len(sessions)} sessions for region {region}")
        return summary_ids
    
    async def _create_collection_run(self, run_id: str, keywords: List[str], 
                                   collection_type: str, region: str = None):
        """
        Create a collection run record in MongoDB.
        
        Args:
            run_id: Run identifier
            keywords: Keywords used for collection
            collection_type: "full" or "targeted"
            region: Region (for targeted runs)
        """
        if not self.db_client:
            logger.warning(f"Database not available, skipping collection run creation for {run_id}")
            return
        
        run_doc = {
            "run_id": run_id,
            "type": collection_type,
            "keywords": keywords,
            "status": "running",
            "created_at": datetime.now(timezone.utc),
            "metadata": {
                "region": region
            }
        }
        
        try:
            await self.db_client.create_collection_run(run_doc)
            logger.info(f"Created collection run: {run_id}")
        except Exception as e:
            logger.error(f"Failed to create collection run {run_id}: {e}")            # Continue without database for testing
    
    async def _update_collection_run_status(self, run_id: str, status: str, metadata: Dict = None):
        """
        Update collection run status and metadata.
        
        Args:
            run_id: Run identifier
            status: New status
            metadata: Additional metadata to store
        """
        if not self.db_client:
            logger.warning(f"Database not available, skipping status update for {run_id} to {status}")
            return
        
        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc)
        }
        
        if metadata:
            update_data["metadata"] = metadata
        
        try:
            await self.db_client.update_collection_run(run_id, update_data)
            logger.info(f"Updated run {run_id} status to: {status}")
        except Exception as e:
            logger.error(f"Failed to update run status for {run_id}: {e}")
            # Continue without database for testing
    
    async def _cleanup_temp_data(self, temp_data: List[Dict]):
        """
        Cleanup temporary data when persist=false.
        
        Args:
            temp_data: Temporary data to cleanup
        """
        try:
            # Clear memory references
            temp_data.clear()
            
            # Remove temporary cache files
            if self.cache_dir.exists():
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink()
            
            logger.info("Temporary data cleaned up")
            
        except Exception as e:
            logger.error(f"Error cleaning up temporary data: {e}")

    async def get_collection_status(self, run_id: str) -> Optional[Dict]:
        """
        Get status and results of a collection run.
        
        Args:
            run_id: Run identifier
            
        Returns:
            Optional[Dict]: Run status and metadata
        """
        try:
            return await self.db_client.get_collection_run(run_id)
        except Exception as e:
            logger.error(f"Failed to get collection status for {run_id}: {e}")
            return None
    
    async def list_recent_runs(self, limit: int = 10) -> List[Dict]:
        """
        List recent collection runs.
        
        Args:
            limit: Maximum number of runs to return
            
        Returns:
            List[Dict]: Recent collection runs
        """
        try:
            return await self.db_client.list_collection_runs(limit=limit)
        except Exception as e:
            logger.error(f"Failed to list recent runs: {e}")
            return []
    
    async def _process_source_with_ai(self, articles: List[Dict], source_domain: str, region: str) -> Dict:
        """
        Process source articles with AI to generate summary.
        
        Args:
            articles: List of articles from the source
            source_domain: Domain name of the source
            region: Region identifier
            
        Returns:
            Dict: Processed summary data in the expected format
        """
        try:
            # Create a prompt for AI summarization
            articles_text = ""
            for i, article in enumerate(articles, 1):
                title = article.get("title", "No Title")
                content = article.get("content", article.get("description", ""))
                url = article.get("url", "")
                
                articles_text += f"\n--- Article {i} ---\n"
                articles_text += f"Title: {title}\n"
                articles_text += f"URL: {url}\n"
                articles_text += f"Content: {content[:500]}...\n"  # Limit content length
            
            # Create AI prompt for source processing
            prompt = f"""
You are processing news articles from {source_domain} for the {region} region.

Please analyze these {len(articles)} articles and provide a summary in the following JSON format:

{{
    "processing_summary": {{
        "total_input_articles": {len(articles)},
        "articles_after_deduplication": <count>,
        "articles_after_cleaning": <count>,
        "duplicates_removed": <count>,
        "empty_articles_removed": <count>,
        "processing_date": "{datetime.now(timezone.utc).isoformat()}"
    }},
    "ai_summarized_articles": [
        {{
            "id": "article_1",
            "original_url": "<url>",
            "title": "<title>",
            "summary": "<AI generated summary>",
            "key_entities": {{
                "teams": ["<team_names>"],
                "players": ["<player_names>"],
                "amounts": ["<financial_amounts>"],
                "dates": ["<important_dates>"]
            }},
            "categories": [
                {{
                    "tag": "<category_tag>",
                    "confidence": <0.0-1.0>,
                    "evidence": "<supporting_text>"
                }}
            ],
            "source": "{source_domain}",
            "published_date": "<date>",
            "keywords_matched": ["<matched_keywords>"],
            "content_quality": "high|medium|low",
            "language": "{"turkish" if region == "TR" else "english"}"
        }}
    ]
}}

Focus on sports news, transfers, team news, and player information. Remove duplicates and low-quality content.

Articles to process:
{articles_text}
"""
            
            # Use AI summarizer to process the articles
            response = await self.ai_summarizer.generate_summary(prompt)
            
            # Try to parse the JSON response
            try:
                summary_data = json.loads(response)
                return summary_data
            except json.JSONDecodeError:
                logger.warning(f"AI response was not valid JSON for {source_domain}, creating fallback structure")
                # Create fallback structure
                return {
                    "processing_summary": {
                        "total_input_articles": len(articles),
                        "articles_after_deduplication": len(articles),
                        "articles_after_cleaning": len(articles),
                        "duplicates_removed": 0,
                        "empty_articles_removed": 0,
                        "processing_date": datetime.now(timezone.utc).isoformat()
                    },
                    "ai_summarized_articles": [
                        {
                            "id": f"article_{i}",
                            "original_url": article.get("url", ""),
                            "title": article.get("title", ""),
                            "summary": article.get("content", article.get("description", ""))[:200] + "...",
                            "key_entities": {"teams": [], "players": [], "amounts": [], "dates": []},
                            "categories": [{"tag": "sports", "confidence": 0.5, "evidence": "Fallback categorization"}],
                            "source": source_domain,
                            "published_date": article.get("published_at", article.get("publishedAt", "")),
                            "keywords_matched": [],
                            "content_quality": "medium",
                            "language": "turkish" if region == "TR" else "english"
                        }
                        for i, article in enumerate(articles, 1)
                    ]
                }
            
        except Exception as e:
            logger.error(f"Error processing source {source_domain} with AI: {e}")
            # Return minimal structure on error
            return {
                "processing_summary": {
                    "total_input_articles": len(articles),
                    "articles_after_deduplication": 0,
                    "articles_after_cleaning": 0,
                    "duplicates_removed": 0,
                    "empty_articles_removed": len(articles),
                    "processing_date": datetime.now(timezone.utc).isoformat()
                },
                "ai_summarized_articles": []
            }
