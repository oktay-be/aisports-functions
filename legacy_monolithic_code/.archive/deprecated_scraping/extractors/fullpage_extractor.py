"""
Full-page content extractor.
"""

import logging
from typing import Dict, Any
from bs4 import BeautifulSoup
from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)

class FullPageExtractor(BaseExtractor):
    """Extracts the full HTML content of a page."""

    def __init__(self, config=None): # config might not be needed but kept for consistency
        """
        Initialize the full-page extractor.
        
        Args:
            config: Scraping configuration instance (optional)
        """
        self.config = config

    async def extract(self, html_content: str, url: str, soup: BeautifulSoup = None) -> Dict[str, Any]:
        """
        Extracts the full HTML content, attempting to extract a title.
        
        Args:
            html_content: Raw HTML content
            url: URL of the page
            soup: Optional pre-parsed BeautifulSoup object
            
        Returns:
            Dictionary containing the title and full HTML body.
        """
        if soup is None:
            soup = BeautifulSoup(html_content, "html.parser")

        title = ""
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
        
        # As a fallback for title, try to find the first <h1>
        if not title:
            h1_tag = soup.find('h1')
            if h1_tag and h1_tag.string:
                title = h1_tag.string.strip()

        logger.debug(f"FullPageExtractor extracted title: '{title[:100]}...' for URL: {url}")
        
        return {
            "title": title,
            "body": html_content, # Return the raw HTML content
            "extraction_method": "full_page"
        }

    def get_extraction_priority(self) -> int:
        """Get the priority of this extractor (lowest priority)."""
        return 10 # Lowest priority, as it's a fallback