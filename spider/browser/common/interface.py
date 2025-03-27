#!/usr/bin/env python3
"""
Browser interface definition module.

This module defines abstract base classes and protocols that standardize
the interface between the crawler and different browser implementations
(Selenium, Playwright, etc.).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, Union


class BrowserElement(Protocol):
    """Protocol defining the interface for browser elements."""
    
    @property
    def text(self) -> str:
        """Get the text content of the element."""
        ...
    
    def get_attribute(self, name: str) -> Optional[str]:
        """Get the value of the specified attribute."""
        ...
    
    def is_displayed(self) -> bool:
        """Check if the element is visible."""
        ...
    
    def is_enabled(self) -> bool:
        """Check if the element is enabled."""
        ...


class Browser(ABC):
    """Abstract base class for browser implementations."""
    
    @property
    @abstractmethod
    def current_url(self) -> str:
        """Get the current URL."""
        pass
    
    @property
    @abstractmethod
    def page_source(self) -> str:
        """Get the page source/HTML content."""
        pass
    
    @property
    @abstractmethod
    def title(self) -> str:
        """Get the page title."""
        pass
    
    @abstractmethod
    def get(self, url: str) -> None:
        """Navigate to the specified URL."""
        pass
    
    @abstractmethod
    def find_element(self, by: str, selector: str) -> BrowserElement:
        """Find a single element using the specified selector strategy."""
        pass
    
    @abstractmethod
    def find_elements(self, by: str, selector: str) -> List[BrowserElement]:
        """Find all elements matching the specified selector strategy."""
        pass
    
    @abstractmethod
    def execute_script(self, script: str, *args: Any) -> Any:
        """Execute JavaScript in the browser context."""
        pass
    
    @abstractmethod
    def get_http_status(self) -> int:
        """Get the HTTP status code of the last response."""
        pass
    
    @abstractmethod
    def quit(self) -> None:
        """Close the browser and release resources."""
        pass


class BrowserFactory:
    """Factory class for creating browser instances."""
    
    @staticmethod
    def create(
        engine: str = "selenium",
        headless: bool = True,
        webdriver_path: Optional[str] = None,
        type: str = "chromium",
        **kwargs: Any
    ) -> Browser:
        """
        Create a browser instance of the specified type.
        
        Args:
            engine: Browser engine to use ('selenium' or 'playwright')
            headless: Whether to run in headless mode
            webdriver_path: Path to the WebDriver executable (for Selenium)
            type: Browser type to use ('chromium', 'chrome', 'webkit', 'firefox')
            **kwargs: Additional engine-specific options
            
        Returns:
            Browser: An instance implementing the Browser interface
        """
        if engine.lower() == "playwright":
            from ..playwright.driver import setup_playwright_browser
            return setup_playwright_browser(headless=headless, browser_type=type, **kwargs)
        else:
            from ..selenium.driver import setup_webdriver
            return setup_webdriver(headless=headless, webdriver_path=webdriver_path, **kwargs)


class BrowserNavigator:
    """Utility class with navigation methods for different browser implementations."""
    
    @staticmethod
    def wait_for_spa_content(browser: Browser, timeout: Union[int, float] = 10) -> bool:
        """
        Wait for SPA content to load completely.
        
        Args:
            browser: Browser instance
            timeout: Maximum time to wait (seconds for Selenium, milliseconds for Playwright)
            
        Returns:
            bool: True if waiting completed successfully
        """
        # Detect browser type and call appropriate implementation
        if browser.__class__.__module__.endswith('playwright.driver'):
            from ..playwright.navigator import wait_for_spa_content
            return wait_for_spa_content(browser, timeout=int(timeout * 1000))
        else:
            from ..selenium.navigator import wait_for_spa_content
            return wait_for_spa_content(browser, timeout=timeout)
    
    @staticmethod
    def hash_page_content(html_content: str) -> str:
        """
        Generate a hash of the page content to detect changes.
        
        Args:
            html_content: HTML content to hash
            
        Returns:
            str: MD5 hash of the normalized content
        """
        # This implementation is identical for both engines, so use either one
        from ..selenium.navigator import hash_page_content
        return hash_page_content(html_content)
    
    @staticmethod
    def extract_links(
        browser: Browser,
        url: str,
        base_domain: str,
        path_prefix: Optional[str] = None,
        allow_subdomains: bool = False,
        allowed_extensions: Optional[List[str]] = None,
        is_spa: bool = False
    ) -> set:
        """Extract links from a page with domain/path matching."""
        # Detect browser type and call appropriate implementation
        if browser.__class__.__module__.endswith('playwright.driver'):
            # Use Playwright versions from utils.url
            if is_spa:
                from ...utils.url import get_spa_links_playwright
                return get_spa_links_playwright(
                    browser,  # Playwright page instance
                    url,      # Current URL
                    base_domain,
                    path_prefix,
                    allow_subdomains,
                    allowed_extensions
                )
            else:
                from ...utils.url import get_page_links_playwright
                return get_page_links_playwright(
                    browser,  # Playwright page instance
                    url,      # Current URL
                    base_domain,
                    path_prefix,
                    allow_subdomains,
                    allowed_extensions
                )
        else:
            # Use Selenium-specific implementations
            if is_spa:
                from ...utils.url import get_spa_links
                return get_spa_links(
                    browser, url, base_domain, path_prefix, allow_subdomains, allowed_extensions
                )
            else:
                from ...utils.url import get_page_links
                return get_page_links(
                    browser, url, base_domain, path_prefix, allow_subdomains, allowed_extensions
                )
            

        