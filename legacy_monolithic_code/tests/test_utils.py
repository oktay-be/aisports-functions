"""
Test utilities for testing the API and capabilities.
"""
import os
from contextlib import contextmanager
from typing import Dict, Any, Generator


class MockResponse:
    """
    Mock response for requests.
    """
    def __init__(self, status_code: int, json_data: Dict[str, Any], content: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.content = content

    def json(self) -> Dict[str, Any]:
        """Return JSON data."""
        return self._json_data


@contextmanager
def mock_env_vars(env_vars: Dict[str, str]) -> Generator[None, None, None]:
    """
    Temporarily set environment variables for testing.
    
    Args:
        env_vars: Dictionary of environment variables to set.
        
    Yields:
        None
    """
    original_env = {}
    for key, value in env_vars.items():
        if key in os.environ:
            original_env[key] = os.environ[key]
        os.environ[key] = value
    
    try:
        yield
    finally:
        # Restore original environment variables
        for key in env_vars:
            if key in original_env:
                os.environ[key] = original_env[key]
            else:
                del os.environ[key]
