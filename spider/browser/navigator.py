#!/usr/bin/env python3
"""
Page navigation and interaction module.

This module contains functions for navigating web pages, handling SPAs,
and extracting page content.
"""

import hashlib
import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def hash_page_content(html_content):
    """
    Generate a hash of the page content to detect changes.
    
    Args:
        html_content: HTML content to hash
        
    Returns:
        str: MD5 hash of the normalized content
    """
    # Remove whitespace and newlines to normalize the content
    normalized_content = re.sub(r'\s+', ' ', html_content).strip()
    return hashlib.md5(normalized_content.encode('utf-8')).hexdigest()


def wait_for_spa_content(driver, timeout=10):
    """
    Wait for SPA content to load completely.
    
    Args:
        driver: Selenium WebDriver instance
        timeout: Maximum time to wait in seconds
        
    Returns:
        bool: True if waiting completed successfully
    """
    try:
        # Wait for common loading indicators to disappear
        loading_indicators = [
            ".loading", "#loading", ".spinner", ".loader", 
            "[role='progressbar']", ".progress-bar", 
            ".loading-overlay", ".loading-spinner"
        ]
        
        for indicator in loading_indicators:
            try:
                # Check if indicator exists
                indicators = driver.find_elements(By.CSS_SELECTOR, indicator)
                if indicators:
                    # Wait for it to disappear
                    WebDriverWait(driver, timeout).until(
                        EC.invisibility_of_element_located((By.CSS_SELECTOR, indicator))
                    )
            except:
                continue
        
        # Wait for network activity to complete
        driver.execute_script("""
            return new Promise((resolve) => {
                // If page already loaded, resolve immediately
                if (document.readyState === 'complete') {
                    resolve();
                    return;
                }
                
                // Otherwise wait for load event
                window.addEventListener('load', resolve);
                
                // Set a backup timeout
                setTimeout(resolve, 5000);
            });
        """)
        
        # Check for dynamic content changes
        initial_length = len(driver.page_source)
        time.sleep(1)  # Brief wait to allow for content changes
        
        # If page content is still changing, wait a bit longer
        if len(driver.page_source) != initial_length:
            time.sleep(2)
            
        return True
        
    except Exception as e:
        print(f"Error waiting for SPA content: {e}")
        return False


def extract_page_metadata(driver, url):
    """
    Extract metadata about the page like title, description, etc.
    
    Args:
        driver: Selenium WebDriver instance
        url: URL of the page
        
    Returns:
        dict: Metadata about the page
    """
    metadata = {
        'url': url,
        'title': driver.title,
        'domain': urlparse(url).netloc
    }
    
    try:
        # Extract meta description
        description_elem = driver.find_element(By.CSS_SELECTOR, 'meta[name="description"]')
        if description_elem:
            metadata['description'] = description_elem.get_attribute('content')
    except:
        pass
        
    try:
        # Extract canonical URL
        canonical_elem = driver.find_element(By.CSS_SELECTOR, 'link[rel="canonical"]')
        if canonical_elem:
            metadata['canonical_url'] = canonical_elem.get_attribute('href')
    except:
        pass
        
    try:
        # Extract main heading (h1)
        h1_elem = driver.find_element(By.TAG_NAME, 'h1')
        if h1_elem:
            metadata['h1'] = h1_elem.text
    except:
        pass
    
    return metadata


def check_for_rate_limiting(driver):
    """
    Check if the page shows signs of rate limiting.
    
    Args:
        driver: Selenium WebDriver instance
        
    Returns:
        bool: True if rate limiting is detected
    """
    try:
        page_text = driver.find_element(By.TAG_NAME, 'body').text.lower()
        page_source = driver.page_source.lower()
        
        # Common rate limiting terms
        rate_limit_terms = [
            'rate limit', 'too many requests', 'throttled', 
            'try again later', 'request limit', 'limits exceeded',
            'capacity', 'slow down', 'too frequent', 'abuse detection'
        ]
        
        # Check for rate limit indicators in page
        for term in rate_limit_terms:
            if term in page_text or term in page_source:
                return True
                
        # Check for 429 or similar status codes
        status_code = driver.get_http_status() if hasattr(driver, 'get_http_status') else None
        if status_code in [429, 430, 420, 509]:
            return True
            
        # Check for Cloudflare or similar protection pages
        protection_indicators = [
            'cloudflare', 'captcha', 'challenge', 'ddos protection',
            'security check', 'automated request', 'bot detection'
        ]
        
        for indicator in protection_indicators:
            if indicator in page_text or indicator in page_source:
                return True
        
        return False
        
    except Exception as e:
        print(f"Error checking for rate limiting: {e}")
        return False


def extract_main_content(driver):
    """
    Extract the main content area of a page, excluding navigation,
    headers, footers, etc.
    
    Args:
        driver: Selenium WebDriver instance
        
    Returns:
        BeautifulSoup: BeautifulSoup object containing the main content
    """
    try:
        # Get full page source
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # List of potential main content selectors (in priority order)
        main_content_selectors = [
            'main', '#main', '.main-content', 'article', '.article',
            '#content', '.content', '[role="main"]'
        ]
        
        # Try each selector in turn
        for selector in main_content_selectors:
            main_content = soup.select_one(selector)
            if main_content and len(main_content.get_text(strip=True)) > 200:
                return main_content
        
        # If no main content found, use heuristics:
        # 1. Remove known non-content elements
        for element in soup.select('header, footer, nav, aside, .sidebar, .menu, .navigation, .ads, .comments'):
            element.decompose()
        
        # 2. Find the element with the most text content
        content_candidates = {}
        for element in soup.find_all(['div', 'section']):
            text_length = len(element.get_text(strip=True))
            if text_length > 200:  # Only consider elements with substantial text
                content_candidates[element] = text_length
        
        if content_candidates:
            main_content = max(content_candidates.items(), key=lambda x: x[1])[0]
            return main_content
        
        # Fallback to body if all else fails
        return soup.body
        
    except Exception as e:
        print(f"Error extracting main content: {e}")
        return BeautifulSoup(driver.page_source, 'html.parser')


def take_screenshot(driver, output_path):
    """
    Take a screenshot of the current page.
    
    Args:
        driver: Selenium WebDriver instance
        output_path: Path to save the screenshot
        
    Returns:
        bool: True if screenshot was saved successfully
    """
    try:
        return driver.save_screenshot(output_path)
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return False
