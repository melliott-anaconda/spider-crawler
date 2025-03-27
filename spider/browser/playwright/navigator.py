#!/usr/bin/env python3
"""
Page navigation and interaction module for Playwright.

This module contains functions for navigating web pages, handling SPAs,
and extracting page content using Playwright.
"""

import hashlib
import re
import time


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


def wait_for_spa_content(page, timeout=10000):
    """
    Wait for SPA content to load completely with enhanced monitoring.

    Args:
        page: Playwright page instance
        timeout: Maximum time to wait in milliseconds

    Returns:
        bool: True if waiting completed successfully
    """
    try:
        # Create a timeout deadline
        deadline = time.time() + (timeout / 1000)

        # Wait for common loading indicators to disappear
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
                indicator_element = page.query_selector(indicator)
                if indicator_element:
                    # Wait for it to disappear with a suitable timeout
                    remaining_timeout = max(1000, int((deadline - time.time()) * 1000))
                    page.wait_for_selector(f"{indicator}", state="hidden", timeout=remaining_timeout)
            except Exception:
                # Continue if the selector doesn't exist or times out
                continue

        # Wait for network to be idle
        try:
            # Calculate remaining timeout
            remaining_timeout = max(1000, int((deadline - time.time()) * 1000))
            
            # Wait for network idle (built-in with Playwright)
            page.wait_for_load_state("networkidle", timeout=remaining_timeout)
        except Exception as e:
            # If networkidle fails, try alternative approach
            print(f"Network idle wait failed: {e}, using alternative approach")
            pass

        # Check for dynamic content changes
        initial_content_length = len(page.content())  # Changed from page.content to page.content()
        time.sleep(1)  # Brief wait to allow for content changes

        # If page content is still changing, wait a bit longer
        if len(page.content()) != initial_content_length:  # Changed again
            time.sleep(2)

        return True

    except Exception as e:
        print(f"Error waiting for SPA content: {e}")
        return False

def scroll_page(page, scroll_behavior="smooth", max_scrolls=5):
    """
    Scroll the page to ensure all dynamic content is loaded.

    Args:
        page: Playwright page instance
        scroll_behavior: Scrolling behavior ('smooth' or 'auto')
        max_scrolls: Maximum number of scroll operations

    Returns:
        bool: True if scrolling completed successfully
    """
    try:
        # Get initial page height
        initial_height = page.evaluate("() => { document.body.scrollHeight }")
        
        # Scroll down in increments
        for i in range(max_scrolls):
            # Scroll down
            page.evaluate(f"""() => {{
                window.scrollBy({{
                    top: document.body.scrollHeight / {max_scrolls},
                    behavior: '{scroll_behavior}'
                }});
            }}""")
            
            # Wait a moment for content to load
            page.wait_for_timeout(500)
            
            # Check if we've reached the bottom
            current_height = page.evaluate("() => { document.body.scrollHeight }")
            scroll_position = page.evaluate("() => { window.scrollY + window.innerHeight }")
            
            if scroll_position >= current_height - 200 or current_height == initial_height:
                # We're at the bottom or height didn't change
                break
                
            initial_height = current_height
        
        # Scroll back to top for consistent state
        page.evaluate("() => { window.scrollTo(0, 0) }")
        return True
        
    except Exception as e:
        print(f"Error scrolling page: {e}")
        return False


def click_show_more_buttons(page, timeout=5000):
    """
    Find and click common "show more" or "load more" buttons.

    Args:
        page: Playwright page instance
        timeout: Maximum time to wait for each click in milliseconds

    Returns:
        int: Number of buttons clicked
    """
    try:
        # Common selectors for "show more" buttons
        show_more_selectors = [
            "button:has-text('Show more')",
            "button:has-text('Load more')",
            "button:has-text('View more')",
            "a:has-text('Show more')",
            "a:has-text('Load more')",
            "a:has-text('View more')",
            ".show-more",
            ".load-more",
            ".view-more",
            "[data-testid='show-more']",
        ]
        
        clicks = 0
        for selector in show_more_selectors:
            try:
                # Look for the button with a short timeout
                button = page.wait_for_selector(selector, timeout=1000, state="visible")
                if button:
                    # Click the button
                    button.click()
                    page.wait_for_timeout(timeout)
                    clicks += 1
                    
                    # Wait for any new content to load
                    wait_for_spa_content(page, timeout=3000)
            except Exception:
                # Continue if this selector doesn't exist or can't be clicked
                continue
                
        return clicks
        
    except Exception as e:
        print(f"Error clicking show more buttons: {e}")
        return 0


