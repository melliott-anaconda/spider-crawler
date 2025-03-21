#!/usr/bin/env python3
"""
WebDriver setup and initialization module.

This module contains functions for creating and configuring WebDriver instances
with appropriate settings for web crawling.
"""

import json
import random
import time
import types

from selenium import webdriver
from selenium.common.exceptions import (SessionNotCreatedException, 
                                       TimeoutException, 
                                       WebDriverException)
from selenium.webdriver.chrome.options import Options


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
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless=new')
    
    # Essential options for performance
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    
    # Performance optimizations
    chrome_options.add_argument('--disable-features=NetworkService')
    chrome_options.add_argument('--disable-features=VizDisplayCompositor')
    chrome_options.add_argument('--disable-features=TranslateUI')
    chrome_options.add_argument('--disable-features=AutofillAddressProfileSavePrompt')
    
    # Reduce memory usage
    chrome_options.add_argument('--js-flags=--expose-gc')
    chrome_options.add_argument('--disable-component-extensions-with-background-pages')
    chrome_options.add_argument('--disable-default-apps')
    
    # SPA-friendly settings
    chrome_options.page_load_strategy = 'normal'  # Changed from 'eager' to 'normal' for SPAs
    
    # Add a random user-agent
    chrome_options.add_argument(f'--user-agent={get_random_user_agent()}')
    
    # Add JavaScript capabilities
    chrome_options.add_argument('--enable-javascript')
    
    # Enable network status logging
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})

    # Try to create the WebDriver with retry logic
    for attempt in range(retry_count):
        try:
            # Create driver
            driver = webdriver.Chrome(options=chrome_options)
            
            # Set timeouts
            driver.set_page_load_timeout(page_load_timeout)
            driver.set_script_timeout(page_load_timeout)
            
            # Add JavaScript to capture HTTP response codes
            add_response_monitoring_script = """
            // Create a variable to store status codes
            window.httpStatusCode = 200;  // Default to 200
            window.responseHeaders = {};
            
            // Create a proxy for the original XMLHttpRequest
            (function(open) {
                XMLHttpRequest.prototype.open = function() {
                    this.addEventListener('load', function() {
                        window.httpStatusCode = this.status;
                        
                        // Parse response headers
                        var headers = {};
                        var headerStr = this.getAllResponseHeaders();
                        if (headerStr) {
                            var headerPairs = headerStr.split('\\r\\n');
                            for (var i = 0; i < headerPairs.length; i++) {
                                var headerPair = headerPairs[i];
                                var index = headerPair.indexOf(': ');
                                if (index > 0) {
                                    var key = headerPair.substring(0, index).toLowerCase();
                                    var val = headerPair.substring(index + 2);
                                    headers[key] = val;
                                }
                            }
                        }
                        window.responseHeaders = headers;
                    });
                    
                    // Handle network errors
                    this.addEventListener('error', function() {
                        window.httpStatusCode = 0;  // Use 0 for network errors
                    });
                    
                    open.apply(this, arguments);
                };
            })(XMLHttpRequest.prototype.open);
            
            // Also handle fetch API
            (function(fetch) {
                window.fetch = function() {
                    return fetch.apply(this, arguments).then(response => {
                        window.httpStatusCode = response.status;
                        
                        // Extract response headers
                        var headers = {};
                        response.headers.forEach((value, key) => {
                            headers[key.toLowerCase()] = value;
                        });
                        window.responseHeaders = headers;
                        
                        return response;
                    }).catch(err => {
                        window.httpStatusCode = 0;  // Use 0 for network errors
                        throw err;
                    });
                };
            })(window.fetch);
            
            // Add error event listener to detect failed page loads
            window.addEventListener('error', function(e) {
                if (e && e.target && (e.target.localName === 'link' || e.target.localName === 'script')) {
                    console.error('Resource error:', e.target.src || e.target.href);
                }
            }, true);
            """
            
            # Execute the monitoring script
            driver.execute_script(add_response_monitoring_script)
            
            # Add helper method to get the last HTTP status
            def get_http_status(driver):
                try:
                    status = driver.execute_script("return window.httpStatusCode;")
                    return int(status) if status is not None else 200
                except:
                    return 200  # Default to 200 if we can't get status
                    
            # Add helper method to get response headers
            def get_response_headers(driver):
                try:
                    headers = driver.execute_script("return window.responseHeaders;")
                    return headers if headers else {}
                except:
                    return {}
                    
            # Attach methods to driver
            driver.get_http_status = types.MethodType(get_http_status, driver)
            driver.get_response_headers = types.MethodType(get_response_headers, driver)
            
            # Additional helper to extract network requests from logs
            def analyze_network_requests(driver):
                try:
                    # Get performance logs
                    logs = driver.get_log("performance")
                    
                    requests = []
                    for entry in logs:
                        try:
                            log = json.loads(entry["message"])["message"]
                            if log["method"] == "Network.responseReceived":
                                url = log["params"]["response"]["url"]
                                status = log["params"]["response"]["status"]
                                content_type = log["params"]["response"].get("headers", {}).get("content-type", "")
                                requests.append({
                                    "url": url,
                                    "status": status,
                                    "content_type": content_type
                                })
                        except:
                            pass
                    return requests
                except Exception as e:
                    return []
                    
            # Attach network analysis method to driver
            driver.analyze_network_requests = types.MethodType(analyze_network_requests, driver)
            
            # Override the original get method to capture HTTP status
            original_get = driver.get
            def get_with_status(self, url):
                try:
                    # Reset status code before navigation
                    self.execute_script("window.httpStatusCode = 200; window.responseHeaders = {};")
                    # Call original get method
                    original_get(url)
                    
                    # Give time for status to update
                    time.sleep(0.5)
                    
                    # Try to detect status codes from logs
                    requests = self.analyze_network_requests()
                    main_request = next((r for r in requests if r["url"] == url), None)
                    if main_request:
                        return main_request["status"]
                    
                    # Fall back to the JavaScript status code
                    return self.get_http_status()
                except Exception as e:
                    if isinstance(e, TimeoutException):
                        return 408  # Request Timeout
                    return 0  # General error
                    
            # Attach the new get method
            driver.get_with_status = types.MethodType(get_with_status, driver)
            
            return driver
            
        except (WebDriverException, SessionNotCreatedException) as e:
            print(f"WebDriver creation failed (attempt {attempt+1}/{retry_count}): {e}")
            time.sleep(2)
            
            if attempt == retry_count - 1:
                raise
    
    raise RuntimeError("Failed to create WebDriver after multiple attempts")
