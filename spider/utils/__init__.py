"""
Utility modules for URL handling and HTTP response processing.

This package contains utility functions for normalizing URLs,
checking URL types, and handling HTTP response codes.
"""

from .url import (normalize_url, is_webpage_url, get_page_links, 
                 get_spa_links)
from .http import handle_response_code

__all__ = [
    'normalize_url', 
    'is_webpage_url', 
    'get_page_links',
    'get_spa_links',
    'handle_response_code'
]
