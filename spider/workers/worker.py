#!/usr/bin/env python3
"""
Worker module that implements the crawling worker process with browser pooling.

This module contains the Worker class and worker_process function that handle
individual crawling tasks using a pool of reusable browser instances.
"""

import signal
import sys
import time
from queue import Empty
from multiprocessing import Process
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from selenium.common.exceptions import (InvalidSessionIdException,
                                       TimeoutException,
                                       WebDriverException)
from selenium.webdriver.common.by import By

from ..browser.pool import BrowserPool
from ..content.extractor import search_page_for_keywords
from ..content.markdown import html_to_markdown, save_markdown_file
from ..content.parser import determine_page_category
from ..utils.http import handle_response_code
from ..utils.url import (get_page_links, get_spa_links, is_webpage_url)
from ..browser.driver import ensure_no_chromedriver_zombies


class Worker:
    """
    Worker class that represents a crawler worker responsible for
    processing URLs and extracting content.
    """

    def __init__(self, worker_id, task_queue, result_queue, url_cache,
                base_domain, path_prefix, keywords, content_filter,
                initial_delay, headless=True, webdriver_path=None,
                max_restarts=3, allow_subdomains=False,
                allowed_extensions=None, is_spa=False, markdown_mode=False,
                retry_queue=None, active_workers=None,
                active_workers_lock=None, target_workers=None,
                browser_pool_size=3, browser_max_idle_time=300,
                use_browser_pool=True):
        """
        Initialize a Worker instance.

        Args:
            worker_id: Unique ID for this worker
            task_queue: Queue for receiving URLs to process
            result_queue: Queue for sending back results
            url_cache: Shared dict of processed URLs
            base_domain: Base domain to crawl
            path_prefix: Path prefix to restrict crawling
            keywords: List of keywords to search for
            content_filter: ContentFilter instance
            initial_delay: Initial delay between requests
            headless: Whether to run browser in headless mode
            webdriver_path: Path to WebDriver executable
            max_restarts: Maximum number of WebDriver restarts
            allow_subdomains: Whether to crawl across subdomains
            allowed_extensions: Additional file extensions to allow
            is_spa: Whether to use SPA-specific processing
            markdown_mode: Whether to save content as markdown
            retry_queue: Queue for URLs that need to be retried
            active_workers: Shared counter for active workers
            active_workers_lock: Lock for active_workers
            target_workers: Shared value for target worker count
            browser_pool_size: Size of browser pool (min_browsers)
            browser_max_idle_time: Maximum idle time for browsers in seconds
            use_browser_pool: Whether to use browser pooling
        """
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.url_cache = url_cache
        self.base_domain = base_domain
        self.path_prefix = path_prefix
        self.keywords = keywords
        self.content_filter = content_filter
        self.initial_delay = initial_delay
        self.current_delay = initial_delay
        self.headless = headless
        self.webdriver_path = webdriver_path
        self.max_restarts = max_restarts
        self.allow_subdomains = allow_subdomains
        self.allowed_extensions = allowed_extensions
        self.is_spa = is_spa
        self.markdown_mode = markdown_mode
        self.retry_queue = retry_queue
        self.active_workers = active_workers
        self.active_workers_lock = active_workers_lock
        self.target_workers = target_workers
        self.browser_pool_size = browser_pool_size
        self.browser_max_idle_time = browser_max_idle_time
        self.use_browser_pool = use_browser_pool
        
        self.driver = None
        self.restarts = 0
        self.last_delay_check = time.time()
        self.process = None

    def start(self):
        """Start the worker process."""
        self.process = Process(
            target=worker_process,
            args=(self.worker_id, self.task_queue, self.result_queue,
                  self.url_cache, self.base_domain, self.path_prefix,
                  self.keywords, self.content_filter, self.initial_delay,
                  self.headless, self.webdriver_path, self.max_restarts,
                  self.allow_subdomains, self.allowed_extensions,
                  self.is_spa, self.markdown_mode, self.retry_queue,
                  self.active_workers, self.active_workers_lock,
                  self.target_workers, self.browser_pool_size,
                  self.browser_max_idle_time, self.use_browser_pool)
        )
        self.process.daemon = True
        self.process.start()
        return self.process

    def stop(self, timeout=5):
        """
        Stop the worker process.
        
        Args:
            timeout: Timeout for joining the process
        """
        if self.process and self.process.is_alive():
            self.process.join(timeout=timeout)
            if self.process.is_alive():
                self.process.terminate()

    def is_alive(self):
        """Check if the worker process is alive."""
        return self.process and self.process.is_alive()

