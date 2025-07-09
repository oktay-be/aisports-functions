"""
NewsAPI Service for AISports application.
Handles fetching and transforming NewsAPI data according to the implementation plan.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from pathlib import Path
import aiohttp
import os

logger = logging.getLogger(__name__)

class NewsAPIService:
    """
    Service for fetching and processing NewsAPI data.
    Transforms NewsAPI articles to match our standard article schema.
    """
    
    def __init__(self, api_key: str = None, cache_dir: str = "./cache"):
        """
        Initialize NewsAPI service.
        
        Args:
            api_key: NewsAPI key
            cache_dir: Directory for caching responses
        """
        self.api_key = api_key or os.getenv('NEWSAPI_KEY')
        if not self.api_key:
            logger.warning("NewsAPI key not provided. Service will not be able to fetch data.")
            
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # NewsAPI configuration
        self.base_url = "https://newsapi.org/v2"
        self.sources = os.getenv('NEWSAPI_SOURCES', 'bbc-sport,espn,four-four-two').split(',')
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def fetch_newsapi_articles(self, keywords: List[str], max_results: int = 50) -> List[Dict]:
        """
        Fetch articles from NewsAPI for given keywords.
        
        Args:
            keywords: List of keywords to search for
            max_results: Maximum number of articles to return
            
        Returns:
            List of raw NewsAPI articles
        """
        if not self.api_key:
            logger.error("NewsAPI key not configured")
            return []
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        all_articles = []
        
        # Build search query
        query = ' OR '.join(keywords)
        
        params = {
            'q': query,
            'apiKey': self.api_key,
            'language': 'en',
            'sortBy': 'publishedAt',
            'pageSize': min(max_results, 100),  # NewsAPI max is 100
            'sources': ','.join(self.sources) if self.sources else None
        }
        
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        
        try:
            url = f"{self.base_url}/everything"
            logger.info(f"Fetching NewsAPI articles: {query}")
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    articles = data.get('articles', [])
                    logger.info(f"Fetched {len(articles)} articles from NewsAPI")
                    all_articles.extend(articles[:max_results])
                elif response.status == 429:
                    logger.error("NewsAPI rate limit exceeded")
                elif response.status == 401:
                    logger.error("NewsAPI authentication failed - check API key")
                else:
                    logger.error(f"NewsAPI request failed: {response.status}")
                    
        except Exception as e:
            logger.error(f"Error fetching NewsAPI articles: {e}")
        
        return all_articles
    
    def transform_to_standard_schema(self, newsapi_articles: List[Dict]) -> List[Dict]:
        """
        Transform NewsAPI articles to our standard article schema.
        
        Args:
            newsapi_articles: Raw NewsAPI articles
            
        Returns:
            List of articles in our standard schema
        """
        transformed_articles = []
        
        for idx, article in enumerate(newsapi_articles):
            try:
                # Extract source name
                source_name = "unknown"
                if article.get('source') and article['source'].get('name'):
                    source_name = article['source']['name'].lower().replace(' ', '_')
                
                # Parse published date
                published_date = article.get('publishedAt', datetime.now(timezone.utc).isoformat())
                
                # Create transformed article
                transformed_article = {
                    "id": f"newsapi_article_{idx}_{int(datetime.now().timestamp())}",
                    "original_url": article.get('url', ''),
                    "title": article.get('title', ''),
                    "summary": article.get('description', '') or article.get('content', '')[:200] + "...",
                    "key_entities": {
                        "teams": [],
                        "players": [],
                        "amounts": [],
                        "dates": []
                    },
                    "categories": [
                        {
                            "tag": "news_article",
                            "confidence": 0.8,
                            "evidence": "NewsAPI sourced article"
                        }
                    ],
                    "source": source_name,
                    "published_date": published_date,
                    "keywords_matched": [],  # Will be populated by AI processing
                    "content_quality": "medium",  # Default for NewsAPI articles
                    "language": "english",
                    "newsapi_metadata": {
                        "author": article.get('author'),
                        "source_id": article.get('source', {}).get('id'),
                        "url_to_image": article.get('urlToImage')
                    }
                }
                
                transformed_articles.append(transformed_article)
                
            except Exception as e:
                logger.error(f"Error transforming NewsAPI article: {e}")
                continue
        
        logger.info(f"Transformed {len(transformed_articles)} NewsAPI articles to standard schema")
        return transformed_articles
    
    def _write_to_cache(self, cache_file: str, data: List[Dict]) -> None:
        """
        Write data to cache file.
        
        Args:
            cache_file: Cache file name
            data: Data to cache
        """
        try:
            cache_path = self.cache_dir / cache_file
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Cached data to {cache_path}")
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")
    
    def _read_from_cache(self, cache_file: str) -> Optional[List[Dict]]:
        """
        Read data from cache file.
        
        Args:
            cache_file: Cache file name
            
        Returns:
            Cached data or None if not found/expired
        """
        try:
            cache_path = self.cache_dir / cache_file
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.debug(f"Loaded data from cache: {cache_path}")
                return data
        except Exception as e:
            logger.error(f"Error reading from cache: {e}")
        
        return None
    
    def validate_quota(self) -> bool:
        """
        Validate that we have API quota remaining.
        
        Returns:
            True if quota is available
        """
        if not self.api_key:
            return False
        
        # NewsAPI free tier has 1000 requests per month
        # For now, just return True - could implement quota tracking
        return True
    
    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
