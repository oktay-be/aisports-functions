"""
News aggregator for fetching news from multiple external APIs.

Adapted from muhabir project for Cloud Function deployment.
Supports: NewsAPI, WorldNewsAPI, GNews API
"""

import os
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from enum import Enum
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


def is_content_complete(content: str) -> bool:
    """
    Check if article content is complete or truncated.

    Truncation indicators:
    - Ends with "[+N chars]" or "[N chars]"
    - Content length < 200 chars (suspiciously short)

    Args:
        content: Article content string

    Returns:
        True if content appears complete, False if truncated
    """
    if not content:
        return False

    content_stripped = content.strip()

    # Check for explicit truncation markers like "[+497 chars]" or "[497 chars]"
    if re.search(r'\[[\+]?\d+\s*chars?\]$', content_stripped):
        logger.debug(f"Content truncated (marker found): {content_stripped[-50:]}")
        return False

    # Check for suspiciously short content
    if len(content_stripped) < 200:
        logger.debug(f"Content suspiciously short: {len(content_stripped)} chars")
        return False

    return True


class TimeRangeEnum(str, Enum):
    """Time range options for news queries"""
    LAST_HOUR = "last_hour"
    LAST_6_HOURS = "last_6_hours"
    LAST_12_HOURS = "last_12_hours"
    LAST_24_HOURS = "last_24_hours"
    LAST_WEEK = "last_week"
    LAST_MONTH = "last_month"
    CUSTOM = "custom"


