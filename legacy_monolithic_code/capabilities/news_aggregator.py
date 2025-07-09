"""
News aggregator capability for the Turkish Sports News API.

This module handles fetching news from various sources including NewsAPI, WorldNewsAPI, FotMob, and Gnews.
"""

import os
import sys
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import asyncio  # Added for asyncio operations
import aiohttp  # Added for asynchronous HTTP requests
import pandas as pd
from soccerdata import FotMob
from werkzeug.utils import secure_filename # Added for filename sanitization

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from api.models import TimeRangeEnum
except ImportError:
    # Fallback: define TimeRangeEnum locally to avoid circular dependency
    from enum import Enum
    
    class TimeRangeEnum(str, Enum):
        """Time range options for news queries"""
        LAST_HOUR = "last_hour" 
        LAST_6_HOURS = "last_6_hours"
        LAST_12_HOURS = "last_12_hours"
        LAST_24_HOURS = "last_24_hours"
        LAST_WEEK = "last_week"
        LAST_MONTH = "last_month"
        CUSTOM = "custom"

logger = logging.getLogger(__name__)


class NewsAggregator:
    """News aggregator for Turkish sports news"""
    
    def __init__(self, newsapi_key: str, worldnewsapi_key: Optional[str] = None, 
                 gnews_api_key: Optional[str] = None, cache_dir: str = "./cache", 
                 cache_expiration_hours: int = 1, enable_cache: bool = True):
        """Initialize the news aggregator"""
        self.newsapi_key = newsapi_key
        self.worldnewsapi_key = worldnewsapi_key
        self.gnews_api_key = gnews_api_key
        self.cache_dir = cache_dir
        self.cache_expiration_hours = cache_expiration_hours
        self.enable_cache = enable_cache
        self.seen_articles: Set[str] = set()
        # self.default_keywords = ["Turkey", "Fenerbahçe"] # Removed: Keywords will be passed explicitly
        self.additional_keywords = [] # This will store the keywords passed for the current operation
        self.team_ids = [8650]  # Default: Fenerbahçe
        self.languages = ["tr", "en"]
        self.domains = []
        self.max_results = 50 # Default max results for the class instance, can be configured
        self.time_range = TimeRangeEnum.LAST_24_HOURS # Default time_range for the class instance, can be configured
        self.custom_start_date = None
        self.custom_end_date = None
        
        # Create cache directory if it doesn't exist
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def configure(self, 
                 # default_keywords: Optional[List[str]] = None, # Removed default_keywords from config
                 team_ids: Optional[List[int]] = None,
                 languages: Optional[List[str]] = None,
                 domains: Optional[List[str]] = None,
                 max_results: Optional[int] = None,
                 time_range: Optional[str] = None, # Expects a string like "last_week"
                 custom_start_date: Optional[str] = None,
                 custom_end_date: Optional[str] = None) -> None:
        """Configure the news aggregator"""
        # if default_keywords is not None:
        #     self.default_keywords = default_keywords # Removed
        
        if team_ids is not None:
            self.team_ids = team_ids
            
        if languages is not None:
            self.languages = languages
            
        if domains is not None:
            self.domains = domains
            
        if max_results is not None:
            self.max_results = max_results
            
        if time_range is not None:
            try:
                # Convert the incoming string value to the TimeRangeEnum member
                self.time_range = TimeRangeEnum(time_range) 
                logger.info(f"NewsAggregator: self.time_range set to enum member: {self.time_range} from string '{time_range}'")
            except ValueError:
                # If the string is not a valid value for TimeRangeEnum, log a warning
                # and keep the existing self.time_range.
                logger.warning(
                    f"Invalid time_range string '{time_range}' received in configure. "
                    f"Valid values are: {[e.value for e in TimeRangeEnum]}. " # Assumes TimeRangeEnum is imported
                    f"Keeping existing time_range: {self.time_range}"
                )
            
        if custom_start_date is not None:
            self.custom_start_date = custom_start_date
            
        if custom_end_date is not None:
            self.custom_end_date = custom_end_date
        
        logger.info(f"NewsAggregator.configure: Values AFTER update: self.max_results={self.max_results}, self.time_range='{self.time_range}' (type: {type(self.time_range)})")
        logger.info(f"Configured news aggregator. Team IDs: {self.team_ids}, Max Results: {self.max_results}, Time Range: '{self.time_range}', Custom Start: {self.custom_start_date}, Custom End: {self.custom_end_date}") # Updated log
    
    def update_keywords(self, keywords: List[str]) -> None:
        """Update keywords for the current news fetching operation."""
        # Ensure keywords is a flat list of strings
        if keywords and isinstance(keywords, list) and all(isinstance(item, str) for item in keywords):
            self.additional_keywords = keywords
            logger.info(f"Updated additional keywords: {', '.join(keywords)}")
        elif keywords and isinstance(keywords, list) and len(keywords) == 1 and isinstance(keywords[0], list):
            # Handle cases where keywords might be a list containing a single list of strings
            self.additional_keywords = keywords[0]
            logger.info(f"Updated additional keywords (corrected from nested list): {', '.join(self.additional_keywords)}")
        else:
            self.additional_keywords = []
            logger.warning(f"Received invalid format for keywords: {keywords}. Setting additional_keywords to empty list.")

    def get_date_range(self) -> Dict[str, str]:
        """Get date range based on the time range setting"""
        logger.info(f"NewsAggregator.get_date_range: Evaluating with self.time_range='{self.time_range}' (type: {type(self.time_range)}).")
        now = datetime.now()
        
        if self.time_range == TimeRangeEnum.CUSTOM and self.custom_start_date and self.custom_end_date:
            return {
                "from": self.custom_start_date,
                "to": self.custom_end_date
            }
        
        # Default ranges
        if self.time_range == TimeRangeEnum.LAST_HOUR:
            from_date = now - timedelta(hours=1)
        elif self.time_range == TimeRangeEnum.LAST_6_HOURS:
            from_date = now - timedelta(hours=6)
        elif self.time_range == TimeRangeEnum.LAST_12_HOURS:
            from_date = now - timedelta(hours=12)
        elif self.time_range == TimeRangeEnum.LAST_WEEK:
            from_date = now - timedelta(days=7)
        elif self.time_range == TimeRangeEnum.LAST_MONTH:
            from_date = now - timedelta(days=30)
        else:  # Default to last 24 hours
            from_date = now - timedelta(days=1)
        
        return {
            "from": from_date.isoformat(),
            "to": now.isoformat()
        }
    
    async def fetch_newsapi_articles(self) -> List[Dict]:  # Changed to async
        """Fetch news via NewsAPI with caching"""
        cache_file = os.path.join(self.cache_dir, "newsapi_cache.json")
        
        # Create a unique cache key based on parameters
        cache_key = hashlib.md5(f"{self.additional_keywords}-{self.time_range}-{self.languages}-{self.domains}".encode()).hexdigest()
        cache_file = os.path.join(self.cache_dir, f"newsapi_{cache_key}.json")
        
        # Check for cached data
        cached_data = self._read_from_cache(cache_file)
        if cached_data:
            logger.info(f"Returning {len(cached_data)} articles from NewsAPI cache for key: {cache_key}") # Added cache key to log
            return cached_data
            
        # Use current operational keywords (set via update_keywords)
        if not self.additional_keywords:
            logger.warning("NewsAPI: No keywords provided for fetching. Returning empty list.")
            return []
        query = " OR ".join(self.additional_keywords) # Use additional_keywords which are the operational ones
        
        # Get date range
        date_range = self.get_date_range()        
        params = {
            "q": query,
            "language": self.languages[0] if self.languages else "en",  # Use single language instead of multiple
            "from": date_range["from"],
            "to": date_range["to"],
            "apiKey": self.newsapi_key,
            "pageSize": min(self.max_results, 10),  # Limit to 10 for better reliability
            "sortBy": "publishedAt",  # Add sortBy parameter
            "searchIn": "title,description"  # Add searchIn parameter
        }
        
        # Add domain filtering if specified
        if self.domains:
            params["domains"] = ",".join(self.domains)
            
        try:
            logger.info(f"Making NewsAPI request with query: {query}")
            async with aiohttp.ClientSession() as session:  # Use aiohttp
                async with session.get(
                    "https://newsapi.org/v2/everything", 
                    params=params
                ) as response:
                    response.raise_for_status()
                    data = await response.json()  # await response.json()
                    logger.debug(f"NewsAPI raw response data: {json.dumps(data, indent=2, ensure_ascii=False)}")
            
            # Format the results
            articles = [{
                "title": article.get("title"),
                "url": article.get("url"),
                "source": article.get("source", {}).get("name", "NewsAPI"),
                "published_at": article.get("publishedAt"),
                "content": article.get("description", ""),
                "image_url": article.get("urlToImage")
            } for article in data.get("articles", [])]
            
            # Cache the results
            self._write_to_cache(cache_file, articles)
            
            logger.info(f"Received {len(articles)} articles from NewsAPI")
            return articles
            
        except Exception as e:
            logger.error(f"NewsAPI Error: {str(e)}")
            return []
    
    def fetch_fotmob_articles(self) -> List[Dict]:
        """Fetch team news via SoccerData's FotMob component with caching"""
        # Create a unique cache key based on parameters
        cache_key = hashlib.md5(f"{self.team_ids}-{self.time_range}".encode()).hexdigest()
        cache_file = os.path.join(self.cache_dir, f"fotmob_{cache_key}.json")
        
        # Check for cached data
        cached_data = self._read_from_cache(cache_file)
        if cached_data:
            logger.info(f"Returning {len(cached_data)} articles from FotMob cache")
            return cached_data
        
        all_team_news = []
        
        try:
            logger.info("Initializing FotMob client")
            fotmob = FotMob()
            
            # Get date range
            date_range = self.get_date_range()
            from_date = datetime.fromisoformat(date_range["from"])
            
            # Fetch news for each team ID
            for team_id in self.team_ids:
                try:
                    logger.info(f"Fetching news for team ID {team_id}")
                    team_news_df = fotmob.read_news(team_id=team_id)
                    
                    # Filter by date if needed
                    if 'timestamp' in team_news_df.columns:
                        team_news_df['datetime'] = pd.to_datetime(team_news_df['timestamp'])
                        team_news_df = team_news_df[team_news_df['datetime'] >= from_date]
                    
                    # Convert DataFrame rows to dictionaries
                    team_news = [{
                        "title": row.get("title", ""),
                        "url": row.get("url", ""),
                        "source": row.get("source", "FotMob"),
                        "published_at": row.get("timestamp", ""),
                        "content": row.get("excerpt", ""),
                        "team_id": team_id
                    } for _, row in team_news_df.iterrows()]
                    
                    all_team_news.extend(team_news)
                    logger.info(f"Added {len(team_news)} articles for team ID {team_id}")
                    
                except Exception as e:
                    logger.error(f"Error fetching news for team {team_id}: {str(e)}")
            
            # Cache the results
            self._write_to_cache(cache_file, all_team_news)
            
            return all_team_news
            
        except Exception as e:
            logger.error(f"FotMob Error: {str(e)}")
            return []
    
    async def fetch_worldnewsapi_articles(self) -> List[Dict]:  # Changed to async
        """Fetch news via WorldNewsAPI with caching"""
        if not self.worldnewsapi_key:
            logger.warning("WorldNewsAPI key not provided, skipping this source")
            return []
            
        # Create a unique cache key based on parameters
        cache_key = hashlib.md5(f"worldnews-{self.additional_keywords}-{self.time_range}-{self.languages}".encode()).hexdigest()
        cache_file = os.path.join(self.cache_dir, f"worldnewsapi_{cache_key}.json")
        
        # Check for cached data
        cached_data = self._read_from_cache(cache_file)
        if cached_data:
            logger.info(f"Returning {len(cached_data)} articles from WorldNewsAPI cache for key: {cache_key}") # Added cache key to log
            return cached_data
            
        # Use current operational keywords
        if not self.additional_keywords:
            logger.warning("WorldNewsAPI: No keywords provided for fetching. Returning empty list.")
            return []
        query = " OR ".join(self.additional_keywords) # Use additional_keywords
        
        # Get date range
        date_range = self.get_date_range()
        
        params = {
            "text": query,
            "language": ",".join(self.languages),
            "earliest_publish_date": date_range["from"],
            "latest_publish_date": date_range["to"],
            "api-key": self.worldnewsapi_key,
            "number": self.max_results,
            "sort": "publish-time",
            "sort_direction": "desc"
        }
        
        # Add source domains if specified
        if self.domains:
            params["source_domains"] = ",".join(self.domains)
            
        try:
            logger.info(f"Making WorldNewsAPI request with query: {query}")
            async with aiohttp.ClientSession() as session:  # Use aiohttp
                async with session.get(
                    "https://api.worldnewsapi.com/search-news",
                    params=params
                ) as response:
                    response.raise_for_status()
                    data = await response.json()  # await response.json()
            
            # Format the results to match our standard format
            articles = [{
                "title": article.get("title"),
                "url": article.get("url"),
                "source": article.get("source_name", "WorldNewsAPI"),
                "published_at": article.get("publish_date"),
                "content": article.get("text", article.get("summary", "")),
                "image_url": article.get("image"),
                "sentiment": article.get("sentiment")  # WorldNewsAPI specific field
            } for article in data.get("news", [])]
            
            # Cache the results
            self._write_to_cache(cache_file, articles)
            
            logger.info(f"Received {len(articles)} articles from WorldNewsAPI")
            return articles
            
        except Exception as e:
            logger.error(f"WorldNewsAPI Error: {str(e)}")
            return []
    
    async def fetch_gnews_articles(self) -> List[Dict]:  # Changed to async
        """Fetch news via Gnews API with caching"""
        if not self.gnews_api_key:
            logger.warning("Gnews API key not provided, skipping this source")
            return []
            
        # Create a unique cache key based on parameters
        cache_key = hashlib.md5(f"gnews-{self.additional_keywords}-{self.time_range}-{self.languages}".encode()).hexdigest()
        cache_file = os.path.join(self.cache_dir, f"gnews_{cache_key}.json")
        
        # Check for cached data
        cached_data = self._read_from_cache(cache_file)
        if cached_data:
            logger.info(f"Returning {len(cached_data)} articles from Gnews cache for key: {cache_key}") # Added cache key to log
            return cached_data
            
        # Use current operational keywords
        if not self.additional_keywords:
            logger.warning("GNews: No keywords provided for fetching. Returning empty list.")
            return []
        query = " OR ".join(self.additional_keywords) # Use additional_keywords
        
        # Get date range
        date_range = self.get_date_range()
        from_date = datetime.fromisoformat(date_range["from"])
        
        # Format from_date as YYYY-MM-DD for Gnews API
        from_date_str = from_date.strftime("%Y-%m-%d")
        
        params = {
            "q": query,
            "lang": ",".join(self.languages),  # GNews uses 'lang' not 'language'
            "from": from_date_str,
            "apikey": self.gnews_api_key,
            "max": self.max_results,
            "sortby": "publishedAt"
        }
            
        try:
            logger.info(f"Making Gnews API request with query: {query}")
            async with aiohttp.ClientSession() as session:  # Use aiohttp
                async with session.get(
                    "https://gnews.io/api/v4/search", 
                    params=params
                ) as response:
                    response.raise_for_status()
                    data = await response.json()  # await response.json()
            
            # Format the results
            articles = [{
                "title": article.get("title"),
                "url": article.get("url"),
                "source": article.get("source", {}).get("name", "Gnews"),
                "published_at": article.get("publishedAt"),
                "content": article.get("description", ""),
                "image_url": article.get("image")
            } for article in data.get("articles", [])]
            
            # Cache the results
            self._write_to_cache(cache_file, articles)
            
            logger.info(f"Received {len(articles)} articles from Gnews API")
            return articles
            
        except Exception as e:
            logger.error(f"Gnews API Error: {str(e)}")
            return []
    
    def add_news_source(self, source_name: str, fetch_function):
        """
        Add a new news source to the aggregator
        
        Args:
            source_name: Name of the news source
            fetch_function: Function that fetches articles from the source
        """
        if not hasattr(self, '_news_sources'):
            self._news_sources = {}
            
        self._news_sources[source_name] = fetch_function
        logger.info(f"Added news source: {source_name}")
    
    async def fetch_from_source(self, source_name: str) -> List[Dict]:  # Changed to async
        """
        Fetch news from a specific source
        
        Args:
            source_name: Name of the news source
            
        Returns:
            List of articles from the source
        """
        if not hasattr(self, '_news_sources'):
            self._news_sources = {}
        
        if source_name == 'newsapi':
            return await self.fetch_newsapi_articles()  # await async call
        elif source_name == 'worldnewsapi':
            if not self.worldnewsapi_key:
                logger.warning("WorldNewsAPI key not provided, skipping this source")
                return []
            return await self.fetch_worldnewsapi_articles()  # await async call
        elif source_name == 'fotmob':
            # Fotmob uses soccerdata which is synchronous, run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.fetch_fotmob_articles)
        elif source_name == 'gnews':
            return await self.fetch_gnews_articles()  # await async call
        elif source_name in self._news_sources:
            # Assuming custom sources added via add_news_source could be async or sync
            # For simplicity, if it's a coroutine function, await it.
            # If it's a regular function, it will run synchronously.
            # A more robust solution would be to check inspect.iscoroutinefunction
            # or run sync functions in an executor.
            fetch_function = self._news_sources[source_name]
            if asyncio.iscoroutinefunction(fetch_function):
                return await fetch_function()
            else:  # Run synchronous custom source in executor
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, fetch_function)
        else:
            logger.warning(f"Unknown news source: {source_name}")
            return []
    
    def get_available_sources(self) -> List[str]:
        """
        Get list of available news sources
        
        Returns:
            List of available source names
        """
        sources = ['newsapi', 'fotmob', 'gnews']
        
        if self.worldnewsapi_key:
            sources.append('worldnewsapi')
            
        if hasattr(self, '_news_sources'):
            sources.extend(list(self._news_sources.keys()))
            
        return sorted(list(set(sources)))  # Deduplicate and sort
        
    async def get_news(self, keywords: Optional[List[str]] = None) -> List[Dict]:
        """Fetch news from all configured sources"""
        if keywords:
            self.update_keywords(keywords) # Ensure this is called with a flat list

        # Use asyncio.gather to run all fetching operations concurrently
        all_articles_lists = await asyncio.gather(
            *[self.fetch_from_source(source) for source in self.get_available_sources()]
        )
        
        # Flatten the list of lists
        all_articles = [article for sublist in all_articles_lists for article in sublist]
        
        logger.info(f"Fetched {len(all_articles)} articles from all sources")
        
        # Deduplicate articles
        unique_articles = self.deduplicate_articles(all_articles)
        
        # Sort by publication date
        sorted_articles = self.sort_articles(unique_articles)
        
        return sorted_articles
    
    def deduplicate_articles(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles based on URL hash"""
        unique_articles = []
        
        for article in articles:
            article_hash = self._hash_article(article)
            
            if article_hash not in self.seen_articles:
                self.seen_articles.add(article_hash)
                unique_articles.append(article)
        
        logger.info(f"Deduplicated {len(articles)} articles to {len(unique_articles)} unique articles")
        return unique_articles
    
    def sort_articles(self, articles: List[Dict], sort_by: str = "published_at", reverse: bool = True) -> List[Dict]:
        """Sort articles by the specified field"""
        return sorted(
            articles,
            key=lambda x: x.get(sort_by, ""),
            reverse=reverse
        )
    
    def _hash_article(self, article: Dict) -> str:
        """Create a hash for an article based on its URL"""
        url = article.get("url", "")
        return hashlib.md5(url.encode()).hexdigest()
    
    def _write_to_cache(self, cache_file: str, data: List[Dict]) -> None:
        """Write data to cache file with expiration timestamp"""
        try:
            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "data": data
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False)
            logger.debug(f"Cached {len(data)} items to {cache_file}")
        except Exception as e:
            logger.error(f"Error writing to cache: {str(e)}")
    
    def _read_from_cache(self, cache_file: str) -> Optional[List[Dict]]:
        """Read data from cache if it exists and is not expired"""
        try:
            if not os.path.exists(cache_file):
                return None
                
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            cache_time = datetime.fromisoformat(cache_data["timestamp"])
            expiration = cache_time + timedelta(hours=self.cache_expiration_hours)
            
            if datetime.now() > expiration:
                logger.debug(f"Cache expired for {cache_file}")
                return None
                
            return cache_data["data"]
        except Exception as e:
            logger.error(f"Error reading from cache: {str(e)}")
            return None

    async def fetch_news_for_session(self, session_id: str, base_workspace_path: str, query: List[str], sources: Optional[List[str]] = None, limit: Optional[int] = None) -> List[str]:
        """
        Fetches news from specified sources and saves each article to a session-specific directory.
        The 'limit' parameter here allows overriding self.max_results for this specific call.
        It's generally recommended to use `configure()` to set `max_results`.

        Args:
            session_id (str): The unique ID for this analysis session.
            base_workspace_path (str): The root directory for all workspace data.
            query (List[str]): List of keywords to search for.
            sources (Optional[List[str]]): List of sources to fetch from (e.g., ['newsapi', 'gnews']). 
                                         If None, uses all available/configured sources.
            limit (Optional[int]): If provided, this will temporarily override `self.max_results` (set via `configure()`
                                   for the API calls made *within this method execution*.
        Returns:
            List[str]: A list of absolute file paths to the saved articles.
        """
        logger.info(f"Session [{session_id}]: Starting news aggregation. Query: {query}, Sources: {sources}, Configured Max Results (at start of call): {self.max_results}, Call-specific Limit: {limit}")
        self.update_keywords(query) # Set the keywords for this run

        original_instance_max_results = self.max_results 
        
        try:
            if limit is not None:
                # Temporarily override self.max_results for this specific call's fetch operations
                self.max_results = limit 
                logger.info(f"Session [{session_id}]: Call-specific limit ({limit}) provided. Temporarily setting instance max_results to {self.max_results} for this fetch, overriding original instance default ({original_instance_max_results}).")
            else:
                # No limit provided for the call, use the already configured self.max_results
                logger.info(f"Session [{session_id}]: Using configured instance max_results: {self.max_results} for this fetch operation.")

            session_raw_articles_path = os.path.join(base_workspace_path, session_id, "raw_articles")
            os.makedirs(session_raw_articles_path, exist_ok=True)

            target_sources = sources or self.get_available_sources()
            
            fetch_tasks = []
            for source_name in target_sources:
                # fetch_from_source will use the current self.max_results value
                fetch_tasks.append(self.fetch_from_source(source_name)) 
                logger.debug(f"Session [{session_id}]: Added task for source: {source_name} with query: {query} and effective max_results for API call: {self.max_results}")

            all_articles_lists = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            
            processed_urls = set() 
            articles_saved_count = 0
            saved_article_filepaths = [] # To store paths of saved articles

            for i, result_list in enumerate(all_articles_lists):
                source_name = target_sources[i]
                if isinstance(result_list, Exception):
                    logger.error(f"Session [{session_id}]: Error fetching news from {source_name} - {result_list}", exc_info=result_list)
                    continue
                
                if not result_list:
                    logger.info(f"Session [{session_id}]: No articles found from {source_name}.")
                    continue

                logger.info(f"Session [{session_id}]: Received {len(result_list)} articles from {source_name}.")
                for article in result_list:
                    article_url = article.get("url")
                    if not article_url or article_url in processed_urls:
                        logger.debug(f"Session [{session_id}]: Skipping duplicate or invalid URL: {article_url}")
                        continue
                    
                    processed_urls.add(article_url)
                    
                    # Sanitize title for filename
                    title_for_filename = article.get("title", "untitled_article")
                    # Keep only alphanumeric, spaces, and common punc, then replace spaces/punc with underscores
                    sane_title = "".join(c if c.isalnum() or c.isspace() or c in ['-', '_'] else '' for c in title_for_filename)
                    sane_title = "_".join(sane_title.split()) # Replace spaces with underscores
                    sane_title = secure_filename(sane_title[:80]) # Limit length and further sanitize

                    # Create a unique filename
                    article_source_name = article.get("source", source_name).replace(" ", "_").lower()
                    filename_base = f"{article_source_name}_{sane_title}"
                    
                    # Ensure filename uniqueness by appending a short hash of the URL if needed, or a counter
                    # For simplicity, using a small part of the URL hash
                    url_hash_suffix = hashlib.md5(article_url.encode()).hexdigest()[:6]
                    filename = f"{filename_base}_{url_hash_suffix}.json"
                    filepath = os.path.join(session_raw_articles_path, filename)
                    
                    try:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            json.dump(article, f, ensure_ascii=False, indent=2)
                        articles_saved_count += 1
                        saved_article_filepaths.append(filepath) # Add path to list
                        logger.debug(f"Session [{session_id}]: Saved article to {filepath}")
                    except Exception as e:
                        logger.error(f"Session [{session_id}]: Error saving article {filename} - {e}", exc_info=True)
                        
            if articles_saved_count > 0: # Log actual saved count
                 logger.info(f"Session [{session_id}]: Aggregation complete. Processed articles from sources. Saved {articles_saved_count} new articles to {session_raw_articles_path}.")
            else:
                 logger.info(f"Session [{session_id}]: Aggregation complete. Processed articles from sources. No new articles were saved.")
            return saved_article_filepaths
        finally:
            # Restore self.max_results to its original value if it was temporarily changed by the limit parameter
            if limit is not None and self.max_results != original_instance_max_results:
                self.max_results = original_instance_max_results
                logger.info(f"Session [{session_id}]: Restored instance max_results to {self.max_results} after fetch operation with temporary limit.")
            elif limit is None:
                 logger.info(f"Session [{session_id}]: Instance max_results ({self.max_results}) was not changed by this call (no limit provided).")
