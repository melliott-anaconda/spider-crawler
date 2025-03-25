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
    normalized_content = re.sub(r"\s+", " ", html_content).strip()
    return hashlib.md5(normalized_content.encode("utf-8")).hexdigest()


def wait_for_spa_content(driver, timeout=10):
    """
    Wait for SPA content to load completely with enhanced CDP monitoring.

    Args:
        driver: Selenium WebDriver instance
        timeout: Maximum time to wait in seconds

    Returns:
        bool: True if waiting completed successfully
    """
    try:
        # Wait for common loading indicators to disappear - keep existing code
        loading_indicators = [
            ".loading",
            "#loading",
            ".spinner",
            ".loader",
            "[role='progressbar']",
            ".progress-bar",
            ".loading-overlay",
            ".loading-spinner",
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

        # NEW: Use CDP to monitor network activity
        try:
            # Enable network monitoring if not already enabled
            driver.execute_cdp_cmd("Network.enable", {})

            # Wait for network to be idle
            end_time = time.time() + timeout
            while time.time() < end_time:
                try:
                    # Get network metrics
                    metrics = driver.execute_cdp_cmd("Network.getMetrics", {})
                    pending_requests = metrics.get("pendingRequests", 0)

                    if pending_requests == 0:
                        # No pending requests, network is idle
                        break

                    time.sleep(0.5)
                except:
                    # If we can't get metrics, fall back to the existing method
                    break
        except:
            # If CDP monitoring fails, continue with existing approach
            pass

        # Your existing approach - keep this as a fallback
        driver.execute_script(
            """
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
        """
        )

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
