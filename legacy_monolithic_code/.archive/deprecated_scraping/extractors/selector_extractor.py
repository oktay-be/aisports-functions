"""
CSS selector-based content extractor.
"""

import logging
from typing import Dict, Any
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class SelectorExtractor(BaseExtractor):
    """Extracts content using CSS selectors (site-specific and generic)."""
    
    def __init__(self, config):
        """
        Initialize the selector extractor.
        
        Args:
            config: Scraping configuration instance
        """
        self.config = config
    
    async def extract(self, html_content: str, url: str, soup: BeautifulSoup = None) -> Dict[str, Any]:
        """
        Extract content using CSS selectors.
        
        Args:
            html_content: Raw HTML content
            url: URL of the page
            soup: Optional pre-parsed BeautifulSoup object
            
        Returns:
            Dictionary containing extracted content
        """
        if soup is None:
            soup = BeautifulSoup(html_content, "html.parser")
        
        domain = urlparse(url).netloc.lower()
        selectors = self.config.get_selectors_for_domain(domain)
        
        # Extract title
        extracted_title = self._extract_title(soup, selectors, url)
        
        # Extract body
        extracted_body = self._extract_body(soup, selectors, url)
        
        result = {
            "title": extracted_title,
            "body": extracted_body,
            "extraction_method": f"css_selectors_{self._get_selector_type(domain)}"
        }
        
        logger.debug(f"Selector extractor found title: '{extracted_title[:50]}...', body length: {len(extracted_body)}")
        
        return result
    
    def _get_selector_type(self, domain: str) -> str:
        """Get the type of selectors used for a domain."""
        for site_domain in self.config.site_specific_selectors:
            if site_domain in domain:
                return "site_specific"
        return "generic"
    
    def _extract_title(self, soup: BeautifulSoup, selectors: Dict[str, str], url: str) -> str:
        """Extract title using selectors."""
        title_selector = selectors.get("title_selector", "h1")
        title_tag = soup.select_one(title_selector)
        
        if title_tag:
            title = title_tag.get_text(strip=True)
            logger.debug(f"Found title using selector '{title_selector}' for {url}")
            return title
        
        # Fallback to HTML title tag
        html_title_tag = soup.find('title')
        if html_title_tag and html_title_tag.string:
            title = html_title_tag.string.strip()
            # Remove site name if present
            for sep in [" - ", " | ", " – ", " — "]:
                if sep in title:
                    title = title.split(sep)[0]
                    break
            return title
        
        return ""
    
    def _extract_body(self, soup: BeautifulSoup, selectors: Dict[str, str], url: str) -> str:
        """Extract body content using selectors."""
        content_selector = selectors.get("content_selector", "article")
        content_tag = soup.select_one(content_selector)
        
        if content_tag:
            body_parts = self._extract_text_from_content(content_tag)
            if body_parts:
                logger.debug(f"Found body using selector '{content_selector}' for {url}")
                return "\n\n".join(body_parts)
        
        # Fallback to general content selectors
        fallback_selectors = [
            "article", ".article", ".story-content", ".entry-content",
            "div[role='main']", ".article-body", ".article-content",
            ".news-text", "main", ".content"
        ]
        
        for fallback_selector in fallback_selectors:
            content_tag = soup.select_one(fallback_selector)
            if content_tag:                # Clean out unwanted elements
                for unwanted in content_tag.find_all(['nav', 'header', 'footer', 'aside', 'script', 'style']):
                    unwanted.decompose()
                text = content_tag.get_text(separator='\n', strip=True)
                if text and len(text) > 20:  # Use same threshold as individual paragraphs
                    logger.debug(f"Found body using fallback selector '{fallback_selector}' for {url}")
                    return text
        
        return ""
    
    def _extract_text_from_content(self, content_tag) -> list[str]:
        """Extract text paragraphs from content element."""
        body_parts = []
        
        for element in content_tag.find_all(['p', 'div'], recursive=True):
            # Skip unwanted elements
            if element.name in ['nav', 'header', 'footer', 'script', 'style', 'aside', 'form']:
                continue
            
            text = element.get_text(separator='\n', strip=True)
            if text and len(text) > 20:  # Filter out short text fragments
                body_parts.append(text)
        
        # If no substantial paragraphs found, get all text from content tag
        if not body_parts:
            full_text = content_tag.get_text(separator='\n', strip=True)
            if full_text:
                body_parts.append(full_text)
        
        return body_parts
    
    def get_extraction_priority(self) -> int:
        """Get the priority of this extractor (medium priority)."""
        return 30  # Medium priority - site-specific but may miss content