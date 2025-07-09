"""
Init file for the capabilities package.
"""

from capabilities.news_aggregator import NewsAggregator
from capabilities.trends_analyzer import TrendsAnalyzer
from capabilities.content_scraping_service import Journalist, JOURNALIST_AVAILABLE

__all__ = ['NewsAggregator', 'TrendsAnalyzer', 'Journalist', 'JOURNALIST_AVAILABLE']
