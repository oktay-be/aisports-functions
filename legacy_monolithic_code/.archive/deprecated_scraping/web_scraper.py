"""
Modular web scraper orchestrator that coordinates all scraping components.
Enhanced with multi-strategy content extraction including readability-lxml.
"""

import logging
import asyncio
import json
import hashlib
import os
import html
from typing import List, Dict, Optional, Any
from datetime import datetime
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from readability import Document
from werkzeug.utils import secure_filename

from .config import ScrapingConfig
from .session_manager import SessionManager
from .cache_manager import CacheManager
from .link_discoverer import LinkDiscoverer
from .content_extractor import ContentExtractor
from .file_manager import FileManager
from .network_utils import normalize_url, is_valid_url # Added

logger = logging.getLogger(__name__)


class WebScraper:
    """
    Modular web scraper that orchestrates all scraping components
    """
    
    def __init__(self, cache_dir: str, cache_expiration_hours: int = 1):
        """
        Initialize the modular web scraper
        
        Args:
            cache_dir: Directory for caching scraped content
            cache_expiration_hours: Hours before cached content expires
        """
        self.cache_dir = cache_dir
        self.cache_expiration_hours = cache_expiration_hours        # Initialize components
        self.config = ScrapingConfig()
        self.session_manager = SessionManager(self.config)
        self.cache_manager = CacheManager(cache_dir, cache_expiration_hours)
        self.link_discoverer = LinkDiscoverer(max_concurrent_tasks=3)
        self.content_extractor = ContentExtractor(self.config)
        self.file_manager = FileManager(cache_dir)
        
        # Semaphores for concurrency control
        self.discover_semaphore = asyncio.Semaphore(3)
        self.scrape_semaphore = asyncio.Semaphore(5)
        
        logger.info("Modular web scraper initialized")
    
    async def execute_scraping_for_session(self, session_id: str, keywords: List[str], 
                                         sites: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Execute complete scraping session with link discovery and content extraction
        
        Args:
            session_id: Unique identifier for this scraping session
            keywords: Keywords to search for
            sites: Optional list of specific sites to scrape
            
        Returns:
            Dict containing scraped articles and session metadata
        """
        session_start = datetime.now()
        logger.info(f"Starting scraping session {session_id} with keywords: {keywords}")
        
        try:
            # Check if session results are cached
            cached_session = self.file_manager.load_session_data(session_id)
            if cached_session:
                logger.info(f"Returning cached session data for {session_id}")
                return cached_session
            
            # Get sites to scrape
            target_sites = sites or list(self.config.site_specific_selectors.keys())
            
            # Discover links
            all_links_raw = [] # Renamed to indicate raw links before processing
            async with self.session_manager: # SessionManager handles session start/stop
                # tasks = [self._discover_links_for_site(site, keywords) for site in target_sites]
                # results = await asyncio.gather(*tasks, return_exceptions=True)
                # for i, result in enumerate(results):
                #     if isinstance(result, list):
                #         all_links_raw.extend(result)
                #         logger.info(f"Found {len(result)} raw links from {target_sites[i]}")
                #     elif isinstance(result, Exception):
                #         logger.error(f"Failed to discover links from {target_sites[i]}: {result}")
                for site in target_sites: # Sequential discovery per site for now
                    try:
                        site_links = await self._discover_links_for_site(site, keywords)
                        all_links_raw.extend(site_links)
                        logger.info(f"Discovered {len(site_links)} links from {site}")
                    except Exception as e:
                        logger.error(f"Failed to discover links from {site}: {e}")

            if not all_links_raw:
                logger.warning(f"No raw links discovered for session {session_id}")
                return {'articles': [], 'session_metadata': self._create_session_metadata(session_id, session_start, 0, 0)}
            
            logger.info(f"Total {len(all_links_raw)} raw links discovered across all sites")
            
            # Normalize and filter discovered links
            processed_links = []
            for link_info in all_links_raw: # Assuming _discover_links_for_site now returns list of dicts
                url = link_info.get('url')
                if not url:
                    logger.warning(f"Link info missing 'url': {link_info}")
                    continue
                
                normalized = normalize_url(url)
                if is_valid_url(normalized):
                    if normalized not in processed_links: # Ensure uniqueness after normalization
                        processed_links.append(normalized)
                else:
                    logger.warning(f"Skipping invalid or non-normalizable URL: {url} (normalized: {normalized})")

            if not processed_links:
                logger.warning(f"No valid links remaining after normalization and filtering for session {session_id}")
                return {'articles': [], 'session_metadata': self._create_session_metadata(session_id, session_start, 0, 0)}

            logger.info(f"Normalized and filtered to {len(processed_links)} unique, valid links.")
            
            # Scrape content from discovered links
            scraped_articles = []
            # Session is already managed by the outer context manager
            tasks = [self._scrape_single_article(link, keywords) for link in processed_links]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, dict) and result:
                    scraped_articles.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"Scraping task failed: {result}")
            
            logger.info(f"Successfully scraped {len(scraped_articles)} articles out of {len(processed_links)} links")
            
            # Prepare session results
            session_data = {
                'articles': scraped_articles,
                'session_metadata': self._create_session_metadata(
                    session_id, session_start, len(processed_links), len(scraped_articles)
                )
            }
            
            # Save session data
            self.file_manager.save_session_data(session_id, session_data)
            
            return session_data
            
        except Exception as e:
            logger.error(f"Scraping session {session_id} failed: {e}")
            return {
                'articles': [],
                'session_metadata': self._create_session_metadata(session_id, session_start, 0, 0),
                'error': str(e)
            }
    
    async def _discover_links_for_site(self, site: str, keywords: List[str]) -> List[Dict[str, Any]]: # Return list of dicts
        """Discover links for a specific site using the LinkDiscoverer module."""
        async with self.discover_semaphore:
            session = await self.session_manager.get_session() # Explicitly get session
            if not session or session.closed:
                logger.error("Session not active or closed in SessionManager, cannot discover links.")
                return []

            search_depth = self.config.link_discovery_depth if hasattr(self.config, 'link_discovery_depth') else 0
            
            # LinkDiscoverer.discover_links returns List[Dict[str, Any]]
            discovered_link_infos = await self.link_discoverer.discover_links(
                site_url=site,
                keywords=keywords,
                session=session, 
                search_depth=search_depth            )
            
            # No need to extract just URLs here, return the full info
            # Normalization and validation will happen in execute_scraping_for_session
            return discovered_link_infos
    
    async def _scrape_single_article(self, url: str, keywords: List[str]) -> Optional[Dict[str, Any]]:
        """
        Enhanced multi-strategy content extraction from a single article URL.
        Uses LD+JSON, readability-lxml, CSS selectors, and full page text as fallbacks.
        """
        
        original_url = url # Keep original for logging if needed
        normalized_url = normalize_url(url)

        if not is_valid_url(normalized_url):
            logger.warning(f"Skipping scraping for invalid or non-normalizable URL: {original_url} (normalized: {normalized_url})")
            return None

        async with self.scrape_semaphore:
            try:
                # Check cache first
                cache_key_params = {"keywords": keywords}
                # Use normalized_url for cache key generation
                cache_key = self.cache_manager.generate_cache_key(normalized_url, params=cache_key_params)
                cached_content = self.cache_manager.get_cached_content(cache_key)
                
                if cached_content:
                    logger.debug(f"Using cached content for {normalized_url} (key: {cache_key})")
                    return cached_content
                
                # Fetch content using normalized_url
                html_content = await self.session_manager.fetch_content(normalized_url)
                if not html_content:
                    logger.warning(f"Failed to fetch HTML content from {normalized_url}")
                    return None
                
                # Enhanced multi-strategy content extraction
                extracted_content = await self._extract_content_multi_strategy(normalized_url, html_content)
                if not extracted_content:
                    logger.warning(f"Failed to extract quality content from {normalized_url}")
                    return None
                
                # Prepare article data
                article_data = {
                    'url': normalized_url, # Store normalized URL
                    'original_url': original_url, # Optionally store original URL
                    'scraped_at': datetime.now().isoformat(),
                    'keywords_used': keywords,
                    'title': extracted_content.get('title', ''),
                    'content': extracted_content.get('body', ''),
                    'extraction_method': extracted_content.get('extraction_method', 'unknown'),
                    'site': urlparse(normalized_url).netloc
                }                # Cache the result
                self.cache_manager.cache_content(cache_key, article_data)
                
                # Save individual article with URL-based filename
                self._save_article_with_url_filename(article_data)
                
                return article_data
                
            except Exception as e:
                logger.error(f"Failed to scrape article {normalized_url} (original: {original_url}): {e}")
                return None

    def _decode_html_entities(self, text: str) -> str:
        """
        Decode HTML entities in text.
        
        Args:
            text: Text that may contain HTML entities
            
        Returns:
            Text with HTML entities decoded
        """
        if not text or not isinstance(text, str):
            return text
        return html.unescape(text)

    async def _extract_content_multi_strategy(self, article_url: str, html_content: str) -> Optional[Dict[str, Any]]:
        """
        Enhanced multi-strategy content extraction with proper HTML entity decoding.
        
        Strategy 1: JSON-LD structured data
        Strategy 2: Readability-lxml (key improvement for HTML entity handling)  
        Strategy 3: CSS selectors (site-specific and generic)
        Strategy 4: Full page text cleanup (last resort)
        """
        soup = BeautifulSoup(html_content, "html.parser")
        article_domain = urlparse(article_url).netloc.lower()

        extracted_title = "Untitled"
        extracted_body = ""
        extraction_method_log = []

        # Strategy 1: Try to parse application/ld+json
        try:
            ld_json_scripts = soup.find_all("script", type="application/ld+json")
            for script_tag in ld_json_scripts:
                if script_tag.string:
                    try:
                        ld_data_content = script_tag.string
                        # Remove potential leading/trailing non-JSON content
                        first_brace = ld_data_content.find('{')
                        first_bracket = ld_data_content.find('[')
                        last_brace = ld_data_content.rfind('}')
                        last_bracket = ld_data_content.rfind(']')

                        start_index = -1
                        if first_brace != -1 and first_bracket != -1:
                            start_index = min(first_brace, first_bracket)
                        elif first_brace != -1:
                            start_index = first_brace
                        elif first_bracket != -1:
                            start_index = first_bracket
                        
                        end_index = -1
                        if last_brace != -1 and last_bracket != -1:
                            end_index = max(last_brace, last_bracket)
                        elif last_brace != -1:
                            end_index = last_brace
                        elif last_bracket != -1:
                            end_index = last_bracket
                        
                        if start_index != -1 and end_index != -1 and end_index > start_index:
                            ld_data_content = ld_data_content[start_index : end_index+1]
                        
                        ld_data = json.loads(ld_data_content)
                        
                        items_to_check = []
                        if isinstance(ld_data, list):
                            items_to_check.extend(ld_data)
                        elif isinstance(ld_data, dict):
                            items_to_check.append(ld_data)
                            # Sometimes nested inside "@graph"
                            if isinstance(ld_data.get("@graph"), list):
                                items_to_check.extend(ld_data["@graph"])

                        for item in items_to_check:
                            if isinstance(item, dict):
                                item_type = item.get("@type", "")
                                if isinstance(item_type, list):
                                    item_type_str = " ".join(item_type).lower()
                                else:
                                    item_type_str = str(item_type).lower()

                                if any(t in item_type_str for t in ["newsarticle", "article", "webpage", "reportage", "blogposting"]):
                                    current_item_body = item.get("articleBody") or item.get("text") or item.get("description")
                                    current_item_title = item.get("headline") or item.get("name")

                                    if current_item_body and isinstance(current_item_body, str) and (not extracted_body or len(current_item_body) > len(extracted_body)):
                                        extracted_body = self._decode_html_entities(current_item_body) # Apply decoding
                                        extraction_method_log.append(f"ld+json:body_from_type_{item_type_str.split()[0] if item_type_str else 'unknown'}")
                                    
                                    if current_item_title and isinstance(current_item_title, str) and ((not extracted_title or extracted_title == "Untitled") or len(current_item_title) > len(extracted_title)):
                                        extracted_title = self._decode_html_entities(current_item_title) # Apply decoding
                                        extraction_method_log.append(f"ld+json:title_from_type_{item_type_str.split()[0] if item_type_str else 'unknown'}")
                        
                        # Ensure strings
                        if extracted_body and isinstance(extracted_body, list):
                            extracted_body = "\n\n".join(filter(None, [str(p) for p in extracted_body]))
                        if extracted_title and isinstance(extracted_title, list):
                            extracted_title = " ".join(filter(None, [str(t) for t in extracted_title]))

                        if extracted_body and len(extracted_body) > 100 and extracted_title and extracted_title != "Untitled":
                            logger.info(f"Extracted content via ld+json for {article_url}")
                            break 
                    except json.JSONDecodeError as e_json:
                        logger.debug(f"Failed to parse ld+json content for {article_url}: {e_json}")
                    except Exception as e_ld:
                        logger.warning(f"Error processing ld+json for {article_url}: {e_ld}")
                        
        except Exception as e:
            logger.warning(f"Outer error during ld+json processing for {article_url}: {e}")
        
        # Strategy 2: Use readability-lxml (KEY IMPROVEMENT for HTML entity handling)
        if not extracted_body or len(extracted_body) < 200: 
            if extracted_body:
                logger.info(f"ld+json body for {article_url} is short (len: {len(extracted_body)}). Trying readability.")
            else:
                logger.info(f"ld+json found no body for {article_url}. Trying readability.")
            try:
                doc = Document(html_content)
                readability_title = doc.title()
                content_html = doc.summary(html_partial=True)
                content_soup = BeautifulSoup(content_html, "html.parser")
                
                # Extract text with proper HTML entity decoding
                body_paragraphs = [p.get_text(strip=True) for p in content_soup.find_all(['p', 'div'])]
                readability_body = "\\n\\n".join(filter(None, body_paragraphs))

                if len(readability_body) > len(extracted_body):
                    extracted_body = self._decode_html_entities(readability_body) # Apply decoding
                    extraction_method_log.append("readability:body")
                
                if readability_title and ((not extracted_title or extracted_title == "Untitled" or len(extracted_title) < 10) or len(readability_title) > len(extracted_title)):
                    extracted_title = self._decode_html_entities(readability_title) # Apply decoding
                    extraction_method_log.append("readability:title")
                logger.info(f"Used readability for {article_url}. Body len: {len(extracted_body)}, Title: '{extracted_title[:50]}...'")
            except Exception as e_read:
                logger.warning(f"Error using readability-lxml for {article_url}: {e_read}")

        # Strategy 3: Fallback to CSS selectors if readability failed
        if not extracted_body or len(extracted_body) < 200:
            logger.warning(f"Readability/ld+json extracted little content for {article_url} (body len: {len(extracted_body)}). Falling back to CSS selectors.")
            
            # Get site-specific or generic selectors
            current_selectors = self.config.generic_selectors
            for site_domain_key in self.config.site_specific_selectors:
                if site_domain_key in article_domain:
                    current_selectors = self.config.site_specific_selectors[site_domain_key]
                    logger.debug(f"Using site-specific selectors for {article_domain}")
                    break

            # CSS Title extraction
            if not extracted_title or extracted_title == "Untitled" or len(extracted_title) < 10:
                title_selector_str = current_selectors.get("title_selector", self.config.generic_selectors["title_selector"])
                title_tag = soup.select_one(title_selector_str)
                css_title = title_tag.get_text(strip=True) if title_tag else "Untitled"
                if len(css_title) > len(extracted_title) or extracted_title == "Untitled":
                    extracted_title = self._decode_html_entities(css_title) # Apply decoding
                    extraction_method_log.append("css:title")

            # CSS Body extraction
            body_selector_str = current_selectors.get("content_selector", self.config.generic_selectors["content_selector"])
            content_tag = soup.select_one(body_selector_str)
            if content_tag:
                # Clean unwanted elements
                for unwanted in content_tag.find_all(['nav', 'header', 'footer', 'aside', 'script', 'style']):
                    unwanted.decompose()
                
                # Extract text with HTML entity decoding
                css_body_parts = []
                for element in content_tag.find_all(['p', 'div'], recursive=True):
                    text = element.get_text(separator='\n', strip=True)
                    if text and len(text) > 20:
                        css_body_parts.append(text)
                
                css_body = "\\n\\n".join(css_body_parts) if css_body_parts else content_tag.get_text(separator='\\n', strip=True)
                
                if len(css_body) > len(extracted_body):
                    extracted_body = self._decode_html_entities(css_body) # Apply decoding
                    extraction_method_log.append("css:body")

        # Strategy 4: Last resort - full page text cleanup
        if not extracted_body or len(extracted_body) < 100:
            logger.warning(f"All extraction strategies yielded minimal content for {article_url}. Using full page fallback.")
            
            # Remove unwanted elements
            for unwanted in soup.find_all(['nav', 'header', 'footer', 'script', 'style', 'aside']):
                unwanted.decompose()
            
            full_text = soup.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in full_text.split('\n') if line.strip() and len(line.strip()) > 10]
            
            if lines:
                # Take substantial content from middle section
                start_idx = max(0, len(lines) // 4)
                end_idx = min(len(lines), 3 * len(lines) // 4)
                selected_lines = lines[start_idx:end_idx]
                
                if selected_lines:
                    extracted_body = self._decode_html_entities("\\n".join(selected_lines)) # Apply decoding
                    extraction_method_log.append("fullpage:body")
            
            # Fallback title from HTML title tag
            if not extracted_title or extracted_title == "Untitled":
                html_title_tag = soup.find('title')
                if html_title_tag and html_title_tag.string:
                    title = html_title_tag.string.strip()
                    # Remove site name if present
                    for sep in [" - ", " | ", " – ", " — "]:
                        if sep in title:
                            title = title.split(sep)[0]
                            break
                    extracted_title = self._decode_html_entities(title) # Apply decoding
                    extraction_method_log.append("fullpage:title")

        # Quality check
        if not extracted_body or len(extracted_body) < 50:
            logger.warning(f"All extraction strategies failed for {article_url}. Final body length: {len(extracted_body)}")
            return None

        extraction_method = " -> ".join(extraction_method_log) if extraction_method_log else "unknown"
        logger.info(f"Content extraction complete for {article_url}. Method: {extraction_method}, Title: '{extracted_title[:50]}...', Body length: {len(extracted_body)}")

        return {
            "title": extracted_title,
            "body": extracted_body,
            "extraction_method": extraction_method
        }
    
    def _create_session_metadata(self, session_id: str, start_time: datetime,
                               links_found: int, articles_scraped: int) -> Dict[str, Any]:
        """Create session metadata"""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return {
            'session_id': session_id,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration,
            'links_discovered': links_found,
            'articles_scraped': articles_scraped,
            'success_rate': articles_scraped / links_found if links_found > 0 else 0,
            'scraper_version': 'modular-v1.0'
        }
    
    def get_scraper_info(self) -> Dict[str, Any]:
        """Get information about the scraper configuration"""
        return {
            'cache_dir': self.cache_dir,
            'cache_expiration_hours': self.cache_expiration_hours,
            'supported_sites': list(self.config.site_specific_selectors.keys()),
            'extraction_strategies': self.content_extractor.get_extractor_info(),
            'http_timeout': self.config.http_timeout,
            'max_retries': self.config.max_retries
        }
    
    def cleanup_old_data(self, session_days: int = 7, article_days: int = 30) -> Dict[str, int]:
        """Clean up old cached data"""
        session_cleaned = self.file_manager.cleanup_old_sessions(session_days)
        article_cleaned = self.file_manager.cleanup_old_articles(article_days)        # Use the new cleanup_expired_cache method name
        cache_cleaned = self.cache_manager.cleanup_expired_cache()
        
        return {
            'sessions_removed': session_cleaned,
            'articles_removed': article_cleaned,
            'cache_files_removed': cache_cleaned
        }
    
    def _save_article_with_url_filename(self, article_data: Dict[str, Any]) -> str:
        """
        Save article with URL-based filename for easy identification.
        
        Args:
            article_data: Article data dictionary
            
        Returns:
            Generated filename
        """
        try:
            url = article_data.get('url', '')
            if not url:
                # Fallback to cache key approach
                cache_key = hashlib.md5(json.dumps(article_data, sort_keys=True).encode()).hexdigest()
                filename = f"article_{cache_key}.json"
            else:
                filename = self._generate_url_based_filename(url, article_data.get('title', ''))
            
            # Save to cache directory
            filepath = os.path.join(self.cache_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(article_data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved article to: {filepath}")
            return filename
            
        except Exception as e:
            logger.error(f"Failed to save article with URL filename: {e}")
            # Fallback to original method
            cache_key = hashlib.md5(json.dumps(article_data, sort_keys=True).encode()).hexdigest()
            self.file_manager.save_article(cache_key, article_data)
            return cache_key

    def _generate_url_based_filename(self, url: str, title: str = "") -> str:
        """
        Generate a filename based on URL and title for easy identification.
        
        Args:
            url: Article URL
            title: Article title (optional)
            
        Returns:
            Safe filename string
        """
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.replace('www.', '')
            
            # Clean up the path
            path = parsed_url.path.strip('/')
            if path:
                # Remove file extensions and clean up
                path_parts = path.split('/')
                if path_parts:
                    # Take the last meaningful part of the path
                    last_part = path_parts[-1]
                    if '.' in last_part:
                        last_part = last_part.split('.')[0]
                    path = last_part
                else:
                    path = 'article'
            else:
                path = 'article'
            
            # Clean up title if provided
            title_part = ""
            if title:
                # Take first few words of title
                title_words = title.split()[:8]  # Limit to 8 words
                title_part = '_' + '_'.join(title_words)
                # Remove special characters
                title_part = ''.join(c for c in title_part if c.isalnum() or c in ('_', '-'))
            
            # Create timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Combine parts
            base_name = f"{domain}__{path}{title_part}_{timestamp}"
            
            # Make filename safe
            safe_name = secure_filename(base_name)
            
            # Ensure it's not too long (max 255 chars for most filesystems)
            if len(safe_name) > 200:  # Leave room for .json extension
                safe_name = safe_name[:200]
            
            return f"{safe_name}.json"
            
        except Exception as e:
            logger.error(f"Failed to generate URL-based filename for {url}: {e}")
            # Fallback to hash-based filename
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"article_{url_hash}_{timestamp}.json"

    def _generate_cache_key(self, url: str, params: Optional[Dict] = None) -> str:
        """
        Generate cache key for URL with optional parameters.
        
        Args:
            url: URL to generate key for
            params: Optional parameters to include in key
            
        Returns:
            Cache key string
        """
        key_data = {'url': url}
        if params:
            key_data.update(params)
        
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.session_manager.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.session_manager.__aexit__(exc_type, exc_val, exc_tb)