def worker_process(worker_id, task_queue, result_queue, url_cache, base_domain, path_prefix, 
                  keywords, content_filter, initial_delay, headless, webdriver_path, max_restarts, 
                  allow_subdomains=False, allowed_extensions=None, is_spa=False, markdown_mode=False,
                  retry_queue=None, active_workers=None, active_workers_lock=None, target_workers=None,
                  browser_pool_size=3, browser_max_idle_time=300, use_browser_pool=True):
    """
    Worker process that fetches URLs, extracts keywords and links.
    
    This function runs in a separate process and handles crawling tasks.

    Args:
        worker_id: ID for this worker
        task_queue: Queue for receiving URLs to process
        result_queue: Queue for sending back results
        url_cache: Shared dict of processed URLs
        base_domain: Base domain to crawl
        path_prefix: Path prefix to restrict crawling
        keywords: List of keywords to search for
        content_filter: ContentFilter instance
        initial_delay: Initial delay between requests
        headless: Whether to run browser in headless mode
        webdriver_path: Path to WebDriver executable
        max_restarts: Maximum number of WebDriver restarts
        allow_subdomains: Whether to crawl across subdomains
        allowed_extensions: Additional file extensions to allow
        is_spa: Whether to use SPA-specific processing
        markdown_mode: Whether to save content as markdown
        retry_queue: Queue for URLs that need to be retried
        active_workers: Shared counter for active workers
        active_workers_lock: Lock for active_workers
        target_workers: Shared value for target worker count
        browser_pool_size: Size of browser pool (min_browsers)
        browser_max_idle_time: Maximum idle time for browsers in seconds
        use_browser_pool: Whether to use browser pooling
    """
    print(f"Worker {worker_id} started and waiting for URLs")
    
    # Create a local copy of the delay that can be updated
    current_delay = initial_delay
    last_delay_check = time.time()
    startup_time = time.time()
    last_activity_time = time.time()
    
    # Track if we've ever received a URL
    received_url = False
    startup_timeout = 120  # Wait up to 2 minutes for initial URLs
    idle_timeout = 300     # Wait up to 5 minutes when idle after processing URLs
    
    # Increment active workers counter
    if active_workers_lock and active_workers:
        with active_workers_lock:
            active_workers.value += 1
            print(f"Worker {worker_id} incremented active count: {active_workers.value}")
    
    # Function to check and update delay from shared value
    def update_current_delay():
        nonlocal current_delay, last_delay_check
        now = time.time()
        
        # Check periodically
        if now - last_delay_check > 5:
            try:
                if target_workers and hasattr(target_workers, 'value'):
                    shared_delay = getattr(target_workers, 'current_delay', current_delay)
                    if hasattr(shared_delay, 'value'):
                        delay_value = shared_delay.value
                        if abs(current_delay - delay_value) > 0.1:
                            old_delay = current_delay
                            current_delay = delay_value
                            print(f"Worker {worker_id} updated delay: {old_delay:.2f}s → {current_delay:.2f}s")
            except:
                pass
            
            last_delay_check = now
        
        return current_delay
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        print(f"Worker {worker_id} received shutdown signal")
        try:
            # More aggressive cleanup
            if 'driver' in locals() and driver:
                print(f"Worker {worker_id} quitting WebDriver")
                try:
                    driver.quit()
                except:
                    pass
                
                # Extra step: try to find and kill the chromedriver process
                driver = None
                ensure_no_chromedriver_zombies()
        except:
            pass
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize browser pool or single WebDriver
    browser_pool = None
    driver = None
    use_undetected = False  # Flag to indicate if we should try undetected mode on failure
    # Start with single browser mode until system is stable
    initial_single_browser_period = True  # Start with single browser mode
    urls_processed = 0
    
    # Then later in the browser pool initialization section:
    if use_browser_pool and not initial_single_browser_period:
        try:
            from ..browser.pool import BrowserPool
            print(f"Worker {worker_id} initializing browser pool with size {browser_pool_size}")
            browser_pool = BrowserPool(
                min_browsers=1,  # Start with just 1 browser
                max_browsers=browser_pool_size,
                headless=headless,
                webdriver_path=webdriver_path,
                max_idle_time=browser_max_idle_time,
                check_interval=30
            )
            
            # Check if initialization succeeded by trying to get a browser
            browser = browser_pool.get_browser(timeout=10)
            if browser:
                # Return the browser to the pool if we got one
                browser_pool.release_browser(browser)
                print(f"Worker {worker_id} browser pool initialized successfully")
            else:
                # Fail if we couldn't get a browser
                print(f"Worker {worker_id} browser pool initialization failed: couldn't create or get browser")
                browser_pool = None
                use_browser_pool = False
        except Exception as e:
            print(f"Worker {worker_id} failed to initialize browser pool: {e}")
            browser_pool = None
            use_browser_pool = False
    
    try:
        # If not using browser pool, we'll initialize WebDriver when needed
        if not use_browser_pool or initial_single_browser_period:
            driver = None
            restarts = 0
        
        while True:
            try:
                # Get a URL from the queue
                try:
                    # Use a shorter timeout during startup, longer after receiving URLs
                    timeout = idle_timeout / 60 if received_url else 10
                    url = task_queue.get(timeout=timeout)
                    
                    # Mark that we've received a URL
                    if not received_url and url is not None:
                        received_url = True
                        print(f"Worker {worker_id} received first URL: {url}")
                    
                    # Update activity timestamp
                    last_activity_time = time.time()
                    
                except Empty:
                    # Check if parent has indicated shutdown via stop_event
                    # Since workers are in a separate process, we need another way to check
                    # We can use the task queue - if it's been closed or parent has stopped
                    # filling it, we should eventually exit
                    
                    if task_queue.empty():  # If queue is empty, check how long we've been idle
                        current_time = time.time()
                        
                        # If we've never received a URL, check for startup timeout
                        if not received_url:
                            elapsed = current_time - startup_time
                            if elapsed > startup_timeout:
                                print(f"Worker {worker_id} shutting down - no URLs received after {elapsed:.1f}s")
                                break
                            if elapsed % 30 < 1:  # Log every ~30 seconds to reduce noise
                                print(f"Worker {worker_id} waiting for initial URLs... ({elapsed:.1f}s/{startup_timeout}s)")
                            continue
                        else:
                            # If we've processed URLs before, check idle timeout
                            elapsed = current_time - last_activity_time
                            if elapsed > idle_timeout:
                                print(f"Worker {worker_id} shutting down - idle for {elapsed:.1f}s")
                                break
                            if elapsed % 60 < 1:  # Log every ~60 seconds
                                print(f"Worker {worker_id} waiting for more URLs... (idle for {elapsed:.1f}s)")
                                
                                # Additional check - if we've been idle for a significant time
                                # Check if the parent process might be shutting down
                                if elapsed > 120:  # After 2 minutes of inactivity
                                    print(f"Worker {worker_id} checking parent process status...")
                                    try:
                                        # Put a small dummy task to see if someone is listening
                                        # This is just a probe - it won't be processed
                                        task_queue.put_nowait("PROBE")
                                        # If we made it here, queue is still accepting tasks
                                        # which means parent hasn't closed it
                                    except:
                                        # If we get an error, queue may be closed
                                        print(f"Worker {worker_id} detected parent process shutdown")
                                        break
                            continue
                
                # Exit signal
                if url is None:
                    print(f"Worker {worker_id} received exit signal")
                    break
                
                # Process the URL
                try:
                    # Check if URL is a webpage before visiting
                    if not is_webpage_url(url, allowed_extensions):
                        print(f"Skipping non-webpage URL: {url}")
                        result_queue.put({
                            'url': url,
                            'status': 'skipped',
                            'reason': 'non-webpage-url'
                        })
                        continue
                    
                    # Get the current delay value from shared memory
                    delay_to_use = update_current_delay()
                    
                    # Apply the current delay before processing
                    print(f"Worker {worker_id} waiting {delay_to_use:.2f}s before processing {url}")
                    time.sleep(delay_to_use)
                    
                    # Use a browser from the pool or initialize/use the single driver
                    if use_browser_pool and not initial_single_browser_period and browser_pool is not None:
                        # Get a browser from the pool
                        browser = browser_pool.get_browser(timeout=30)
                        if not browser:
                            print(f"Worker {worker_id} couldn't get a browser from pool. Retrying URL later")
                            if retry_queue is not None:
                                retry_queue.put({
                                    'url': url,
                                    'retry_after': 10,
                                    'action': 'retry'
                                })
                            continue
                        
                        # Use the browser's driver
                        driver = browser.driver
                        process_success = False
                        
                        try:
                            # Process URL with the browser
                            process_success = process_url(driver, url, result_queue, 
                                                         keywords, content_filter, is_spa, 
                                                         base_domain, path_prefix, allow_subdomains, 
                                                         allowed_extensions, markdown_mode, retry_queue)
                            
                        finally:
                            # Release the browser back to the pool
                            browser_pool.release_browser(browser, success=process_success)
                    else:
                        # Initialize WebDriver if not already done
                        if driver is None:
                            try:
                                print(f"Worker {worker_id} initializing WebDriver for first URL")
                                
                                if use_undetected:
                                    # Try undetected mode if standard setup failed before
                                    try:
                                        from ..browser.undetected import setup_undetected_webdriver
                                        driver = setup_undetected_webdriver(headless=headless)
                                    except ImportError:
                                        from ..browser.driver import setup_webdriver
                                        driver = setup_webdriver(headless, webdriver_path)
                                else:
                                    # Standard setup
                                    from ..browser.driver import setup_webdriver
                                    driver = setup_webdriver(headless, webdriver_path)
                                    
                                    # Apply stealth mode if available
                                    try:
                                        from ..browser.stealth import apply_stealth_mode
                                        driver = apply_stealth_mode(driver)
                                    except ImportError:
                                        print("Stealth mode not available, proceeding without it")
                                    
                                    # Apply CDP features
                                    try:
                                        from ..browser.driver import enable_cdp_features
                                        driver = enable_cdp_features(driver)
                                        
                                        # Optionally block resources to speed up crawling
                                        # from ..browser.driver import enable_resource_blocking
                                        # driver = enable_resource_blocking(driver, block_images=True)
                                    except Exception as e:
                                        print(f"Could not enable CDP features: {e}")
                                    
                            except Exception as e:
                                print(f"Worker {worker_id} failed to initialize WebDriver: {e}")
                                # If standard mode fails, try undetected mode next time
                                if not use_undetected:
                                    use_undetected = True
                                    print(f"Will try undetected mode next time")
                                
                                # Put the URL back in the queue and continue
                                if retry_queue is not None:
                                    retry_queue.put({
                                        'url': url,
                                        'retry_after': 5,
                                        'action': 'retry'
                                    })
                                continue
                        
                        # Process the URL with the single driver
                        process_success = process_url(driver, url, result_queue, 
                                   keywords, content_filter, is_spa, 
                                   base_domain, path_prefix, allow_subdomains, 
                                   allowed_extensions, markdown_mode, retry_queue)
                        
                        # Browser pool initialization section
                        if use_browser_pool and initial_single_browser_period and urls_processed >= 3:
                            # Transition to browser pool mode after processing 3 URLs successfully
                            initial_single_browser_period = False
                            print(f"Worker {worker_id} completed initial stability period, enabling browser pool")
                            
                            try:
                                from ..browser.pool import BrowserPool
                                # Initialize browser pool with the target size but start with just 1 browser
                                print(f"Worker {worker_id} initializing browser pool with size {browser_pool_size}")
                                browser_pool = BrowserPool(
                                    min_browsers=1,           # Start with 1 browser
                                    max_browsers=browser_pool_size * 2,  # Allow room for growth 
                                    target_browsers=browser_pool_size,   # Target is the desired pool size
                                    headless=headless,
                                    webdriver_path=webdriver_path,
                                    max_idle_time=browser_max_idle_time,
                                    check_interval=30,        # Check browser health every 30 seconds
                                    growth_interval=60,       # Try to grow pool every 60 seconds
                                    success_threshold=5       # Need 5 successful operations before growing
                                )
                                
                                # Check if pool initialized correctly
                                if len(browser_pool.browsers) > 0:
                                    print(f"Worker {worker_id} browser pool initialized successfully with {len(browser_pool.browsers)} browsers")
                                    use_browser_pool = True
                                    
                                    # Close the current driver since we'll use the pool now
                                    if driver:
                                        try:
                                            driver.quit()
                                        except:
                                            pass
                                        driver = None
                                else:
                                    print(f"Worker {worker_id} browser pool initialization failed, continuing with single browser")
                                    use_browser_pool = False
                                    browser_pool = None
                            except Exception as e:
                                print(f"Worker {worker_id} failed to initialize browser pool: {e}")
                                use_browser_pool = False
                                browser_pool = None
                    
                    # Update activity timestamp after successful processing
                    last_activity_time = time.time()
                    
                except WebDriverException as e:
                    # Only handle this for single driver mode
                    if not use_browser_pool:
                        # Check for session errors that require restart
                        if isinstance(e, InvalidSessionIdException) or "invalid session id" in str(e) or "session deleted" in str(e) or "session not found" in str(e):
                            print(f"Worker {worker_id} WebDriver session error: {e}")
                            
                            # Close the current driver
                            try:
                                if driver:
                                    driver.quit()
                            except:
                                pass
                            
                            # Increment restart counter
                            restarts += 1
                            
                            if restarts > max_restarts:
                                print(f"Worker {worker_id} exceeded maximum restarts ({max_restarts}).")
                                result_queue.put({
                                    'url': url,
                                    'status': 'error',
                                    'error': str(e)
                                })
                                
                                # Put URL in retry queue if available
                                if retry_queue is not None:
                                    retry_queue.put({
                                        'url': url,
                                        'retry_after': 60,  # Give a longer delay for driver failure
                                        'action': 'retry'
                                    })
                                break
                            
                            # Set up a new WebDriver
                            print(f"Worker {worker_id} restarting WebDriver (attempt {restarts}/{max_restarts})...")
                            driver = None  # Will be initialized on next iteration
                            
                            # Put the URL back in the queue
                            if retry_queue is not None:
                                retry_queue.put({
                                    'url': url,
                                    'retry_after': 5,  # Short delay for driver restart
                                    'action': 'retry'
                                })
                            else:
                                task_queue.put(url)
                            
                        else:
                            print(f"Worker {worker_id} error processing {url}: {e}")
                            result_queue.put({
                                'url': url,
                                'status': 'error',
                                'error': str(e)
                            })
                            
                            # Put URL in retry queue if available
                            if retry_queue is not None:
                                retry_queue.put({
                                    'url': url,
                                    'retry_after': 30,  # Medium delay for general errors
                                    'action': 'retry_once'
                                })
                    
                except Exception as e:
                    print(f"Worker {worker_id} error processing {url}: {e}")
                    result_queue.put({
                        'url': url,
                        'status': 'error',
                        'error': str(e)
                    })
                    
                    # Put URL in retry queue if available
                    if retry_queue is not None:
                        retry_queue.put({
                            'url': url,
                            'retry_after': 30,  # Medium delay for general errors
                            'action': 'retry_once'
                        })
                    
            except Exception as e:
                print(f"Worker {worker_id} error: {e}")
                continue
                
    finally:
        # Clean up
        print(f"Worker {worker_id} shutting down")
        try:
            if browser_pool:
                browser_pool.stop()
            elif driver:
                driver.quit()
        except:
            pass

    if active_workers_lock and active_workers:
        with active_workers_lock:
            active_workers.value -= 1
            print(f"Worker {worker_id} decremented active count: {active_workers.value}")