class NewsAggregator:
    """News aggregator for fetching news from multiple APIs"""
    
    def __init__(
        self,
        newsapi_key: Optional[str] = None,
        worldnewsapi_key: Optional[str] = None,
        gnews_api_key: Optional[str] = None,
        enable_cache: bool = False
    ):
        """Initialize the news aggregator with API keys."""
        self.newsapi_key = newsapi_key
        self.worldnewsapi_key = worldnewsapi_key
        self.gnews_api_key = gnews_api_key
        self.enable_cache = enable_cache
        
        self.seen_articles: Set[str] = set()
        self.keywords: List[str] = []
        self.languages = ["tr", "en"]
        self.domains: List[str] = []
        self.max_results = 100
        self.time_range = TimeRangeEnum.LAST_24_HOURS
        self.custom_start_date: Optional[str] = None
        self.custom_end_date: Optional[str] = None
        self.raw_responses: Dict[str, Dict] = {}  # Store raw API responses
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL for source attribution."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            # Convert domain to readable name (e.g., "thesun.co.uk" -> "The Sun")
            return domain.split('.')[0].title() if domain else "Unknown"
        except Exception:
            return "Unknown"
        
    def configure(
        self,
        languages: Optional[List[str]] = None,
        domains: Optional[List[str]] = None,
        max_results: Optional[int] = None,
        time_range: Optional[str] = None,
        custom_start_date: Optional[str] = None,
        custom_end_date: Optional[str] = None
    ) -> None:
        """Configure the news aggregator settings."""
        if languages is not None:
            self.languages = languages
            
        if domains is not None:
            self.domains = domains
            
        if max_results is not None:
            self.max_results = max_results
            
        if time_range is not None:
            try:
                self.time_range = TimeRangeEnum(time_range)
                logger.info(f"Time range set to: {self.time_range}")
            except ValueError:
                logger.warning(f"Invalid time_range '{time_range}', keeping: {self.time_range}")
            
        if custom_start_date is not None:
            self.custom_start_date = custom_start_date
            
        if custom_end_date is not None:
            self.custom_end_date = custom_end_date
        
        logger.info(f"Configured: max_results={self.max_results}, time_range={self.time_range}")
    
    def update_keywords(self, keywords: List[str]) -> None:
        """Update keywords for the current news fetching operation."""
        if keywords and isinstance(keywords, list):
            # Handle nested list case
            if len(keywords) == 1 and isinstance(keywords[0], list):
                self.keywords = keywords[0]
            else:
                self.keywords = [k for k in keywords if isinstance(k, str)]
            logger.info(f"Updated keywords: {', '.join(self.keywords)}")
        else:
            self.keywords = []
            logger.warning(f"Invalid keywords format: {keywords}")

    def get_date_range(self) -> Dict[str, str]:
        """Get date range based on the time range setting."""
        now = datetime.now()
        
        if self.time_range == TimeRangeEnum.CUSTOM and self.custom_start_date and self.custom_end_date:
            return {
                "from": self.custom_start_date,
                "to": self.custom_end_date
            }
        
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
        
        # Return date-only format (YYYY-MM-DD) for WorldNewsAPI compatibility
        return {
            "from": from_date.strftime("%Y-%m-%d"),
            "to": now.strftime("%Y-%m-%d")
        }
    
    async def fetch_newsapi_articles(self) -> List[Dict]:
        """Fetch news via NewsAPI."""
        if not self.newsapi_key:
            logger.warning("NewsAPI key not provided, skipping")
            return []
            
        if not self.keywords:
            logger.warning("NewsAPI: No keywords provided")
            return []
        
        query = " OR ".join(self.keywords)
        date_range = self.get_date_range()
        
        params = {
            "q": query,
            "language": self.languages[0] if self.languages else "en",
            "from": date_range["from"],
            "to": date_range["to"],
            "apiKey": self.newsapi_key,
            "pageSize": min(self.max_results, 100),
            "sortBy": "publishedAt",
            "searchIn": "title,description"
        }
        
        if self.domains:
            params["domains"] = ",".join(self.domains)
            
        try:
            logger.info(f"Fetching from NewsAPI with query: {query}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://newsapi.org/v2/everything",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 429:
                        logger.warning("NewsAPI rate limit reached")
                        return []
                    response.raise_for_status()
                    data = await response.json()

            # Store raw API response
            self.raw_responses['newsapi'] = data

            articles = [{
                "title": article.get("title") or "Untitled",
                "url": article.get("url"),
                "original_url": article.get("url"),
                "source": article.get("source", {}).get("name", "NewsAPI"),
                "publish_date": article.get("publishedAt"),
                "summary": article.get("description", ""),
                "content": article.get("content") or article.get("description", ""),
                "image_url": article.get("urlToImage"),
                "api_source": "newsapi",
                "language": self.languages[0] if self.languages else "en",
                "categories": [],
                "key_entities": {"competitions": [], "locations": [], "players": [], "teams": []},
                "content_quality": "medium",
                "confidence": 0.5
            } for article in data.get("articles", [])]
            
            logger.info(f"NewsAPI returned {len(articles)} articles")
            return articles
            
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                logger.warning("NewsAPI rate limit reached")
            else:
                logger.error(f"NewsAPI HTTP Error: {e}")
            return []
        except Exception as e:
            logger.error(f"NewsAPI Error: {e}")
            return []
    
    async def fetch_worldnewsapi_articles(self) -> List[Dict]:
        """Fetch news via WorldNewsAPI."""
        if not self.worldnewsapi_key:
            logger.warning("WorldNewsAPI key not provided, skipping")
            return []
            
        if not self.keywords:
            logger.warning("WorldNewsAPI: No keywords provided")
            return []
        
        query = " OR ".join(self.keywords)
        date_range = self.get_date_range()
        
        params = {
            "text": query,
            "language": ",".join(self.languages),
            "earliest-publish-date": date_range["from"],
            "latest-publish-date": date_range["to"],
            "api-key": self.worldnewsapi_key,
            "number": self.max_results,
            "sort": "publish-time",
            "sort-direction": "desc"
        }
        
        if self.domains:
            params["news-sources"] = ",".join(self.domains)
            
        try:
            logger.info(f"Fetching from WorldNewsAPI with query: {query}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.worldnewsapi.com/search-news",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 429:
                        logger.warning("WorldNewsAPI rate limit reached")
                        return []
                    response.raise_for_status()
                    data = await response.json()

            # Store raw API response
            self.raw_responses['worldnewsapi'] = data

            def get_worldnews_language(article):
                """
                Get language from WorldNewsAPI article.
                source_country has precedence over language field for determining region.
                WorldNewsAPI sometimes returns incorrect language (e.g., 'en' for Turkish articles).
                """
                source_country = article.get("source_country", "")
                # source_country takes precedence - if Turkish source, return Turkish language
                if source_country == "tr":
                    return "tr"
                # Fall back to API's language field
                return article.get("language")

            articles = [{
                "title": article.get("title") or "Untitled",
                "url": article.get("url"),
                "original_url": article.get("url"),
                "source": article.get("source_name") or self._extract_domain(article.get("url", "")),
                "publish_date": article.get("publish_date", "").replace(" ", "T") if article.get("publish_date") else "",
                "summary": article.get("summary") or article.get("text", "")[:500] if article.get("text") else "",
                "content": article.get("text", article.get("summary", "")),
                "image_url": article.get("image"),
                "sentiment": article.get("sentiment"),
                "api_source": "worldnewsapi",
                "language": get_worldnews_language(article),
                "source_country": article.get("source_country"),  # Preserve for debugging
                "categories": [article.get("category")] if article.get("category") else [],
                "key_entities": {"competitions": [], "locations": [], "players": [], "teams": []},
                "content_quality": "medium",
                "confidence": 0.5
            } for article in data.get("news", [])]
            
            logger.info(f"WorldNewsAPI returned {len(articles)} articles")
            return articles
            
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                logger.warning("WorldNewsAPI rate limit reached")
            else:
                logger.error(f"WorldNewsAPI HTTP Error: {e}")
            return []
        except Exception as e:
            logger.error(f"WorldNewsAPI Error: {e}")
            return []
    
    async def fetch_gnews_articles(self) -> List[Dict]:
        """Fetch news via GNews API."""
        if not self.gnews_api_key:
            logger.warning("GNews API key not provided, skipping")
            return []
            
        if not self.keywords:
            logger.warning("GNews: No keywords provided")
            return []
        
        query = " OR ".join(self.keywords)
        date_range = self.get_date_range()
        from_date = datetime.fromisoformat(date_range["from"])
        from_date_str = from_date.strftime("%Y-%m-%d")
        
        params = {
            "q": query,
            "lang": ",".join(self.languages),
            "from": from_date_str,
            "apikey": self.gnews_api_key,
            "max": min(self.max_results, 100),
            "sortby": "publishedAt"
        }
            
        try:
            logger.info(f"Fetching from GNews API with query: {query}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://gnews.io/api/v4/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 429:
                        logger.warning("GNews API rate limit reached")
                        return []
                    response.raise_for_status()
                    data = await response.json()

            # Store raw API response
            self.raw_responses['gnews'] = data

            articles = [{
                "title": article.get("title") or "Untitled",
                "url": article.get("url"),
                "original_url": article.get("url"),
                "source": article.get("source", {}).get("name", "GNews") if isinstance(article.get("source"), dict) else "GNews",
                "publish_date": article.get("publishedAt"),
                "summary": article.get("description", ""),
                "content": article.get("content") or article.get("description", ""),
                "image_url": article.get("image"),
                "api_source": "gnews",
                "language": article.get("lang"),  # Use API's lang field directly
                "categories": [],
                "key_entities": {"competitions": [], "locations": [], "players": [], "teams": []},
                "content_quality": "medium",
                "confidence": 0.5
            } for article in data.get("articles", [])]
            
            logger.info(f"GNews API returned {len(articles)} articles")
            return articles
            
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                logger.warning("GNews API rate limit reached")
            else:
                logger.error(f"GNews HTTP Error: {e}")
            return []
        except Exception as e:
            logger.error(f"GNews API Error: {e}")
            return []
    
    def get_available_sources(self) -> List[str]:
        """Get list of available news sources based on configured API keys."""
        sources = []

        if self.newsapi_key:
            sources.append('newsapi')
        if self.worldnewsapi_key:
            sources.append('worldnewsapi')
        if self.gnews_api_key:
            sources.append('gnews')

        return sources

    def get_raw_responses(self) -> Dict[str, Dict]:
        """Get the raw API responses from all sources."""
        return self.raw_responses

    async def get_news(self, keywords: Optional[List[str]] = None) -> List[Dict]:
        """Fetch news from all configured sources concurrently."""
        if keywords:
            self.update_keywords(keywords)

        # Build list of fetch tasks based on available API keys
        tasks = []
        if self.newsapi_key:
            tasks.append(self.fetch_newsapi_articles())
        if self.worldnewsapi_key:
            tasks.append(self.fetch_worldnewsapi_articles())
        if self.gnews_api_key:
            tasks.append(self.fetch_gnews_articles())
        
        if not tasks:
            logger.warning("No API sources available")
            return []
        
        # Fetch from all sources concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results, handling exceptions
        all_articles = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error from source {i}: {result}")
                continue
            if result:
                all_articles.extend(result)
        
        logger.info(f"Fetched {len(all_articles)} total articles from all sources")
        
        # Deduplicate and sort
        unique_articles = self.deduplicate_articles(all_articles)
        sorted_articles = self.sort_articles(unique_articles)
        
        return sorted_articles
    
    def deduplicate_articles(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles based on URL hash."""
        unique_articles = []
        
        for article in articles:
            article_hash = self._hash_article(article)
            
            if article_hash not in self.seen_articles:
                self.seen_articles.add(article_hash)
                unique_articles.append(article)
        
        logger.info(f"Deduplicated {len(articles)} -> {len(unique_articles)} unique articles")
        return unique_articles
    
    def sort_articles(self, articles: List[Dict], sort_by: str = "publish_date", reverse: bool = True) -> List[Dict]:
        """Sort articles by the specified field."""
        return sorted(
            articles,
            key=lambda x: x.get(sort_by, ""),
            reverse=reverse
        )
    
    def _hash_article(self, article: Dict) -> str:
        """Create a hash for an article based on its URL."""
        url = article.get("url", "")
        return hashlib.md5(url.encode()).hexdigest()
