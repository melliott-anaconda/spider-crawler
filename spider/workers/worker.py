#!/usr/bin/env python3
"""
Worker module that implements the crawling worker process.

This module contains the Worker class and worker_process function that handle
individual crawling tasks.
"""

import signal
import sys
import time
from multiprocessing import Process
from queue import Empty
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# Import the browser factory
from ..browser import create_browser, wait_for_spa_content, extract_links, execute_browser_script, clean_cookie_elements
from ..content.extractor import search_page_for_keywords
from ..content.markdown import html_to_markdown, save_markdown_file
from ..content.parser import determine_page_category
from ..utils.http import handle_response_code
from ..utils.url import is_webpage_url


class Worker:
    """
    Worker class that represents a crawler worker responsible for
    processing URLs and extracting content.
    """

    def __init__(
        self,
        worker_id,
        task_queue,
        result_queue,
        url_cache,
        base_domain,
        path_prefix,
        keywords,
        content_filter,
        initial_delay,
        headless=True,
        webdriver_path=None,
        max_restarts=3,
        allow_subdomains=False,
        allowed_extensions=None,
        is_spa=False,
        markdown_mode=False,
        retry_queue=None,
        active_workers=None,
        active_workers_lock=None,
        target_workers=None,
        browser_engine="selenium",
        browser_type="chromium",
    ):
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
        self.browser_engine = browser_engine
        self.browser_type = browser_type

        self.driver = None
        self.restarts = 0
        self.last_delay_check = time.time()
        self.process = None

    def start(self):
        """Start the worker process."""
        self.process = Process(
            target=worker_process,
            args=(
                self.worker_id,
                self.task_queue,
                self.result_queue,
                self.url_cache,
                self.base_domain,
                self.path_prefix,
                self.keywords,
                self.content_filter,
                self.initial_delay,
                self.headless,
                self.webdriver_path,
                self.max_restarts,
                self.allow_subdomains,
                self.allowed_extensions,
                self.is_spa,
                self.markdown_mode,
                self.retry_queue,
                self.active_workers,
                self.active_workers_lock,
                self.target_workers,
                self.browser_engine,
                self.browser_type,
            ),
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


def worker_process(
    worker_id,
    task_queue,
    result_queue,
    url_cache,
    base_domain,
    path_prefix,
    keywords,
    content_filter,
    initial_delay,
    headless,
    webdriver_path,
    max_restarts,
    allow_subdomains=False,
    allowed_extensions=None,
    is_spa=False,
    markdown_mode=False,
    retry_queue=None,
    active_workers=None,
    active_workers_lock=None,
    target_workers=None,
    browser_engine="selenium",
    browser_type="chrome",
):
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
        allow_subdomains: Whether to allow crawling across subdomains
        allowed_extensions: Set of additional file extensions to allow
        is_spa: Whether to use SPA-specific processing
        markdown_mode: Whether to save content as markdown
        retry_queue: Queue for URLs that need to be retried
        active_workers: Shared counter for active workers
        active_workers_lock: Lock for active_workers
        target_workers: Shared value for target worker count
        browser_engine: Browser engine to use ("selenium" or "playwright")
        browser_type: Browser type for playwright ("chromium", "chrome", "webkit", or "firefox")
    """
    print(f"Worker {worker_id} started and waiting for URLs (using {browser_engine} engine on {browser_type})")

    # Create a local copy of the delay that can be updated
    current_delay = initial_delay
    last_delay_check = time.time()
    startup_time = time.time()
    last_activity_time = time.time()

    # Track if we've ever received a URL
    received_url = False
    startup_timeout = 20  # Reduced from 120s to 20s
    idle_timeout = 20     # Reduced from 300s to 20s

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
                if target_workers and hasattr(target_workers, "value"):
                    shared_delay = getattr(
                        target_workers, "current_delay", current_delay
                    )
                    if hasattr(shared_delay, "value"):
                        delay_value = shared_delay.value
                        if abs(current_delay - delay_value) > 0.1:
                            old_delay = current_delay
                            current_delay = delay_value
                            print(
                                f"Worker {worker_id} updated delay: {old_delay:.2f}s → {current_delay:.2f}s"
                            )
            except:
                pass

            last_delay_check = now

        return current_delay

    # Setup signal handlers
    def signal_handler(sig, frame):
        print(f"Worker {worker_id} received shutdown signal")
        try:
            if "browser" in locals() and browser:
                browser.quit()
        except Exception as e:
            print(f"Worker {worker_id} browser quit error: {e}")
        
        # Don't call sys.exit() here, just break out of the main loop
        nonlocal received_exit_signal
        received_exit_signal = True

    # Add a flag to track if we received an exit signal
    received_exit_signal = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Set up browser for this worker (delayed initialization)
    browser = None
    restarts = 0
    
    # Status reporting to main process
    last_status_report = time.time()
    
    try:
        while True:
            # Check exit signal at the start of the loop
            if received_exit_signal:
                print(f"Worker {worker_id} exiting due to signal")
                break
            try:
                # Report worker status periodically
                current_time = time.time()
                if current_time - last_status_report > 10:  # Every 10 seconds
                    # Report worker status to main process
                    result_queue.put({
                        "status": "worker_status",
                        "worker_id": worker_id,
                        "idle_time": current_time - last_activity_time,
                        "received_url": received_url
                    })
                    last_status_report = current_time
                
                # Get a URL from the queue
                try:
                    # Use a shorter timeout to check the queue more frequently
                    # This makes shutdown more responsive
                    timeout = 5.0  # Check queue every 5 seconds
                    url_info = task_queue.get(timeout=timeout)

                    # Mark that we've received a URL
                    if not received_url and url_info is not None:
                        received_url = True
                        
                        # Handle both tuple and string formats
                        if isinstance(url_info, tuple):
                            url, depth = url_info
                            print(f"Worker {worker_id} received first URL: {url} (depth: {depth})")
                        else:
                            url = url_info
                            depth = 0  # Default to depth 0 if not specified
                            print(f"Worker {worker_id} received first URL: {url}")

                    # Update activity timestamp
                    last_activity_time = time.time()

                except Empty:
                    # Check timeouts
                    current_time = time.time()
                    
                    # If we've never received a URL, check for startup timeout
                    if not received_url:
                        elapsed = current_time - startup_time
                        if elapsed > startup_timeout:
                            print(f"Worker {worker_id} shutting down - no URLs received after {elapsed:.1f}s")
                            # Report shutdown to main process
                            result_queue.put({
                                "status": "worker_shutdown",
                                "worker_id": worker_id,
                                "reason": "startup_timeout"
                            })
                            break
                        continue
                    else:
                        # If we've processed URLs before, check idle timeout
                        elapsed = current_time - last_activity_time
                        if elapsed > idle_timeout:
                            print(f"Worker {worker_id} shutting down - idle for {elapsed:.1f}s")
                            # Report shutdown to main process
                            result_queue.put({
                                "status": "worker_shutdown",
                                "worker_id": worker_id,
                                "reason": "idle_timeout"
                            })
                            break
                        continue

                # Exit signal
                if url_info is None:
                    print(f"Worker {worker_id} received exit signal")
                    # Report shutdown to main process
                    result_queue.put({
                        "status": "worker_shutdown",
                        "worker_id": worker_id,
                        "reason": "exit_signal"
                    })
                    break
                    
                # Extract URL and depth from the tuple
                if isinstance(url_info, tuple):
                    url, depth = url_info
                else:
                    url = url_info
                    depth = 0  # Default depth
                    
                print(f"Worker {worker_id} processing: {url} (depth: {depth})")

                # Initialize browser if not already done
                if browser is None:
                    try:
                        print(
                            f"Worker {worker_id} initializing {browser_engine} browser for first URL"
                        )
                        
                        # Use the factory to create a browser instance with the specified engine
                        browser = create_browser(
                            engine=browser_engine,
                            headless=headless,
                            webdriver_path=webdriver_path,
                            page_load_timeout=30 if browser_engine == "selenium" else 30000,
                            retry_count=3,
                            type=browser_type,
                        )
                        
                    except Exception as e:
                        print(f"Worker {worker_id} failed to initialize browser: {e}")
                        
                        # Put the URL back in the queue and continue
                        if retry_queue is not None:
                            retry_queue.put(
                                {"url": url, "retry_after": 5, "action": "retry"}
                            )
                        continue

                print(f"Worker {worker_id} processing: {url}")

                # Get the current delay value from shared memory
                delay_to_use = update_current_delay()

                # Apply the current delay before processing
                print(
                    f"Worker {worker_id} waiting {delay_to_use:.2f}s before processing {url}"
                )
                time.sleep(delay_to_use)

                # Process the URL
                try:
                    # Check if URL is a webpage before visiting
                    if not is_webpage_url(url, allowed_extensions):
                        print(f"Skipping non-webpage URL: {url}")
                        result_queue.put(
                            {
                                "url": url,
                                "status": "skipped",
                                "reason": "non-webpage-url",
                            }
                        )
                        continue

                    try:
                        # Navigate to URL
                        browser.get(url)

                        try:
                            is_loaded = execute_browser_script(browser, "() => document.readyState === 'complete'")
                            dom_elements = execute_browser_script(browser, "() => document.body.children.length")
                            print(f"Page loaded: {is_loaded}, DOM elements: {dom_elements}")
                            
                            # Check for SPA frameworks
                            frameworks = execute_browser_script(browser, """
                                () => {
                                    const detections = [];
                                    if (window.React || document.querySelector('[data-reactroot]')) detections.push('React');
                                    if (window.angular || document.querySelector('[ng-app]')) detections.push('Angular');
                                    if (window.Vue || document.querySelector('[data-v-]')) detections.push('Vue');
                                    return detections.join(', ') || 'None detected';
                                }
                            """)
                            print(f"Detected frameworks: {frameworks}")
                        except Exception as e:
                            print(f"Error checking page load: {e}")
                    
                        clean_cookie_elements(browser)

                        blocked_content = execute_browser_script(browser, """
                            () => {
                                const checks = [];
                                if (document.body.textContent.includes('security check')) checks.push('Security check text');
                                if (document.body.textContent.includes('blocked')) checks.push('Blocked text');
                                if (document.body.textContent.includes('captcha')) checks.push('Captcha text');
                                if (document.body.textContent.includes('proxy')) checks.push('Proxy detection');
                                if (document.body.textContent.includes('cloudflare')) checks.push('Cloudflare');
                                return checks.join(', ');
                            }
                        """)
                        if blocked_content:
                            print(f"Possible blocking content detected: {blocked_content}")

                        # Get HTTP status code 
                        http_status = 200  # Default status if detection fails
                        
                        try:
                            # Use our browser abstraction to get the HTTP status
                            http_status = browser.get_http_status()
                        except:
                            # Fallback to checking page content for error indications
                            # This section can remain mostly unchanged from the original
                            try:
                                title = browser.title.lower() if hasattr(browser, 'title') else ""
                                body_text = ""
                                try:
                                    body_element = browser.find_element("tag name", "body")
                                    body_text = body_element.text.lower()
                                except:
                                    body_text = ""

                                # Check for common error pages
                                if (
                                    "404" in title
                                    or "not found" in title
                                    or "404" in body_text
                                    and "not found" in body_text
                                ):
                                    http_status = 404
                                elif (
                                    "403" in title
                                    or "forbidden" in title
                                    or "access denied" in body_text
                                    or "forbidden" in body_text
                                ):
                                    http_status = 403
                                elif (
                                    "500" in title
                                    or "server error" in title
                                    or "internal server error" in body_text
                                ):
                                    http_status = 500
                                elif (
                                    "429" in body_text
                                    or "too many requests" in body_text
                                    or "rate limit" in body_text
                                ):
                                    http_status = 429
                            except:
                                # If we can't check the page content, assume success
                                pass

                    except Exception as e:
                        if "timeout" in str(e).lower():
                            # Timeout indicates a problem - treat as a 408 Request Timeout
                            http_status = 408
                        else:
                            # Other errors - continue with error handling
                            raise

                    # Handle response based on status code
                    response_handling = handle_response_code(url, http_status)

                    if not response_handling["success"]:
                        print(
                            f"Worker {worker_id} - HTTP error for {url}: {response_handling['reason']}"
                        )

                        # Report the error to main process
                        result_queue.put(
                            {
                                "url": url,
                                "status": "http_error",
                                "http_status": http_status,
                                "handling": response_handling,
                                "retry_queue": retry_queue is not None,
                            }
                        )

                        # If retry is requested and retry queue exists
                        if (
                            response_handling["action"]
                            in ["retry", "retry_once", "throttle_and_retry"]
                            and retry_queue is not None
                        ):
                            # Put the URL in retry queue with any recommended delay
                            retry_queue.put(
                                {
                                    "url": url,
                                    "retry_after": response_handling["retry_after"],
                                    "action": response_handling["action"],
                                }
                            )

                        # Skip further processing for error responses
                        continue

                    # For successful responses, continue with normal processing
                    # Wait for content to load, especially for SPAs
                    if is_spa:
                        # Use the abstracted function for both engines
                        wait_for_spa_content(browser)

                    # Get links from the page using our abstracted function
                    links = extract_links(
                        browser,
                        url,
                        base_domain,
                        path_prefix,
                        allow_subdomains,
                        allowed_extensions,
                        is_spa
                    )

                    if markdown_mode:
                        # For markdown mode: Get the page source after JavaScript execution
                        page_content = browser.page_source

                        # Parse with BeautifulSoup
                        soup = BeautifulSoup(page_content, "html.parser")

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
                        domain = urlparse(url).netloc.replace(".", "_")

                        # Save markdown file
                        file_path = save_markdown_file(
                            domain, category, url, markdown_content
                        )

                        # Send results back to main process
                        result_queue.put(
                            {
                                "url": url,
                                "links": list(links),
                                "status": "success",
                                "http_status": http_status,
                                "markdown_saved": file_path,
                                "category": category,
                                "depth": depth,
                            }
                        )
                    else:
                        # Original keyword search mode
                        keyword_results = search_page_for_keywords(
                            browser, url, keywords, content_filter
                        )

                        # Send results back to main process
                        result_queue.put(
                            {
                                "url": url,
                                "keyword_results": keyword_results,
                                "links": list(links),
                                "status": "success",
                                "http_status": http_status,
                                "depth": depth,
                            }
                        )

                    # Update activity timestamp after successful processing
                    last_activity_time = time.time()

                except Exception as e:
                    # Check for browser-specific errors that require restart
                    browser_error = False
                    
                    # Check for known errors that indicate browser issues
                    error_str = str(e).lower()
                    if any(err in error_str for err in [
                        "invalid session", "session deleted", "session not found",
                        "browser closed", "target closed", "connection closed",
                        "browser has disconnected", "browser context",
                        "browser crashed"
                    ]):
                        browser_error = True
                        
                    if browser_error:
                        print(f"Worker {worker_id} browser session error: {e}")

                        # Close the current browser
                        try:
                            if browser:
                                browser.quit()
                                browser = None
                        except:
                            pass

                        # Increment restart counter
                        restarts += 1

                        if restarts > max_restarts:
                            print(
                                f"Worker {worker_id} exceeded maximum restarts ({max_restarts})."
                            )
                            result_queue.put(
                                {"url": url, "status": "error", "error": str(e)}
                            )

                            # Put URL in retry queue if available
                            if retry_queue is not None:
                                retry_queue.put(
                                    {
                                        "url": url,
                                        "retry_after": 60,  # Give a longer delay for browser failure
                                        "action": "retry",
                                    }
                                )
                            break

                        # Set up a new browser
                        print(
                            f"Worker {worker_id} restarting browser (attempt {restarts}/{max_restarts})..."
                        )
                        browser = create_browser(
                            engine=browser_engine,
                            headless=headless,
                            webdriver_path=webdriver_path,
                            page_load_timeout=30 if browser_engine == "selenium" else 30000,
                            retry_count=3,
                            type=browser_type
                        )

                        # Put the URL back in the queue
                        if retry_queue is not None:
                            retry_queue.put(
                                {
                                    "url": url,
                                    "retry_after": 5,  # Short delay for browser restart
                                    "action": "retry",
                                }
                            )
                        else:
                            task_queue.put(url)

                    else:
                        print(f"Worker {worker_id} error processing {url}: {e}")
                        result_queue.put(
                            {"url": url, "status": "error", "error": str(e)}
                        )

                        # Put URL in retry queue if available
                        if retry_queue is not None:
                            retry_queue.put(
                                {
                                    "url": url,
                                    "retry_after": 30,  # Medium delay for general errors
                                    "action": "retry_once",
                                }
                            )

            except Exception as e:
                print(f"Worker {worker_id} error: {e}")
                continue

    finally:
        # Clean up
        print(f"Worker {worker_id} shutting down")
        try:
            if browser:
                browser.quit()
        except:
            pass

        # Decrement active workers counter
        if active_workers_lock and active_workers:
            with active_workers_lock:
                active_workers.value -= 1
                print(f"Worker {worker_id} decremented active count: {active_workers.value}")
                
        # Final shutdown notification
        try:
            result_queue.put({
                "status": "worker_shutdown_complete",
                "worker_id": worker_id
            })
        except:
            pass  # Queue might be closed