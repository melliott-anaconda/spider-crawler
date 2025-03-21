#!/usr/bin/env python3
"""
Worker module that implements the crawling worker process.

This module contains the Worker class and worker_process function that handle
individual crawling tasks.
"""

import json
import os
import re
import signal
import sys
import threading
import time
import traceback
from multiprocessing import Process
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from selenium.common.exceptions import (InvalidSessionIdException,
                                       SessionNotCreatedException,
                                       TimeoutException,
                                       WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

# Import these functions from your existing modules
# You'll need to adjust these imports based on your final structure
from ..browser.driver import setup_webdriver
from ..content.extractor import search_page_for_keywords
from ..content.filter import ContentFilter
from ..content.markdown import html_to_markdown, save_markdown_file
from ..content.parser import determine_page_category
from ..utils.http import handle_response_code
from ..utils.url import (get_page_links, get_spa_links, is_webpage_url,
                         normalize_url)


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
                active_workers_lock=None, target_workers=None):
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
                  self.target_workers)
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
                  retry_queue=None, active_workers=None, active_workers_lock=None, target_workers=None):
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
    """
    print(f"Worker {worker_id} started")
    
    # Create a local copy of the delay that can be updated
    current_delay = initial_delay
    last_delay_check = time.time()
    
    # Function to check and update delay from shared value
    def update_current_delay():
        nonlocal current_delay, last_delay_check
        now = time.time()
        
        # Check periodically
        if now - last_delay_check > 5:
            try:
                if target_workers and hasattr(target_workers, '_value'):
                    shared_delay = target_workers._value.get_obj().current_delay.value
                    if abs(current_delay - shared_delay) > 0.1:
                        old_delay = current_delay
                        current_delay = shared_delay
                        print(f"Worker {worker_id} updated delay: {old_delay:.2f}s → {current_delay:.2f}s")
            except:
                pass
            
            last_delay_check = now
        
        return current_delay
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        print(f"Worker {worker_id} received shutdown signal")
        try:
            if 'driver' in locals():
                driver.quit()
        except:
            pass
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Set up WebDriver for this worker
    driver = None
    try:
        driver = setup_webdriver(headless, webdriver_path)
        restarts = 0
        
        while True:
            try:
                # Get a URL from the queue
                url = task_queue.get()
                
                # Exit signal
                if url is None:
                    break
                    
                print(f"Worker {worker_id} processing: {url}")
                
                # Get the current delay value from shared memory
                delay_to_use = update_current_delay()
                
                # Apply the current delay before processing
                print(f"Worker {worker_id} waiting {delay_to_use:.2f}s before processing {url}")
                time.sleep(delay_to_use)
                
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
                        print(f"Worker {worker_id} - HTTP error for {url}: {response_handling['reason']}")
                        
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
                        continue
                    
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
                    
                except WebDriverException as e:
                    # Check for session errors that require restart
                    if any(error_text in str(e) for error_text in ["invalid session id", "session deleted", "session not found"]):
                        print(f"Worker {worker_id} WebDriver session error: {e}")
                        
                        # Close the current driver
                        try:
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
                        driver = setup_webdriver(headless, webdriver_path)
                        
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
            if driver:
                driver.quit()
        except:
            pass

    if active_workers_lock and active_workers:
        with active_workers_lock:
            active_workers.value -= 1
            print(f"Worker {worker_id} decremented active count: {active_workers.value}")
