"""
Content scraping service using the journalist library.

This module simply re-exports the journalist library for use in the AISports application.
The journalist library (https://github.com/oktay-be/journalist) handles all scraping functionality.
"""

try:
    from journalist import Journalist
    from journalist.exceptions import NetworkError, ExtractionError, ValidationError
    JOURNALIST_AVAILABLE = True
except ImportError:
    JOURNALIST_AVAILABLE = False
    
    # Fallback class if journalist is not available
    class Journalist:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "journalist library (journ4list) is not available. "
                "Please install it using: pip install journ4list"
            )

# Re-export for convenience
__all__ = ['Journalist', 'NetworkError', 'ExtractionError', 'ValidationError', 'JOURNALIST_AVAILABLE']
