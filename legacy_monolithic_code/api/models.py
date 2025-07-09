"""
API data models for the Turkish Sports News API.

This module defines the data structures used for request/response handling.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator


class TimeRangeEnum(str, Enum):
    """Time range options for news queries"""
    LAST_HOUR = "last_hour" 
    LAST_6_HOURS = "last_6_hours"
    LAST_12_HOURS = "last_12_hours"
    LAST_24_HOURS = "last_24_hours"
    LAST_WEEK = "last_week"
    LAST_MONTH = "last_month"
    CUSTOM = "custom"


class NewsSourceEnum(str, Enum):
    """Available news sources"""
    NEWSAPI = "newsapi"
    WORLDNEWSAPI = "worldnewsapi"
    GNEWS = "gnews"
    FOTMOB = "fotmob"
    WEB_SCRAPING = "web_scraping"
    TWITTER = "twitter"
    ALL = "all"


class NewsArticle(BaseModel):
    """News article model"""
    title: str
    url: str
    source: str
    published_at: str
    content: Optional[str] = None
    image_url: Optional[str] = None
    team_id: Optional[int] = None
    keywords: List[str] = Field(default_factory=list)


class TrendingTopic(BaseModel):
    """Trending topic model"""
    name: str
    tweet_volume: Optional[int] = None
    relevance_score: float = 1.0
    related_keywords: List[str] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    """Request model for the main analysis endpoint"""
    keywords: List[str] = Field(default_factory=list, description="Keywords for news aggregation and analysis.")
    scrape_urls: List[str] = Field(default_factory=list, description="Specific URLs to scrape content from.")
    # client_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Client-specific configurations, e.g., for NewsAggregator.")
    use_config_defaults_as_fallback: bool = Field(default=True, description="Whether to use defaults from search_parameters.json if specific inputs are not provided by client.")
    
    # Date range parameters for NewsAggregator, with highest priority
    time_range: Optional[TimeRangeEnum] = Field(default=None, description="Time range for news articles (e.g., last_24_hours, last_week). Overrides search_parameters.json and NewsAggregator defaults.")
    custom_start_date: Optional[str] = Field(default=None, description="Custom start date in ISO format (YYYY-MM-DDTHH:mm:ss). Used if time_range is 'custom'.")
    custom_end_date: Optional[str] = Field(default=None, description="Custom end date in ISO format (YYYY-MM-DDTHH:mm:ss). Used if time_range is 'custom'.")

    @validator('custom_start_date', 'custom_end_date', pre=True)
    def validate_analysis_date_format(cls, v):
        if v:
            try:
                # Attempt to parse to validate, then return original string if valid,
                # or reformat to ensure consistency if needed.
                # For now, just ensuring it's a valid ISO format string.
                datetime.fromisoformat(v.replace("Z", "+00:00")) # Handles 'Z' for UTC
                return v 
            except (ValueError, TypeError):
                raise ValueError("Date must be in ISO format (e.g., YYYY-MM-DDTHH:mm:ss or YYYY-MM-DDTHH:mm:ssZ)")
        return v


class NewsRequest(BaseModel):
    """Request model for news search"""
    keywords: List[str] = Field(default_factory=list)
    team_ids: List[int] = Field(default=[8650])  # Default: Fenerbahçe
    languages: List[str] = Field(default=["tr", "en"])
    domains: List[str] = Field(default_factory=list)
    max_results: int = Field(default=50, ge=1, le=100)
    time_range: TimeRangeEnum = Field(default=TimeRangeEnum.LAST_24_HOURS)
    sources: List[NewsSourceEnum] = Field(default=[NewsSourceEnum.ALL])
    include_trends: bool = Field(default=True)
    scrape_urls: List[str] = Field(default_factory=list)
    custom_start_date: Optional[str] = None
    custom_end_date: Optional[str] = None
    
    @validator('custom_start_date', 'custom_end_date', pre=True)
    def validate_date_format(cls, v):
        if v:
            try:
                return datetime.fromisoformat(v).isoformat()
            except (ValueError, TypeError):
                raise ValueError("Date must be in ISO format (YYYY-MM-DDThh:mm:ss)")
        return v


class NewsResponse(BaseModel):
    """Response model for news search"""
    articles: List[NewsArticle]
    trending_topics: List[TrendingTopic] = Field(default_factory=list)
    total_count: int
    sources_used: List[str]
    query_time: float


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    code: int
    details: Optional[str] = None


class TrendingRequest(BaseModel):
    """Request model for trending topics endpoint"""
    keywords: List[str] = Field(default=["Turkey", "Fenerbahçe", "football"])
    location: str = Field(default="Turkey")
    limit: int = Field(default=10, ge=1, le=50)


class TrendingResponse(BaseModel):
    """Response model for trending topics"""
    topics: List[TrendingTopic]
    count: int
    location: str


class SessionMetadata(BaseModel):
    """Session metadata model"""
    session_id: str
    urls_requested: int
    urls_processed: int
    articles_extracted: int
    extraction_time_seconds: float
    keywords_used: List[str]
    scrape_depth: int
    persist_mode: bool
    extraction_timestamp: str
    source_specific: bool
    source_domain: str
    articles_scraped: int


class SessionDataModel(BaseModel):
    """Session data model - defines the structure of session data files"""
    source_domain: str
    source_url: str
    articles: List[Dict[str, Any]] = Field(default_factory=list)
    articles_count: int
    session_metadata: SessionMetadata


# SESSION_DATA_MODEL for reference in testing
SESSION_DATA_MODEL = {
    "source_domain": "www.fanatik.com.tr",
    "source_url": "https://www.fanatik.com.tr", 
    "articles": [],
    "articles_count": 28,
    "session_metadata": {}
}
