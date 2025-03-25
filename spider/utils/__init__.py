"""
Utility modules for URL handling and HTTP response processing.

This package contains utility functions for normalizing URLs,
checking URL types, and handling HTTP response codes.
"""

from .http import handle_response_code
from .url import get_page_links, get_spa_links, is_webpage_url, normalize_url

__all__ = [
    "normalize_url",
    "is_webpage_url",
    "get_page_links",
    "get_spa_links",
    "handle_response_code",
]