def extract_meta_data(page):
    """
    Extract metadata from page like title, description, etc.

    Args:
        page: Playwright page instance

    Returns:
        dict: Dictionary containing page metadata
    """
    try:
        metadata = {
            'title': page.title(),
            'url': page.url
        }
        
        # Extract meta description
        try:
            description = page.query_selector("meta[name='description']")
            if description:
                metadata['description'] = description.get_attribute('content')
        except:
            pass
            
        # Extract canonical URL
        try:
            canonical = page.query_selector("link[rel='canonical']")
            if canonical:
                metadata['canonical_url'] = canonical.get_attribute('href')
        except:
            pass
            
        # Extract open graph data
        og_tags = ['og:title', 'og:description', 'og:type', 'og:image', 'og:url']
        for tag in og_tags:
            try:
                og_element = page.query_selector(f"meta[property='{tag}']")
                if og_element:
                    metadata[tag.replace(':', '_')] = og_element.get_attribute('content')
            except:
                pass
                
        return metadata
        
    except Exception as e:
        print(f"Error extracting metadata: {e}")
        return {'title': '', 'url': page.url}


def get_page_status(page):
    """
    Get HTTP status code and response information.

    Args:
        page: Playwright page instance

    Returns:
        dict: Dictionary with status code and response details
    """
    try:
        # Get the last response from the page if available
        if hasattr(page, '_last_response'):
            response = page._last_response
            return {
                'status_code': response.status,
                'ok': response.ok,
                'status_text': response.status_text if hasattr(response, 'status_text') else '',
                'url': response.url
            }
        
        # If no response is stored, try to get status from the page itself
        try:
            # Use Navigation API to get response info
            status = page.evaluate("""
                () => {
                    try {
                        const entries = performance.getEntriesByType('navigation');
                        if (entries && entries.length > 0) {
                            return entries[0].responseStatus || 200;
                        }
                        return 200;
                    } catch (e) {
                        return 200;
                    }
                }
            """)
            
            return {
                'status_code': status,
                'ok': 200 <= status < 300,
                'status_text': '',
                'url': page.url
            }
        except:
            # Default to 200 if we can't determine status
            return {'status_code': 200, 'ok': True, 'status_text': '', 'url': page.url}
            
    except Exception as e:
        print(f"Error getting page status: {e}")
        return {'status_code': 200, 'ok': True, 'status_text': '', 'url': page.url}


def enhance_page_for_scraping(page):
    """
    Enhance the page to improve content extraction.
    
    Args:
        page: Playwright page instance
        
    Returns:
        bool: True if enhancement succeeded
    """
    try:
        # Expand any collapsed content (like "read more" sections)
        page.evaluate("""
            () => {
                // Try to find and click elements that might expand content
                const expandElements = [
                    ...document.querySelectorAll('details:not([open])'),
                    ...document.querySelectorAll('.collapsible:not(.expanded)'),
                    ...document.querySelectorAll('.expandable:not(.expanded)'),
                    ...document.querySelectorAll('.collapse:not(.show)')
                ];
                
                for (const elem of expandElements) {
                    try {
                        if (elem.tagName === 'DETAILS') {
                            elem.setAttribute('open', 'true');
                        } else {
                            elem.click();
                        }
                    } catch (e) {
                        // Ignore click errors
                    }
                }
                
                // Try to remove obstructing elements
                const obstructions = [
                    ...document.querySelectorAll('.modal'),
                    ...document.querySelectorAll('.dialog'),
                    ...document.querySelectorAll('.cookie-banner'),
                    ...document.querySelectorAll('.popup'),
                    ...document.querySelectorAll('.overlay')
                ];
                
                for (const elem of obstructions) {
                    try {
                        elem.style.display = 'none';
                    } catch (e) {
                        // Ignore style errors
                    }
                }
                
                return true;
            }
        """)
        
        return True
        
    except Exception as e:
        print(f"Error enhancing page: {e}")
        return False