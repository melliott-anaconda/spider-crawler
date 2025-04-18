"""
Browser module for handling browser initialization and navigation.

This package contains components for setting up browser instances (Selenium or Playwright)
and navigating web pages including SPAs (Single Page Applications).
"""

from .common.interface import Browser, BrowserFactory, BrowserNavigator
from .utils import execute_browser_script, clean_cookie_elements

# Export the factory function for creating browser instances
create_browser = BrowserFactory.create

# Export navigation utilities
wait_for_spa_content = BrowserNavigator.wait_for_spa_content
extract_links = BrowserNavigator.extract_links
hash_page_content = BrowserNavigator.hash_page_content

# Export browser interface for type hints
__all__ = [
    "Browser",             # Abstract browser interface
    "create_browser",      # Factory function to create browser instances
    "wait_for_spa_content", # Utility to wait for SPA content
    "extract_links",       # Utility to extract links from page
    "hash_page_content",   # Utility to hash page content
    "execute_browser_script", # Utility to execute evals correctly in either Playwright or Selenium
    "clean_cookie_elements", # Utility to handle pesky cookie banners and pref centres
]