"""
Browser module for handling browser initialization and navigation.

This package contains components for setting up WebDriver instances and
navigating web pages including SPAs (Single Page Applications).
"""

from .driver import (enable_cdp_features, enable_resource_blocking,
                     get_random_user_agent, setup_webdriver)
from .navigator import hash_page_content, wait_for_spa_content
from .stealth import apply_stealth_mode

__all__ = [
    "setup_webdriver",
    "get_random_user_agent",
    "wait_for_spa_content",
    "hash_page_content",
    "enable_cdp_features",
    "enable_resource_blocking",
    "apply_stealth_mode",
]
