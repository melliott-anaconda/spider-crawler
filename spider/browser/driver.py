#!/usr/bin/env python3
"""
WebDriver setup and initialization module.

This module contains functions for creating and configuring WebDriver instances
with appropriate settings for web crawling.
"""

import random
import time
import types
import subprocess
import os
import signal

from selenium import webdriver
from selenium.common.exceptions import (SessionNotCreatedException, 
                                       WebDriverException)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def ensure_no_chromedriver_zombies():
        """Clean up any zombie ChromeDriver processes."""
        
        try:
            # Find all chromedriver processes
            result = subprocess.run(['pgrep', 'chromedriver'], 
                                    capture_output=True, text=True)
            
            if result.returncode == 0:  # Found processes
                pids = result.stdout.strip().split('\n')
                print(f"Found {len(pids)} ChromeDriver processes to clean up")
                
                for pid in pids:
                    pid = pid.strip()
                    if pid:
                        try:
                            # Try regular termination first
                            os.kill(int(pid), signal.SIGTERM)
                            time.sleep(0.1)  # Give it a moment
                            
                            # Check if still running
                            try:
                                os.kill(int(pid), 0)  # Signal 0 checks if process exists
                                # If we get here, process still exists, try SIGKILL
                                os.kill(int(pid), signal.SIGKILL)
                            except OSError:
                                # Process already gone
                                pass
                        except Exception as e:
                            print(f"Error killing ChromeDriver process {pid}: {e}")
        except Exception as e:
            print(f"Error checking for ChromeDriver processes: {e}")
    

def get_random_user_agent():
    """
    Generate a random user-agent string.
    
    Returns:
        str: Random user agent string
    """
    # List of common user agents
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
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
    ]
    
    return random.choice(user_agents)


def setup_webdriver(headless=True, webdriver_path=None, retry_count=3, page_load_timeout=30):
    """
    Set up and return a Selenium WebDriver instance with retry logic and HTTP status monitoring.
    
    Args:
        headless: Whether to run in headless mode
        webdriver_path: Path to the WebDriver executable
        retry_count: Number of times to retry WebDriver creation
        page_load_timeout: Timeout for page loads in seconds
        
    Returns:
        WebDriver: Configured Selenium WebDriver instance
        
    Raises:
        RuntimeError: If WebDriver creation fails after specified retry attempts
    """

    import os
    import platform
    print(f"Starting WebDriver setup: headless={headless}, system={platform.system()}, python={platform.python_version()}")
    print(f"Memory info: {os.popen('ps -o rss -p %d | tail -1' % os.getpid()).read().strip()} KB used by this process")
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless=new')  # Updated headless syntax
    
    # Optimize page load strategy
    chrome_options.page_load_strategy = 'normal'  # Use 'eager' if not handling SPAs
    
    # Essential options for performance - keep existing ones
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    
    # Add new performance optimizations
    chrome_options.add_argument('--disable-notifications')
    chrome_options.add_argument('--disable-popup-blocking')
    chrome_options.add_argument('--disable-background-networking')
    chrome_options.add_argument('--disable-backgrounding-occluded-windows')
    
    # Limit memory and process resources - IMPORTANT
    chrome_options.add_argument('--js-flags=--expose-gc')
    chrome_options.add_argument('--single-process')  # This can help on Mac
    chrome_options.add_argument('--disable-application-cache')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--disable-browser-side-navigation')
    
    # More aggressive resource limits for macOS
    if platform.system() == 'Darwin':  # macOS
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--enable-low-end-device-mode')
        chrome_options.add_argument('--force-device-scale-factor=1')

    # Add a random user-agent - keep your existing function
    chrome_options.add_argument(f'--user-agent={get_random_user_agent()}')
    
    # Set logging preferences - keep your existing settings
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})

    # Try to create the WebDriver with retry logic
    for attempt in range(retry_count):
        try:
            # Create driver using Service object with ChromeDriverManager
            if not webdriver_path:
                service = Service(ChromeDriverManager().install())
            else:
                service = Service(webdriver_path)
                
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Set timeouts
            driver.set_page_load_timeout(page_load_timeout)
            driver.set_script_timeout(page_load_timeout)
            
            # Add your existing JavaScript monitoring script
            add_response_monitoring_script = """
            // Your existing monitoring script
            """
            
            # Execute the monitoring script
            driver.execute_script(add_response_monitoring_script)
            
            # Add helper methods - keep your existing implementations
            def get_http_status(driver):
                # Your existing implementation
                pass
                
            def get_response_headers(driver):
                # Your existing implementation
                pass
            
            # Attach methods to driver
            driver.get_http_status = types.MethodType(get_http_status, driver)
            driver.get_response_headers = types.MethodType(get_response_headers, driver)
            
            # Keep your analyze_network_requests method
            def analyze_network_requests(driver):
                # Your existing implementation
                pass
                
            # Attach network analysis method to driver
            driver.analyze_network_requests = types.MethodType(analyze_network_requests, driver)
            
            # Keep your implementation of get_with_status
            original_get = driver.get
            def get_with_status(self, url):
                # Your existing implementation
                pass
                
            # Attach the new get method
            driver.get_with_status = types.MethodType(get_with_status, driver)
            
            # NEW: Add CDP-based network control
            driver = enable_cdp_features(driver)
            
            return driver
            
        except (WebDriverException, SessionNotCreatedException) as e:
            print(f"WebDriver creation failed (attempt {attempt+1}/{retry_count}): {e}")
            time.sleep(2)
            
            if attempt == retry_count - 1:
                raise
    
    raise RuntimeError("Failed to create WebDriver after multiple attempts")

