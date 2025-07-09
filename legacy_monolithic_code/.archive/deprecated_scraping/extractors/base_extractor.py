"""
Base extractor class for content extraction strategies.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup


class BaseExtractor(ABC):
    """Abstract base class for content extractors."""

    @abstractmethod
    async def extract(self, html_content: str, url: str) -> dict:
        """
        Extracts content from the given HTML.

        Args:
            html_content: The HTML content of the page.
            url: The URL of the page.

        Returns:
            A dictionary containing the extracted data (e.g., title, body, published_date).
            Returns an empty dictionary or a dictionary with error info if extraction fails.
        """
        pass

    def get_extraction_priority(self) -> int:
        """
        Get the priority of this extractor (lower numbers = higher priority).

        Returns:
            Priority number (1-100, where 1 is highest priority)
        """
        return 50  # Default priority