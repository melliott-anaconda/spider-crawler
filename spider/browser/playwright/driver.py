#!/usr/bin/env python3
"""
Playwright browser setup and initialization module.

This module contains functions for creating and configuring Playwright browser
instances with appropriate settings for web crawling.
"""

import random
import time

from playwright.sync_api import sync_playwright


def get_random_user_agent():
    """
    Generate a random user-agent string.

    Returns:
        str: Random user agent string
    """
    # List of common user agents (same as in selenium version)
    user_agents = [
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        # Chrome on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        # Chrome on Linux
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        # Firefox on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        # Firefox on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
        # Edge
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        # Safari
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]

    return random.choice(user_agents)


def setup_playwright_browser(
    headless=True, retry_count=3, page_load_timeout=30000, block_resources=True, browser_type="chrome"
):
    """
    Set up and return a Playwright browser instance.

    Args:
        headless: Whether to run in headless mode
        retry_count: Number of times to retry browser creation
        page_load_timeout: Timeout for page loads in milliseconds
        block_resources: Whether to block non-essential resources 
        browser_type: Browser to use ("chromium", "chrome", "firefox", or "webkit")

    Returns:
        Browser page with selenium-compatible interface
    """
    for attempt in range(retry_count):
        try:
            user_agent = get_random_user_agent()
            
            # Start Playwright and launch browser
            playwright = sync_playwright().start()
            
            # Configure browser options
            browser_args = []
            if not headless:
                browser_args.append("--start-maximized")
            
            browser_args.extend([
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-notifications",
                "--disable-popup-blocking",
                "--disable-background-networking",
            ])
            
            # Choose which browser to launch
            if browser_type == "chrome":
                browser = playwright.chromium.launch(
                    headless=headless,
                    args=browser_args,
                    channel="chrome",
                )
            elif browser_type == "firefox":
                browser = playwright.firefox.launch(
                    headless=headless,
                    args=browser_args,
                )
            elif browser_type == "webkit":
                browser = playwright.webkit.launch(
                    headless=headless,
                )
            else:
                # Default to chromium
                browser = playwright.chromium.launch(
                    headless=headless,
                    args=browser_args,
                )
            
            # Create context with custom settings
            context = browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                java_script_enabled=True,
                ignore_https_errors=True,
                locale="en-US",
                timezone_id="America/New_York",  # Add timezone
                permissions=["geolocation"],     # Add common permissions
                bypass_csp=True,  # Bypass Content Security Policy
                accept_downloads=True
            )
            
            # Set context-level timeouts
            context.set_default_timeout(page_load_timeout)
            
            # Create page
            page = context.new_page()
            
            # Configure resource blocking if requested
            if block_resources:
                page.route(
                    "**/*.{png,jpg,jpeg,gif,webp,svg,css,woff,woff2,ttf,otf,eot}",
                    lambda route: route.abort()
                )
                
            # Apply stealth mode
            # page = enable_stealth_mode(page)
                
            # Store references to original methods/properties
            original_url_getter = lambda: page.url
            original_content_method = page.content
            original_title_method = page.title
            
            # Add direct method-based compatibility interface instead of using properties
            # This is simpler and more reliable across implementations
            page.get_current_url = original_url_getter
            page.get_page_source = original_content_method
            page.get_title = original_title_method
            
            # Also set properties for backward compatibility, using a more reliable approach
            class EnhancedPage:
                def __init__(self, page):
                    self._page = page
                
                @property
                def current_url(self):
                    return self._page.url
                
                @property
                def page_source(self):
                    return self._page.content()
                
                @property
                def title(self):
                    return self._page.title()
                
                def __getattr__(self, name):
                    return getattr(self._page, name)
            
            # Create enhanced page wrapper
            enhanced_page = EnhancedPage(page)
            
            # Add compatible methods to the enhanced page
            def get(url):
                try:
                    # Navigate with a longer timeout
                    response = page.goto(
                        url, 
                        wait_until="domcontentloaded",  # Try this instead of networkidle
                        timeout=page_load_timeout
                    )
                    
                    page.evaluate("""
                    () => {
                        // Attempt to restore native functions that might be modified
                        window.HTMLElement.prototype.appendChild = Element.prototype.appendChild;
                        window.HTMLElement.prototype.addEventListener = Element.prototype.addEventListener;
                    }
                    """)

                    # Add an additional wait for dynamic content
                    page.wait_for_selector("body", timeout=5000)
                    
                    # Give extra time for JavaScript frameworks to initialize
                    page.wait_for_timeout(2000)

                    return response
                except Exception as e:
                    print(f"Navigation error: {e}")
                    # Try again with a different wait strategy
                    try:
                        response = page.goto(url, wait_until="load", timeout=page_load_timeout)
                        page.wait_for_timeout(3000)  # Give extra time
                        return response
                    except Exception as e2:
                        print(f"Second navigation attempt failed: {e2}")
                        raise
            
            enhanced_page.get = get
            
            def find_element(by, selector):
                if by == "css selector":
                    return page.query_selector(selector)
                elif by == "xpath":
                    return page.query_selector(f"xpath={selector}")
                elif by == "tag name":
                    return page.query_selector(selector)
                else:
                    raise ValueError(f"Unsupported locator: {by}")
            enhanced_page.find_element = find_element
            
            def find_elements(by, selector):
                if by == "css selector":
                    return page.query_selector_all(selector)
                elif by == "xpath":
                    return page.query_selector_all(f"xpath={selector}")
                elif by == "tag name":
                    return page.query_selector_all(selector)
                else:
                    raise ValueError(f"Unsupported locator: {by}")
            enhanced_page.find_elements = find_elements
            
            def execute_script(script, *args):
                # Ensure script is properly wrapped in a function if it contains a return
                if 'return' in script and not script.strip().startswith('function') and not script.strip().startswith('('):
                    # Wrap in a function to make return valid
                    script = f"() => {{ {script} }}"
                return page.evaluate(script, *args)
            enhanced_page.execute_script = execute_script
            
            def quit():
                try:
                    if page:
                        page.close()
                    if context:
                        context.close()
                    if browser:
                        browser.close()
                    if playwright:
                        playwright.stop()
                except Exception as e:
                    print(f"Error during quit: {e}")
            enhanced_page.quit = quit
            
            # Add HTTP status monitoring
            def get_http_status():
                try:
                    # Use response info from last navigation
                    return page._last_response.status if hasattr(page, '_last_response') else 200
                except:
                    return 200
            enhanced_page.get_http_status = get_http_status
            
            # Store last response for status code checking
            def store_response_info(response):
                page._last_response = response
            page.on("response", store_response_info)
            
            # Add element compatibility methods
            def patch_element(element):
                if element is None:
                    return None
                
                # Add Selenium-compatible methods and properties
                element.get_attribute = lambda name: element.get_attribute(name)
                element.text = element.text_content()
                element.is_displayed = lambda: element.is_visible()
                element.is_enabled = lambda: not element.is_disabled()
                
                return element
            
            # Override element methods to patch returned elements
            original_query_selector = page.query_selector
            original_query_selector_all = page.query_selector_all
            
            def patched_query_selector(selector):
                element = original_query_selector(selector)
                return patch_element(element)
            
            def patched_query_selector_all(selector):
                elements = original_query_selector_all(selector)
                return [patch_element(element) for element in elements]
            
            page.query_selector = patched_query_selector
            page.query_selector_all = patched_query_selector_all
            
            # Store a reference to playwright objects
            enhanced_page._pw = playwright
            enhanced_page._browser = browser
            enhanced_page._context = context
            enhanced_page._page = page
            
            return enhanced_page
            
        except Exception as e:
            print(f"Playwright browser creation failed (attempt {attempt+1}/{retry_count}): {e}")
            time.sleep(2)
            
            if attempt == retry_count - 1:
                raise RuntimeError(f"Failed to create Playwright browser after {retry_count} attempts: {e}")
    
    raise RuntimeError("Failed to create Playwright browser")


def enable_stealth_mode(page):
    """
    Apply stealth mode to the Playwright page to avoid bot detection.
    
    Args:
        page: Playwright page instance
        
    Returns:
        page: The modified page instance
    """
    try:
        # Evaluate scripts to make automation less detectable
        page.evaluate("""
        () => {
            // Overwrite navigator properties
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
            
            // Overwrite chrome properties
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // Overwrite permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        }
        """)
        
        print("Applied stealth mode to Playwright browser")
        return page
    except Exception as e:
        print(f"Warning: Could not apply stealth mode: {e}")
        return page