def enable_cdp_features(driver):
    """Enable Chrome DevTools Protocol features for better performance and control."""
    try:
        # Enable network monitoring
        driver.execute_cdp_cmd('Network.enable', {})
        
        # Enable caching
        driver.execute_cdp_cmd('Network.setCacheDisabled', {'cacheDisabled': False})
        
        # Set custom user agent to bypass simple bot detection
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            'userAgent': driver.execute_script('return navigator.userAgent'),
            'acceptLanguage': 'en-US,en;q=0.9',
            'platform': 'Windows'
        })
        
        # Add HTTP status monitoring via CDP - FIX HERE
        # Instead of passing a lambda directly, set up a listener script in the browser
        driver.execute_script("""
            // Set up a network response listener
            if (!window._networkListener) {
                window._lastHttpStatus = 200;
                window._responseHeaders = {};
                
                window._networkListener = true;
                
                // Create function to handle network events
                const originalFetch = window.fetch;
                window.fetch = function() {
                    return originalFetch.apply(this, arguments)
                        .then(response => {
                            window._lastHttpStatus = response.status;
                            return response;
                        });
                };
                
                // Also handle XHR requests
                const originalXHROpen = XMLHttpRequest.prototype.open;
                XMLHttpRequest.prototype.open = function() {
                    this.addEventListener('load', function() {
                        window._lastHttpStatus = this.status;
                    });
                    return originalXHROpen.apply(this, arguments);
                };
            }
        """)
        
        # Add a method to get the status
        def get_cdp_status(driver):
            try:
                return driver.execute_script("return window._lastHttpStatus || 200;")
            except:
                return 200
                
        driver.get_cdp_status = types.MethodType(get_cdp_status, driver)
        
        return driver
    except Exception as e:
        print(f"Warning: Could not enable CDP features: {e}")
        return driver
    
def enable_resource_blocking(driver, block_images=True, block_fonts=True, block_media=True):
    """Block resource types to speed up crawling using CDP."""
    try:
        # Create the blocking patterns
        blocked_types = []
        if block_images:
            blocked_types.append('Image')
        if block_fonts:
            blocked_types.append('Font')
        if block_media:
            blocked_types.append('Media')
            
        # Convert to JSON string for JavaScript
        import json
        blocked_types_json = json.dumps(blocked_types)
        
        # Set up request blocking via JavaScript
        driver.execute_script(f"""
            // Set up resource blocking
            const blockedTypes = {blocked_types_json};
            
            // Create a new fetch handler
            const originalFetch = window.fetch;
            window.fetch = function(resource, options) {{
                const url = resource.toString();
                
                // Simple heuristic for resource type
                let resourceType = '';
                if (url.match(/\\.(jpg|jpeg|png|gif|webp|svg|ico)($|\\?)/i)) resourceType = 'Image';
                else if (url.match(/\\.(woff|woff2|ttf|otf|eot)($|\\?)/i)) resourceType = 'Font';
                else if (url.match(/\\.(mp3|mp4|webm|ogg|wav|avi|mov)($|\\?)/i)) resourceType = 'Media';
                
                if (blockedTypes.includes(resourceType)) {{
                    // Create a Response object that mimics a network error
                    return Promise.resolve(new Response('', {{
                        status: 0,
                        statusText: 'Blocked by spider crawler'
                    }}));
                }}
                
                return originalFetch.apply(this, arguments);
            }};
        """)
        
        return driver
    except Exception as e:
        print(f"Warning: Could not enable resource blocking: {e}")
        return driver
    