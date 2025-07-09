"""
PyMongo Async-based MongoDB client for AISports application.
Handles all async database operations for the news collection and AI processing workflow.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import os

# Try to import PyMongo async, handle gracefully if not installed
try:
    from pymongo import AsyncMongoClient, ASCENDING, DESCENDING
    from pymongo.errors import ConnectionFailure, DuplicateKeyError
    from bson import ObjectId
    PYMONGO_ASYNC_AVAILABLE = True
except ImportError:
    PYMONGO_ASYNC_AVAILABLE = False
    # Define dummy classes for type hints when pymongo is not available
    class AsyncMongoClient: pass
    class ConnectionFailure(Exception): pass
    class DuplicateKeyError(Exception): pass
    class ObjectId: pass
    ASCENDING = 1
    DESCENDING = -1

logger = logging.getLogger(__name__)

class MongoDBClient:
    """
    Async MongoDB client for AISports application using PyMongo Async.
    Manages connections and operations for all collections.
    """
    
    def __init__(self, connection_string: str = None, database_name: str = "aisports"):
        """
        Initialize MongoDB client.
        
        Args:
            connection_string: MongoDB connection URI
            database_name: Database name to use
        """
        if not PYMONGO_ASYNC_AVAILABLE:
            raise ImportError("PyMongo with async support is required but not installed. Install with: pip install pymongo>=4.5")
            
        self.connection_string = connection_string or os.getenv(
            "MONGODB_URI", 
            "mongodb://localhost:27017"
        )
        self.database_name = database_name
        self.client = None
        self.db = None
        self._connected = False
        
        # Collection names
        self.COLLECTION_RUNS = "collection_runs"
        self.AI_SUMMARIES_PER_SOURCE = "ai_summaries_per_source"
        self.AI_AGGREGATED_RESULTS = "ai_aggregated_results"
        self.AI_DIFF_RESULTS = "ai_diff_results"
        self.NEWSAPI_DATA = "newsapi_data"
        self.AI_POSTS = "ai_posts"
    
    async def connect(self) -> bool:
        """
        Connect to MongoDB and ensure database setup.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.client = AsyncMongoClient(self.connection_string)
            # Test connection
            await self.client.admin.command('ping')
            self.db = self.client[self.database_name]
            self._connected = True
            
            # Ensure indexes
            await self.ensure_indexes()
            
            logger.info(f"Connected to MongoDB database: {self.database_name}")
            return True
            
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from MongoDB."""
        if self.client:
            await self.client.close()
            self._connected = False
            logger.info("Disconnected from MongoDB")
    
    async def ensure_indexes(self):
        """Create necessary indexes for performance."""
        try:
            # Collection runs indexes
            await self.db[self.COLLECTION_RUNS].create_index([
                ("run_id", ASCENDING)
            ], unique=True)
            
            await self.db[self.COLLECTION_RUNS].create_index([
                ("created_at", DESCENDING)
            ])
            
            await self.db[self.COLLECTION_RUNS].create_index([
                ("run_type", ASCENDING),
                ("status", ASCENDING)
            ])
            
            # AI summaries per source indexes
            await self.db[self.AI_SUMMARIES_PER_SOURCE].create_index([
                ("run_id", ASCENDING),
                ("source_domain", ASCENDING)
            ])
            
            await self.db[self.AI_SUMMARIES_PER_SOURCE].create_index([
                ("region", ASCENDING),
                ("created_at", DESCENDING)
            ])
            
            # AI aggregated results indexes
            await self.db[self.AI_AGGREGATED_RESULTS].create_index([
                ("run_id", ASCENDING),
                ("region", ASCENDING),
                ("aggregation_type", ASCENDING)
            ])
            
            # AI diff results indexes
            await self.db[self.AI_DIFF_RESULTS].create_index([
                ("run_id", ASCENDING)
            ])
            
            # NewsAPI data indexes
            await self.db[self.NEWSAPI_DATA].create_index([
                ("run_id", ASCENDING)
            ])
            
            await self.db[self.NEWSAPI_DATA].create_index([
                ("fetch_timestamp", DESCENDING)
            ])
            
            # AI posts indexes
            await self.db[self.AI_POSTS].create_index([
                ("post_id", ASCENDING)
            ], unique=True)
            
            await self.db[self.AI_POSTS].create_index([
                ("post_status", ASCENDING),
                ("created_at", DESCENDING)
            ])
            
            await self.db[self.AI_POSTS].create_index([
                ("based_on_articles", ASCENDING)
            ])
            
            logger.info("Database indexes ensured")
            
        except Exception as e:
            logger.error(f"Error ensuring indexes: {e}")
    
    # Collection Runs Operations
    async def save_collection_run(self, run_data: Dict) -> str:
        """
        Save collection run metadata.
        
        Args:
            run_data: Collection run data
            
        Returns:
            str: run_id of saved record
        """
        try:
            run_data["created_at"] = datetime.now(timezone.utc)
            
            result = await self.db[self.COLLECTION_RUNS].insert_one(run_data)
            logger.info(f"Saved collection run: {run_data['run_id']}")
            return run_data["run_id"]
            
        except DuplicateKeyError:
            logger.warning(f"Collection run already exists: {run_data['run_id']}")
            return run_data["run_id"]
        except Exception as e:
            logger.error(f"Error saving collection run: {e}")
            raise
    
    async def update_collection_run_status(self, run_id: str, status: str, stats: Dict = None) -> bool:
        """
        Update collection run status and stats.
        
        Args:
            run_id: Collection run identifier
            status: New status ("running", "completed", "failed")
            stats: Optional stats to update
            
        Returns:
            bool: True if update successful
        """
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.now(timezone.utc)
            }
            
            if stats:
                update_data["stats"] = stats
            
            if status == "completed":
                update_data["completed_at"] = datetime.now(timezone.utc)
            elif status == "failed":
                update_data["failed_at"] = datetime.now(timezone.utc)
            
            result = await self.db[self.COLLECTION_RUNS].update_one(
                {"run_id": run_id},
                {"$set": update_data}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error updating collection run status: {e}")
            return False
    
    async def get_collection_run(self, run_id: str) -> Optional[Dict]:
        """Get collection run by ID."""
        try:
            return await self.db[self.COLLECTION_RUNS].find_one({"run_id": run_id})
        except Exception as e:
            logger.error(f"Error getting collection run: {e}")
            return None
    
    async def get_latest_run(self, run_type: str = None) -> Optional[Dict]:
        """Get latest collection run, optionally filtered by type."""
        try:
            query = {}
            if run_type:
                query["run_type"] = run_type
            
            return await self.db[self.COLLECTION_RUNS].find_one(
                query,
                sort=[("created_at", DESCENDING)]
            )
        except Exception as e:
            logger.error(f"Error getting latest run: {e}")
            return None
    
    # AI Summaries Per Source Operations
    async def save_source_summary(self, summary_data: Dict) -> str:
        """
        Save AI summary for specific source.
        
        Args:
            summary_data: Source summary data
            
        Returns:
            str: ObjectId of saved record
        """
        try:
            summary_data["created_at"] = datetime.now(timezone.utc)
            
            result = await self.db[self.AI_SUMMARIES_PER_SOURCE].insert_one(summary_data)
            logger.info(f"Saved source summary: {summary_data.get('source_domain')}")
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Error saving source summary: {e}")
            raise
    
    async def get_run_summaries(self, run_id: str, region: str = None) -> List[Dict]:
        """Get all source summaries for a run, optionally filtered by region."""
        try:
            query = {"run_id": run_id}
            if region:
                query["region"] = region
            
            cursor = self.db[self.AI_SUMMARIES_PER_SOURCE].find(query)
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Error getting run summaries: {e}")
            return []
    
    # AI Aggregated Results Operations
    async def save_aggregated_result(self, aggregated_data: Dict) -> str:
        """
        Save regional aggregation result.
        
        Args:
            aggregated_data: Aggregated data
            
        Returns:
            str: ObjectId of saved record
        """
        try:
            aggregated_data["created_at"] = datetime.now(timezone.utc)
            
            result = await self.db[self.AI_AGGREGATED_RESULTS].insert_one(aggregated_data)
            logger.info(f"Saved aggregated result: {aggregated_data.get('region')}")
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Error saving aggregated result: {e}")
            raise
    
    async def get_aggregated_result(self, run_id: str, region: str, aggregation_type: str = "scraped_only") -> Optional[Dict]:
        """Get aggregated result for region and type."""
        try:
            return await self.db[self.AI_AGGREGATED_RESULTS].find_one({
                "run_id": run_id,
                "region": region,
                "aggregation_type": aggregation_type
            })
        except Exception as e:
            logger.error(f"Error getting aggregated result: {e}")
            return None
    
    # AI Diff Results Operations
    async def save_diff_result(self, diff_data: Dict) -> str:
        """
        Save AI diff analysis result.
        
        Args:
            diff_data: Diff analysis data
            
        Returns:
            str: ObjectId of saved record
        """
        try:
            diff_data["created_at"] = datetime.now(timezone.utc)
            
            result = await self.db[self.AI_DIFF_RESULTS].insert_one(diff_data)
            logger.info(f"Saved diff result for run: {diff_data.get('run_id')}")
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Error saving diff result: {e}")
            raise
    
    async def get_diff_result(self, run_id: str) -> Optional[Dict]:
        """Get diff analysis result for run."""
        try:
            return await self.db[self.AI_DIFF_RESULTS].find_one({"run_id": run_id})
        except Exception as e:
            logger.error(f"Error getting diff result: {e}")
            return None
    
    # NewsAPI Data Operations
    async def save_newsapi_data(self, newsapi_data: Dict) -> str:
        """
        Save NewsAPI fetched data.
        
        Args:
            newsapi_data: NewsAPI data
            
        Returns:
            str: ObjectId of saved record
        """
        try:
            newsapi_data["fetch_timestamp"] = datetime.now(timezone.utc)
            
            result = await self.db[self.NEWSAPI_DATA].insert_one(newsapi_data)
            logger.info(f"Saved NewsAPI data for run: {newsapi_data.get('run_id')}")
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Error saving NewsAPI data: {e}")
            raise
    
    async def get_newsapi_data(self, run_id: str) -> Optional[Dict]:
        """Get NewsAPI data for run."""
        try:
            return await self.db[self.NEWSAPI_DATA].find_one({"run_id": run_id})
        except Exception as e:
            logger.error(f"Error getting NewsAPI data: {e}")
            return None
    
    # Post-related operations
    async def save_prepared_post(self, post_data: Dict) -> str:
        """
        Save a prepared social media post.
        """
        try:
            post_data["created_at"] = datetime.now(timezone.utc)
            
            result = await self.db[self.AI_POSTS].insert_one(post_data)
            logger.info(f"Saved prepared post: {post_data.get('post_id')}")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error saving prepared post: {e}")
            raise

    async def get_prepared_posts(self, limit: int = 10, status: str = None) -> List[Dict]:
        """
        Get prepared posts, optionally filtered by status.
        """
        try:
            query = {}
            if status:
                query["post_status"] = status
            
            cursor = self.db[self.AI_POSTS].find(query).sort("created_at", DESCENDING).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error getting prepared posts: {e}")
            return []

    async def update_post_status(self, post_id: str, status: str, x_post_id: str = None) -> bool:
        """
        Update post status and optionally set X/Twitter post ID.
        """
        try:
            update_data = {
                "post_status": status,
                "updated_at": datetime.now(timezone.utc)
            }
            
            if status == "published":
                update_data["published_at"] = datetime.now(timezone.utc)
                if x_post_id:
                    update_data["x_post_id"] = x_post_id
            
            result = await self.db[self.AI_POSTS].update_one(
                {"post_id": post_id},
                {"$set": update_data}
            )
            
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating post status: {e}")
            return False

    async def get_posts_by_articles(self, article_ids: List[str]) -> List[Dict]:
        """
        Get posts that were created based on specific articles.
        """
        try:
            cursor = self.db[self.AI_POSTS].find({
                "based_on_articles": {"$in": article_ids}
            }).sort("created_at", DESCENDING)
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Error getting posts by articles: {e}")
            return []

    async def get_regional_articles(self, region: str, days: int = 7, limit: int = 100) -> Dict:
        """
        Get articles by region for the last N days.
        """
        try:
            since_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            cursor = self.db[self.AI_AGGREGATED_RESULTS].find({
                "region": region,
                "created_at": {"$gte": since_date}
            }).sort("created_at", DESCENDING)
            
            results = await cursor.to_list(length=limit)
            
            # Flatten articles from all results
            all_articles = []
            source_count = 0
            
            for result in results:
                articles = result.get("aggregated_data", {}).get("processed_articles", [])
                all_articles.extend(articles[:limit - len(all_articles)])
                
                sources = result.get("sources_processed", [])
                source_count += len(sources)
                
                if len(all_articles) >= limit:
                    break
            
            return {
                "articles": all_articles,
                "pagination": {
                    "total": len(all_articles),
                    "limit": limit,
                    "has_more": len(results) > limit
                },
                "summary": {
                    "region": region,
                    "days": days,
                    "total": len(all_articles),
                    "sources": source_count
                }
            }
        except Exception as e:
            logger.error(f"Error getting regional articles: {e}")
            return {"articles": [], "pagination": {}, "summary": {}}
    
    # Article retrieval operations
    async def get_articles_by_source(self, run_id: str, source_domain: str) -> List[Dict]:
        """
        Get articles from a specific source for a run.
        
        Args:
            run_id: Collection run identifier
            source_domain: Source domain (e.g., www_fanatik_com)
        
        Returns:
            List of article objects
        """
        try:
            summary = await self.db[self.AI_SUMMARIES_PER_SOURCE].find_one({
                "run_id": run_id,
                "source_domain": source_domain
            })
            
            if not summary:
                return []
            
            return summary.get("summary_data", {}).get("processed_articles", [])
        except Exception as e:
            logger.error(f"Error getting articles by source: {e}")
            return []
    
    async def search_articles(self, query: str, run_id: str = None) -> List[Dict]:
        """
        Search articles across runs using text search.
        
        Args:
            query: Search query
            run_id: Optional run ID to limit search scope
            
        Returns:
            List of matching article objects
        """
        try:
            # Create aggregation pipeline to search within nested articles
            pipeline = [
                {"$unwind": "$summary_data.processed_articles"},
                {
                    "$match": {
                        "$or": [
                            {"summary_data.processed_articles.title": {"$regex": query, "$options": "i"}},
                            {"summary_data.processed_articles.summary": {"$regex": query, "$options": "i"}},
                            {"summary_data.processed_articles.key_entities.teams": {"$regex": query, "$options": "i"}},
                            {"summary_data.processed_articles.key_entities.players": {"$regex": query, "$options": "i"}}
                        ]
                    }
                },
                {"$replaceRoot": {"newRoot": "$summary_data.processed_articles"}}
            ]
            
            if run_id:
                pipeline.insert(0, {"$match": {"run_id": run_id}})
            
            cursor = self.db[self.AI_SUMMARIES_PER_SOURCE].aggregate(pipeline)
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Error searching articles: {e}")
            return []

    async def get_missing_entities(self, run_id: str) -> List[str]:
        """
        Get missing entities from diff analysis for targeting.
        
        Args:
            run_id: Collection run identifier
        
        Returns:
            List of entity names that are missing in TR but present in EU
        """
        try:
            diff_result = await self.get_diff_result(run_id)
            if not diff_result:
                return []
            
            return diff_result.get("diff_analysis", {}).get("entities_in_eu_only", [])
        except Exception as e:
            logger.error(f"Error getting missing entities: {e}")
            return []
    
    # Additional methods needed by Collection Orchestrator
    async def create_collection_run(self, run_data: Dict) -> str:
        """
        Create a new collection run.
        Alias for save_collection_run for consistency with orchestrator.
        
        Args:
            run_data: Collection run data
            
        Returns:
            str: run_id of created record
        """
        return await self.save_collection_run(run_data)
    
    async def save_ai_summary_per_source(self, summary_data: Dict):
        """
        Save AI summary per source data.
        Alias for save_source_summary for consistency with orchestrator.
        
        Args:
            summary_data: AI summary data
            
        Returns:
            InsertOneResult: MongoDB insert result
        """
        try:
            summary_data["created_at"] = datetime.now(timezone.utc)
            result = await self.db[self.AI_SUMMARIES_PER_SOURCE].insert_one(summary_data)
            logger.info(f"Saved AI summary for source: {summary_data.get('source_domain')}")
            return result
        except Exception as e:
            logger.error(f"Error saving AI summary per source: {e}")
            raise
    
    async def update_collection_run(self, run_id: str, update_data: Dict) -> bool:
        """
        Update collection run with arbitrary data.
        More flexible version of update_collection_run_status.
        
        Args:
            run_id: Collection run identifier
            update_data: Data to update
            
        Returns:
            bool: True if updated successfully
        """
        try:
            result = await self.db[self.COLLECTION_RUNS].update_one(
                {"run_id": run_id},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"Updated collection run: {run_id}")
                return True
            else:
                logger.warning(f"No collection run found to update: {run_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating collection run: {e}")
            return False
    
    async def list_collection_runs(self, limit: int = 10, run_type: str = None) -> List[Dict]:
        """
        List recent collection runs.
        
        Args:
            limit: Maximum number of runs to return
            run_type: Optional filter by run type
            
        Returns:
            List[Dict]: Recent collection runs
        """
        try:
            query = {}
            if run_type:
                query["type"] = run_type
            
            cursor = self.db[self.COLLECTION_RUNS].find(query).sort("created_at", DESCENDING).limit(limit)
            runs = await cursor.to_list(length=limit)
            
            # Convert ObjectId to string for JSON serialization
            for run in runs:
                if "_id" in run:
                    run["_id"] = str(run["_id"])
            
            return runs
            
        except Exception as e:
            logger.error(f"Error listing collection runs: {e}")
            return []
