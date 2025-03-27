"""
Common browser interfaces and utilities module.

This package contains interfaces and utilities shared across
different browser implementations (Selenium, Playwright).
"""

from .interface import Browser, BrowserElement, BrowserFactory, BrowserNavigator

__all__ = ["Browser", "BrowserElement", "BrowserFactory", "BrowserNavigator"]