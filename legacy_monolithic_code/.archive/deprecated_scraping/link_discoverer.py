"""
Link discovery for web scraping.
"""

import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import aiohttp
import asyncio # Added for TimeoutError

# Assuming ScrapingConfig might be used for things like user-agent, timeouts, or link patterns
from .config import ScrapingConfig 

logger = logging.getLogger(__name__)


class LinkDiscoverer:
    """Discovers relevant links from web pages based on keywords and site-specific patterns."""
    
    def __init__(self, max_concurrent_tasks: int = 5):
        """
        Initialize the link discoverer.
        
        Args:
            max_concurrent_tasks: Maximum concurrent discovery tasks.
        """
        self.max_concurrent_tasks = max_concurrent_tasks # Placeholder for now
        logger.info(f"LinkDiscoverer initialized. Max concurrent tasks (placeholder): {max_concurrent_tasks}")

    async def discover_links(
        self, 
        site_url: str, # Renamed from page_url for clarity, this is the entry point for a site
        keywords: List[str], 
        session: aiohttp.ClientSession,
        search_depth: int = 1, # How many levels of links to follow from the initial page
        visited_urls: Optional[set] = None # To avoid re-processing and loops
    ) -> List[Dict[str, str]]: # Return type is a list of dicts with link info
        """
        Discover relevant links starting from a given site URL, potentially following links.
        
        Args:
            site_url: The initial URL of the site/page to start discovery from.
            keywords: Keywords to filter links (case-insensitive).
            session: Active aiohttp.ClientSession for making HTTP requests.
            search_depth: How many levels deep to discover links. 0 means only the initial page.
            visited_urls: A set of already visited URLs to prevent re-fetching and loops.
            
        Returns:
            A list of unique, relevant link information dictionaries.
            Each dictionary contains: {'url': str, 'title_anchor': str, 'source_page_url': str}
        """
        if visited_urls is None:
            visited_urls = set()

        if site_url in visited_urls or search_depth < 0:
            return []

        visited_urls.add(site_url)
        discovered_links_map: Dict[str, Dict[str, str]] = {} # Use a map to store unique links by URL
        
        logger.info(f"Discovering links from {site_url} (depth: {search_depth}, keywords: {keywords})")

        try:
            html_content = await self._fetch_html(site_url, session)
            if not html_content:
                logger.warning(f"No HTML content fetched from {site_url}, cannot discover links.")
                return []
            
            soup = BeautifulSoup(html_content, "html.parser")
            base_domain = urlparse(site_url).netloc
            
            links_on_this_page = []

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                anchor_text = a_tag.get_text(strip=True)
                
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue
                
                absolute_url = urljoin(site_url, href)
                link_domain = urlparse(absolute_url).netloc

                # Basic filter: only consider links within the same domain or subdomains for now
                # More advanced logic could come from self.config (e.g., allowed_domains)
                if not link_domain.endswith(base_domain):
                    # logger.debug(f"Skipping external link: {absolute_url} (base: {base_domain})")
                    continue

                # Check if keywords match URL or anchor text
                if self._matches_keywords(absolute_url, anchor_text, keywords):
                    if absolute_url not in discovered_links_map: # Ensure uniqueness
                        link_info = {
                            "url": absolute_url,
                            "title_anchor": anchor_text,
                            "source_page_url": site_url
                        }
                        discovered_links_map[absolute_url] = link_info
                        links_on_this_page.append(absolute_url)
            
            logger.info(f"Found {len(discovered_links_map)} relevant links on page {site_url}.")            # Recursive discovery if depth allows
            if search_depth > 0:
                for link_url in links_on_this_page: # Iterate over links found on *this* page
                    if link_url not in visited_urls: # Check before recursive call
                        # logger.debug(f"Recursively discovering from {link_url} (depth left: {search_depth - 1})")
                        recursive_links = await self.discover_links(
                            link_url, keywords, session, search_depth - 1, visited_urls
                        )
                        for r_link_info in recursive_links:
                            if r_link_info['url'] not in discovered_links_map:
                                discovered_links_map[r_link_info['url']] = r_link_info
            
        except Exception as e:
            logger.error(f"Error discovering links from {site_url}: {e}", exc_info=True)
        
        final_links = list(discovered_links_map.values())
        logger.info(f"Total {len(final_links)} unique links discovered starting from {site_url} after depth {search_depth}.")
        return final_links
    
    def _matches_keywords(self, url: str, anchor_text: str, keywords: List[str]) -> bool:
        """
        Check if URL or anchor text matches keywords.
        
        Args:
            url: URL to check
            anchor_text: Anchor text to check
            keywords: Keywords to match against
            
        Returns:
            True if matches, False otherwise
        """
        if not keywords:
            return True
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if (keyword_lower in url.lower() or 
                keyword_lower in anchor_text.lower()):
                return True
        
        return False
    
    async def _fetch_html(self, url: str, session: aiohttp.ClientSession) -> Optional[str]:
        """
        Fetch HTML content from URL using settings from self.config.
        
        Args:
            url: URL to fetch
            session: HTTP session to use
              Returns:
            HTML content or None if fetch fails
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": urlparse(url).scheme + "://" + urlparse(url).netloc # Basic referer
        }
        
        timeout_seconds = 20

        try:
            # logger.debug(f"Fetching HTML from {url} with timeout {timeout_seconds}s")
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as response:
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                # Check content type to ensure it's likely HTML
                content_type = response.headers.get('Content-Type', '').lower()
                if 'html' not in content_type:
                    logger.warning(f"Fetched content from {url} is not HTML (Content-Type: {content_type}). Skipping.")
                    return None
                html = await response.text()
                # logger.debug(f"Successfully fetched HTML from {url} (length: {len(html)})")
                return html
                
        except aiohttp.ClientResponseError as e_resp:
            logger.error(f"HTTP error fetching {url}: {e_resp.status} {e_resp.message}")
        except aiohttp.ClientConnectionError as e_conn:
            logger.error(f"Connection error fetching {url}: {e_conn}")
        except asyncio.TimeoutError:
            logger.error(f"Timeout error fetching {url} after {timeout_seconds}s.")
        except Exception as e_gen:
            logger.error(f"Generic error fetching {url}: {e_gen}", exc_info=True)
        
        return None
