#!/usr/bin/env python3
"""
Content filtering module.

This module contains the ContentFilter class that handles filtering
website content to include or exclude various page elements.
"""


class ContentFilter:
    """
    Filter to control what content is included in the keyword search.
    
    This class allows for selective inclusion or exclusion of specific
    page elements like headers, menus, footers, and sidebars from the 
    content processing.
    """
    
    def __init__(self, include_headers=True, include_menus=False, include_footers=False, 
                 include_sidebars=False, custom_exclude_selectors=None):
        """
        Initialize a ContentFilter instance.
        
        Args:
            include_headers: Whether to include header content
            include_menus: Whether to include menu/navigation content
            include_footers: Whether to include footer content
            include_sidebars: Whether to include sidebar content
            custom_exclude_selectors: List of additional CSS selectors to exclude
        """
        self.include_headers = include_headers
        self.include_menus = include_menus
        self.include_footers = include_footers
        self.include_sidebars = include_sidebars
        self.custom_exclude_selectors = custom_exclude_selectors or []
        
    def get_excluded_selectors(self):
        """
        Return CSS selectors for elements that should be excluded.
        
        Returns:
            list: List of CSS selectors to exclude
        """
        excluded = []
        
        # Standard navigation elements
        if not self.include_menus:
            excluded.extend([
                'nav', '.nav', '.navigation', '.menu', '.navbar', '#navbar', '#nav', 
                '[role="navigation"]', '.main-menu', '.site-menu', '.top-menu'
            ])
        
        # Header elements
        if not self.include_headers:
            excluded.extend([
                'header', '.header', '#header', '.site-header', '.page-header'
            ])
            
        # Footer elements
        if not self.include_footers:
            excluded.extend([
                'footer', '.footer', '#footer', '.site-footer', '.page-footer'
            ])
            
        # Sidebar elements
        if not self.include_sidebars:
            excluded.extend([
                'aside', '.sidebar', '#sidebar', '.side-menu', '.widget-area'
            ])
        
        # Add custom exclude selectors
        excluded.extend(self.custom_exclude_selectors)
        
        return excluded
    
    def apply_to_soup(self, soup):
        """
        Apply the content filter to a BeautifulSoup object.
        
        This method removes elements that should be excluded according to
        the filter settings.
        
        Args:
            soup: BeautifulSoup object to filter
            
        Returns:
            BeautifulSoup: Filtered BeautifulSoup object
        """
        excluded_selectors = self.get_excluded_selectors()
        
        # Apply filtering by removing excluded elements
        for selector in excluded_selectors:
            for element in soup.select(selector):
                element.decompose()
        
        return soup
    
    def __str__(self):
        """String representation of the content filter settings."""
        included = []
        
        if self.include_headers:
            included.append("headers")
        if self.include_menus:
            included.append("menus")
        if self.include_footers:
            included.append("footers")
        if self.include_sidebars:
            included.append("sidebars")
        
        if included:
            included_str = ", ".join(included)
            return f"ContentFilter(Includes: {included_str})"
        else:
            return "ContentFilter(Excludes: headers, menus, footers, sidebars)"
