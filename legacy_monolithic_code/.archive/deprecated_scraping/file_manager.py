"""
File management operations for web scraping sessions and article persistence.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


class FileManager:
    """Manages file operations for scraping sessions and article storage"""
    
    def __init__(self, base_data_dir: str):
        """
        Initialize the FileManager.
        Args:
            base_data_dir: The root directory where session and article data will be stored.
                         Subdirectories 'sessions' and 'articles' will be created here.
        """
        self.base_data_dir = base_data_dir
        self.session_dir = os.path.join(self.base_data_dir, 'sessions')
        self.articles_dir = os.path.join(self.base_data_dir, 'articles')
        
        # Ensure directories exist
        try:
            os.makedirs(self.base_data_dir, exist_ok=True)
            os.makedirs(self.session_dir, exist_ok=True)
            os.makedirs(self.articles_dir, exist_ok=True)
            logger.info(f"FileManager initialized. Session dir: {self.session_dir}, Articles dir: {self.articles_dir}")
        except OSError as e:
            logger.error(f"Error creating directories for FileManager at {self.base_data_dir}: {e}")
            # Depending on desired behavior, could raise an exception here
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitizes a string to be used as a filename component."""
        # Use a more robust sanitization than just secure_filename if needed,
        # especially if names can be very long or have many special chars.
        # For now, secure_filename is a good start.
        # Limit length to avoid issues with max path length on some OS.
        # Max filename length is often 255, but keep it shorter for safety.
        return secure_filename(name)[:100] # Limit sanitized name length

    def _get_session_file_path(self, session_id: str) -> str:
        """Get the file path for a session, using sanitized session_id."""
        safe_session_id = self._sanitize_filename(session_id)
        return os.path.join(self.session_dir, f"session_{safe_session_id}.json")

    def _get_article_file_path(self, article_id: str) -> str:
        """Get the file path for an article, using sanitized article_id."""
        # article_id is often a hash, which is already safe, but sanitize just in case.
        safe_article_id = self._sanitize_filename(article_id)
        return os.path.join(self.articles_dir, f"article_{safe_article_id}.json")

    def save_json_data(self, file_path: str, data: Dict[str, Any], data_type: str = "data") -> bool:
        """
        Generic method to save dictionary data to a JSON file.
        
        Args:
            file_path: Full path to the file where data should be saved.
            data: The dictionary data to save.
            data_type: A string describing the type of data (e.g., "session", "article") for logging.
            
        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            # Create directory if it doesn't exist (e.g., if a new session_id creates a new path pattern)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Successfully saved {data_type} to {file_path}")
            return True
        except IOError as e:
            logger.error(f"IOError saving {data_type} to {file_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error saving {data_type} to {file_path}: {e}")
        return False

    def load_json_data(self, file_path: str, data_type: str = "data") -> Optional[Dict[str, Any]]:
        """
        Generic method to load dictionary data from a JSON file.
        
        Args:
            file_path: Full path to the file from which data should be loaded.
            data_type: A string describing the type of data (e.g., "session", "article") for logging.

        Returns:
            Loaded dictionary data or None if an error occurs or file not found.
        """
        if not os.path.exists(file_path):
            logger.debug(f"{data_type.capitalize()} file not found: {file_path}")
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Successfully loaded {data_type} from {file_path}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"JSONDecodeError loading {data_type} from {file_path}: {e}. File might be corrupted.")
            # Optionally, attempt to delete or move corrupted file
        except IOError as e:
            logger.error(f"IOError loading {data_type} from {file_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading {data_type} from {file_path}: {e}")
        return None

    def save_session_data(self, session_id: str, data: Dict[str, Any]) -> bool:
        """
        Save session data to file, including a timestamp
        
        Args:
            session_id: Unique session identifier
            data: Session data to save
            
        Returns:
            True if saved successfully
        """
        try:
            session_file = self._get_session_file_path(session_id)
            
            # Add metadata (timestamp is now part of the main data to be saved by generic method)
            session_payload = {
                'session_id': session_id,
                'saved_at': datetime.now().isoformat(), # Renamed for clarity
                'payload': data # Original data nested under 'payload'
            }
            return self.save_json_data(session_file, session_payload, data_type="session")
            
        except Exception as e:
            logger.error(f"Failed to prepare session data for {session_id}: {e}")
            return False
    
    def load_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load session data from file. Returns the 'payload' part of the stored data
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Session data dict or None if not found
        """
        try:
            session_file = self._get_session_file_path(session_id)
            loaded_data = self.load_json_data(session_file, data_type="session")
            if loaded_data and isinstance(loaded_data, dict):
                # Verify session_id matches, if needed
                if loaded_data.get('session_id') != session_id:
                    logger.warning(f"Session ID mismatch in file {session_file}. Expected {session_id}, found {loaded_data.get('session_id')}")
                    # Decide if this is an error or just a note
                return loaded_data.get('payload') # Return the original data
            return None
            
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None
    
    def save_article(self, article_id: str, article_data: Dict[str, Any]) -> bool:
        """
        Save individual article data, including a timestamp
        
        Args:
            article_id: Unique article identifier (usually URL hash)
            article_data: Article content and metadata
            
        Returns:
            True if saved successfully
        """
        try:
            article_file = self._get_article_file_path(article_id)
            
            # Add metadata (timestamp is now part of the main data)
            # The article_data itself should contain 'scraped_at' as per web_scraper.py
            # We can add an 'article_id_meta' for consistency if desired.
            article_payload = {
                'article_id_meta': article_id, # Storing the id used for filename
                'file_saved_at': datetime.now().isoformat(),
                **article_data # Spread the original article data
            }
            return self.save_json_data(article_file, article_payload, data_type="article")
            
        except Exception as e:
            logger.error(f"Failed to prepare article data {article_id}: {e}")
            return False
    
    def load_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """
        Load individual article data
        
        Args:
            article_id: Unique article identifier
            
        Returns:
            Article data dict or None if not found
        """
        try:
            article_file = self._get_article_file_path(article_id)
            # The loaded data is the full payload including our metadata + original article_data
            loaded_payload = self.load_json_data(article_file, data_type="article")
            # If we want to return just the original article_data (without our 'article_id_meta' and 'file_saved_at')
            # we would need to reconstruct it. For now, return the full saved structure.
            return loaded_payload
            
        except Exception as e:
            logger.error(f"Failed to load article {article_id}: {e}")
            return None
    
    def cleanup_old_files(self, directory: str, days_old: int, file_prefix: Optional[str] = None) -> int:
        """
        Generic method to clean up files older than specified days in a directory.
        
        Args:
            directory: The directory to clean up.
            days_old: Remove files older than this many days based on modification time.
            file_prefix: Optional prefix to filter files (e.g., "session_", "article_").
            
        Returns:
            Number of files removed.
        """
        if not os.path.isdir(directory):
            logger.warning(f"Cleanup directory {directory} does not exist. Skipping cleanup.")
            return 0

        try:
            import time # Keep import local to method if not used elsewhere extensively
            cutoff_time = time.time() - (days_old * 24 * 60 * 60)
            removed_count = 0
            files_processed = 0
            
            for filename in os.listdir(directory):
                if file_prefix and not filename.startswith(file_prefix):
                    continue
                if not filename.endswith('.json'): # Assuming we only manage .json files this way
                    continue

                files_processed += 1
                file_path = os.path.join(directory, filename)
                try:
                    if os.path.isfile(file_path): # Ensure it's a file
                        if os.path.getmtime(file_path) < cutoff_time:
                            os.remove(file_path)
                            removed_count += 1
                            logger.debug(f"Removed old file: {file_path}")
                except FileNotFoundError:
                    logger.debug(f"File {file_path} not found during cleanup (possibly removed by another process). Skipping.")
                except Exception as e_file:
                    logger.error(f"Error processing file {file_path} during cleanup: {e_file}")
            
            logger.info(f"Cleanup in {directory} (prefix: {file_prefix or '*'}): Processed {files_processed} files, removed {removed_count} old files.")
            return removed_count
            
        except Exception as e_main:
            logger.error(f"Failed to cleanup old files in {directory}: {e_main}")
            return 0

    def cleanup_old_sessions(self, days_old: int = 7) -> int:
        """
        Clean up session files older than specified days.
        Args:
            days_old: Remove sessions older than this many days.
        Returns:
            Number of files removed.
        """
        return self.cleanup_old_files(self.session_dir, days_old, file_prefix="session_")
    
    def cleanup_old_articles(self, days_old: int = 30) -> int:
        """
        Clean up article files older than specified days.
        Args:
            days_old: Remove articles older than this many days.
        Returns:
            Number of files removed.
        """
        return self.cleanup_old_files(self.articles_dir, days_old, file_prefix="article_")