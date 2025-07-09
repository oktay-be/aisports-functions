"""
Cache management for web scraping.
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages caching for web scraping operations."""
    
    def __init__(self, cache_dir: str, cache_expiration_hours: int = 24, config: Optional[Any] = None):
        """
        Initialize the cache manager.
        
        Args:
            cache_dir: Directory for cache storage
            cache_expiration_hours: Hours before cache expires
            config: Optional ScrapingConfig object for more advanced cache key generation
        """
        self.cache_dir = cache_dir
        self.cache_expiration_hours = cache_expiration_hours
        self.config = config # Store the config if provided
        os.makedirs(cache_dir, exist_ok=True)
        logger.info(f"CacheManager initialized. Cache directory: {self.cache_dir}, Expiration: {self.cache_expiration_hours} hours.")
    
    def generate_cache_key(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate a cache key for a URL and optional parameters.
        The `params` dictionary can include things like keywords, language, or other query specifics.
        
        Args:
            url: URL to cache
            params: Optional dictionary of parameters that affect the content (e.g., keywords, filters)
            
        Returns:
            Cache key string (MD5 hash)
        """
        # Start with the URL
        key_parts = [url]
        
        # Add sorted params to ensure consistent key generation
        if params:
            for k, v in sorted(params.items()):
                # Normalize list values by sorting them and joining
                if isinstance(v, list):
                    key_parts.append(f"{k}:{'|'.join(sorted(map(str, v)))}")
                else:
                    key_parts.append(f"{k}:{str(v)}")
        
        # Consider domain-specific cache variations from config if available
        # This is a placeholder for more advanced logic if self.config is used
        # For example, if config specifies certain query params to ignore for a domain.
        # if self.config and hasattr(self.config, 'get_cache_key_variations_for_domain'):
        #     domain = urlparse(url).netloc
        #     variations = self.config.get_cache_key_variations_for_domain(domain)
        #     # Apply variations as needed

        cache_key_str = "-".join(key_parts)
        return hashlib.md5(cache_key_str.encode('utf-8')).hexdigest()
    
    def _get_cache_file_path(self, cache_key: str) -> str:
        """
        Get the file path for a cache key.
        
        Args:
            cache_key: Cache key
            
        Returns:
            Full path to cache file
        """
        return os.path.join(self.cache_dir, f"article_{cache_key}.json")
    
    def get_cached_content(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached content if it exists and is not expired.
        Uses the pre-generated cache_key.
        
        Args:
            cache_key: The pre-generated cache key for the content.
            
        Returns:
            Cached content data or None
        """
        # cache_key = self._generate_cache_key(url, keywords) # This line is removed as key is pre-generated
        cache_file = self._get_cache_file_path(cache_key)
        
        try:
            if not os.path.exists(cache_file):
                logger.debug(f"Cache miss (file not found) for key: {cache_key}")
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Ensure timestamp exists
            timestamp_str = cache_data.get("timestamp")
            if not timestamp_str:
                logger.warning(f"Cache file {cache_file} for key {cache_key} is missing timestamp. Discarding.")
                os.remove(cache_file)
                return None

            cache_time = datetime.fromisoformat(timestamp_str)
            # Use self.cache_expiration_hours which should be an int
            expiration_delta = timedelta(hours=int(self.cache_expiration_hours))
            
            if datetime.now() > (cache_time + expiration_delta):
                logger.info(f"Cache expired for key: {cache_key} (file: {cache_file})")
                try:
                    os.remove(cache_file)
                except OSError as e_rem:
                    logger.error(f"Error removing expired cache file {cache_file}: {e_rem}")
                return None
            
            logger.debug(f"Cache hit for key: {cache_key}")
            return cache_data.get("data") # Use .get for safety
            
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from cache file {cache_file} (key: {cache_key}): {e}")
            try:
                os.remove(cache_file)
            except OSError as e_rem:
                logger.error(f"Error removing corrupted cache file {cache_file}: {e_rem}")
        except Exception as e:
            logger.error(f"Error reading from cache file {cache_file} (key: {cache_key}): {e}")
        
        return None
    
    def cache_content(self, cache_key: str, content_data: Dict[str, Any]) -> bool:
        """
        Cache content data using a pre-generated key.
        
        Args:
            cache_key: The pre-generated cache key for the content.
            content_data: Content data to cache
            
        Returns:
            True if cached successfully, False otherwise
        """
        # cache_key = self._generate_cache_key(url, keywords) # This line is removed
        cache_file = self._get_cache_file_path(cache_key)
        
        try:
            cache_payload = {
                "timestamp": datetime.now().isoformat(),
                "data": content_data
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_payload, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Cached content with key: {cache_key} to file: {cache_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing to cache file {cache_file} (key: {cache_key}): {e}")
            return False
    
    def cleanup_expired_cache(self) -> int: # Renamed from clear_expired_cache for consistency
        """
        Clear all expired cache files from the cache directory.
        
        Returns:
            Number of files removed
        """
        removed_count = 0
        files_processed = 0
        now = datetime.now()
        expiration_delta = timedelta(hours=int(self.cache_expiration_hours))

        try:
            for filename in os.listdir(self.cache_dir):
                # Process only files matching the expected cache file pattern
                if filename.startswith("article_") and filename.endswith(".json"):
                    files_processed += 1
                    filepath = os.path.join(self.cache_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            cache_data = json.load(f)
                        
                        timestamp_str = cache_data.get("timestamp")
                        if not timestamp_str:
                            logger.warning(f"Cache file {filepath} is missing timestamp. Removing.")
                            os.remove(filepath)
                            removed_count += 1
                            continue

                        cache_time = datetime.fromisoformat(timestamp_str)
                        
                        if now > (cache_time + expiration_delta):
                            logger.info(f"Removing expired cache file: {filepath}")
                            os.remove(filepath)
                            removed_count += 1
                            
                    except json.JSONDecodeError:
                        logger.warning(f"Corrupted JSON in cache file {filepath}. Removing.")
                        try:
                            os.remove(filepath)
                            removed_count += 1
                        except OSError as e_rem:
                            logger.error(f"Error removing corrupted cache file {filepath}: {e_rem}")
                    except Exception as e:
                        logger.warning(f"Error processing cache file {filepath}, may be corrupted or malformed: {e}. Removing.")
                        # Attempt to remove problematic file
                        try:
                            os.remove(filepath)
                            removed_count += 1
                        except OSError as e_rem:
                            logger.error(f"Error removing problematic cache file {filepath}: {e_rem}")
            
            logger.info(f"Cache cleanup processed {files_processed} files. Removed {removed_count} expired or problematic cache files.")
                
        except Exception as e:
            logger.error(f"Error during cache cleanup in directory {self.cache_dir}: {e}")
        
        return removed_count

    # Alias for backward compatibility if needed, or for clarity in web_scraper.py
    # This matches the method name used in web_scraper.py
    def generate_cache_key_for_article(self, url: str, keywords: List[str]) -> str:
        """Generates a cache key specifically for an article URL and keywords."""
        return self.generate_cache_key(url, params={"keywords": keywords})

    # The methods get_cached_article and cache_article were renamed to 
    # get_cached_content and cache_content respectively to be more generic,
    # as the CacheManager might store things other than just articles in the future.
    # If web_scraper.py specifically calls get_cached_article, we can add aliases or update web_scraper.py.
    # For now, assuming web_scraper.py will be updated to use generate_cache_key and get_cached_content.