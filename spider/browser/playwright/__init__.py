"""
Playwright browser module for handling browser initialization and navigation.

This module provides components for setting up Playwright browser instances
and navigating web pages including SPAs (Single Page Applications).
"""

from .driver import (enable_stealth_mode, get_random_user_agent,
                    setup_playwright_browser)
from .navigator import (click_show_more_buttons, enhance_page_for_scraping,
                        extract_meta_data, get_page_status, hash_page_content,
                        scroll_page, wait_for_spa_content)

__all__ = [
    "setup_playwright_browser",
    "get_random_user_agent",
    "enable_stealth_mode",
    "wait_for_spa_content",
    "hash_page_content",
    "scroll_page",
    "click_show_more_buttons",
    "extract_meta_data",
    "get_page_status",
    "enhance_page_for_scraping",
]