"""
Browser module for handling browser initialization and navigation.

This package contains components for setting up WebDriver instances and
navigating web pages including SPAs (Single Page Applications).
"""

from .driver import setup_webdriver, get_random_user_agent, enable_cdp_features, enable_resource_blocking
from .navigator import (wait_for_spa_content, hash_page_content)
from .stealth import apply_stealth_mode

__all__ = [
    'setup_webdriver', 
    'get_random_user_agent',
    'wait_for_spa_content',
    'hash_page_content',
    'enable_cdp_features',
    'enable_resource_blocking',
    'apply_stealth_mode' 
]
