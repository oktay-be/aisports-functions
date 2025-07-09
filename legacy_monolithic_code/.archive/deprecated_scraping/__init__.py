"""
Modular web scraping package for Turkish sports news.
"""

from .web_scraper import WebScraper
from .config import ScrapingConfig
from .session_manager import SessionManager
from .cache_manager import CacheManager
from .link_discoverer import LinkDiscoverer
from .content_extractor import ContentExtractor
from .file_manager import FileManager

__all__ = [
    'WebScraper',
    'ScrapingConfig',
    'SessionManager', 
    'CacheManager',
    'LinkDiscoverer',
    'ContentExtractor',
    'FileManager'
]

__version__ = '1.0.0'