def process_url(driver, url, result_queue, keywords, content_filter, is_spa, 
               base_domain, path_prefix, allow_subdomains, allowed_extensions, 
               markdown_mode, retry_queue=None):
    """
    Process a URL with the provided browser.
    
    Args:
        driver: Selenium WebDriver instance
        url: URL to process
        result_queue: Queue for sending results
        keywords: List of keywords to search for
        content_filter: ContentFilter instance
        is_spa: Whether to use SPA-specific processing
        base_domain: Base domain for crawling
        path_prefix: Path prefix to restrict crawling
        allow_subdomains: Whether to allow crawling across subdomains
        allowed_extensions: Additional file extensions to allow
        markdown_mode: Whether to save content as markdown
        retry_queue: Queue for URLs that need to be retried
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        print(f"Processing: {url}")
        
        try:
            # Navigate to URL
            driver.get(url)
            
            # Get HTTP status code using various methods
            http_status = 200  # Default status if detection fails
            
            # Try using Navigation Timing API
            try:
                status_from_perf = driver.execute_script("""
                    try {
                        // Get response status from performance API
                        let entries = performance.getEntriesByType('navigation');
                        if (entries && entries.length > 0 && entries[0].responseStatus) {
                            return entries[0].responseStatus;
                        }
                        return null;
                    } catch (e) {
                        return null;
                    }
                """)
                
                if status_from_perf and isinstance(status_from_perf, int):
                    http_status = status_from_perf
            except:
                pass
            
            # If we couldn't get status from performance API, check for error indications
            if http_status == 200:
                try:
                    title = driver.title.lower()
                    body_text = ""
                    try:
                        body_element = driver.find_element(By.TAG_NAME, "body")
                        body_text = body_element.text.lower()
                    except:
                        body_text = ""
                    
                    # Check for common error pages
                    if ("404" in title or "not found" in title or 
                        "404" in body_text and "not found" in body_text):
                        http_status = 404
                    elif ("403" in title or "forbidden" in title or 
                          "access denied" in body_text or "forbidden" in body_text):
                        http_status = 403
                    elif ("500" in title or "server error" in title or 
                          "internal server error" in body_text):
                        http_status = 500
                    elif ("429" in body_text or "too many requests" in body_text or 
                          "rate limit" in body_text):
                        http_status = 429
                except:
                    # If we can't check the page content, assume success
                    pass
                    
        except TimeoutException:
            # Timeout indicates a problem - treat as a 408 Request Timeout
            http_status = 408
        
        # Handle response based on status code
        response_handling = handle_response_code(url, http_status)
        
        if not response_handling['success']:
            print(f"HTTP error for {url}: {response_handling['reason']}")
            
            # Report the error to main process
            result_queue.put({
                'url': url,
                'status': 'http_error',
                'http_status': http_status,
                'handling': response_handling,
                'retry_queue': retry_queue is not None
            })
            
            # If retry is requested and retry queue exists
            if response_handling['action'] in ['retry', 'retry_once', 'throttle_and_retry'] and retry_queue is not None:
                # Put the URL in retry queue with any recommended delay
                retry_queue.put({
                    'url': url,
                    'retry_after': response_handling['retry_after'],
                    'action': response_handling['action']
                })
                
            # Skip further processing for error responses
            return False
        
        # For successful responses, continue with normal processing
        # Wait for content to load, especially for SPAs
        if is_spa:
            from ..browser.navigator import wait_for_spa_content
            wait_for_spa_content(driver)
        
        # Get links from the page (for both modes)
        links = get_spa_links(driver, url, base_domain, path_prefix, allow_subdomains, allowed_extensions) if is_spa else get_page_links(driver, url, base_domain, path_prefix, allow_subdomains, allowed_extensions)
        
        if markdown_mode:
            # For markdown mode: Get the page source after JavaScript execution
            page_content = driver.page_source
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(page_content, 'html.parser')
            
            # Apply content filtering by removing excluded elements
            excluded_selectors = content_filter.get_excluded_selectors()
            for selector in excluded_selectors:
                for element in soup.select(selector):
                    element.decompose()
            
            # Determine page category
            category = determine_page_category(soup, url)
            
            # Convert to markdown
            markdown_content = html_to_markdown(str(soup), url)
            
            # Domain name for directory structure
            domain = urlparse(url).netloc.replace('.', '_')
            
            # Save markdown file
            file_path = save_markdown_file(domain, category, url, markdown_content)
            
            # Send results back to main process
            result_queue.put({
                'url': url,
                'links': list(links),
                'status': 'success',
                'http_status': http_status,
                'markdown_saved': file_path,
                'category': category
            })
        else:
            # Original keyword search mode
            keyword_results = search_page_for_keywords(driver, url, keywords, content_filter)
            
            # Send results back to main process
            result_queue.put({
                'url': url,
                'keyword_results': keyword_results,
                'links': list(links),
                'status': 'success',
                'http_status': http_status
            })
        
        return True
        
    except Exception as e:
        # Handle exceptions and report error
        print(f"Error processing {url}: {e}")
        result_queue.put({
            'url': url,
            'status': 'error',
            'error': str(e)
        })
        
        # Put URL in retry queue if available
        if retry_queue is not None:
            retry_queue.put({
                'url': url,
                'retry_after': 30,  # Medium delay for general errors
                'action': 'retry_once'
            })
            
        return False