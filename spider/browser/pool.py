#!/usr/bin/env python3
"""
Browser pool module with improved growth mechanism.

This module contains the BrowserPool class that manages a pool of browser
instances with gradual growth to the target size.
"""

import threading
import time
import random
from queue import Queue, Empty

from selenium.common.exceptions import (WebDriverException,
                                       InvalidSessionIdException,
                                       TimeoutException)

class BrowserInstance:
    """
    Represents a browser instance in the pool.
    
    This class tracks the state of a browser instance and provides
    methods for health checks and resets.
    """
    
    def __init__(self, browser_id, driver):
        """
        Initialize a browser instance.
        
        Args:
            browser_id: Unique ID for this browser
            driver: Selenium WebDriver instance
        """
        self.browser_id = browser_id
        self.driver = driver
        self.status = "idle"  # idle, busy, crashed
        self.last_activity = time.time()
        self.urls_processed = 0
        self.error_count = 0
        self.lock = threading.RLock()
        self.current_task = None
        
    def is_healthy(self):
        """
        Check if the browser instance is in a healthy state.
        
        Returns:
            bool: True if the browser is healthy, False otherwise
        """
        with self.lock:
            if self.status == "crashed":
                return False
                
            # Check if browser is responsive
            try:
                # Simple check to see if the browser responds
                self.driver.current_url
                return True
            except (InvalidSessionIdException, WebDriverException):
                self.status = "crashed"
                return False
                
    def reset(self, headless=True, webdriver_path=None):
        """
        Reset the browser instance by creating a new driver.
        
        Args:
            headless: Whether to run in headless mode
            webdriver_path: Path to WebDriver executable
            
        Returns:
            bool: True if reset was successful, False otherwise
        """
        with self.lock:
            try:
                # Close the old driver if it exists
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                    
                # Create a new driver
                from .driver import setup_webdriver
                self.driver = setup_webdriver(headless, webdriver_path)
                self.status = "idle"
                self.error_count = 0
                self.last_activity = time.time()
                return True
            except Exception as e:
                print(f"Error resetting browser {self.browser_id}: {e}")
                self.status = "crashed"
                return False
                
    def assign_task(self, task):
        """
        Assign a task to this browser instance.
        
        Args:
            task: Task to assign
            
        Returns:
            bool: True if assignment was successful, False otherwise
        """
        with self.lock:
            if self.status != "idle":
                return False
                
            self.status = "busy"
            self.current_task = task
            self.last_activity = time.time()
            return True
            
    def release(self, success=True):
        """
        Release the browser instance after task completion.
        
        Args:
            success: Whether the task was completed successfully
            
        Returns:
            bool: True if release was successful, False otherwise
        """
        with self.lock:
            if success:
                self.urls_processed += 1
                self.status = "idle"
                self.current_task = None
            else:
                self.error_count += 1
                
                # Mark as crashed if too many errors
                if self.error_count >= 3:
                    self.status = "crashed"
                else:
                    self.status = "idle"
                    self.current_task = None
            
            self.last_activity = time.time()
            return True


class BrowserPool:
    """
    Manages a pool of browser instances for reuse.
    
    This class maintains a pool of browser instances that can be
    checked out for tasks and checked back in when tasks are complete.
    """
    
    def __init__(self, min_browsers=1, max_browsers=3, headless=True, 
                webdriver_path=None, max_idle_time=300, check_interval=30,
                growth_interval=60, success_threshold=5):
        """
        Initialize the browser pool.
        
        Args:
            min_browsers: Initial minimum number of browsers to maintain
            max_browsers: Maximum number of browsers allowed
            headless: Whether to run browsers in headless mode
            webdriver_path: Path to WebDriver executable
            max_idle_time: Maximum idle time before a browser is recycled
            check_interval: Interval for health checks
            growth_interval: Seconds between growth attempts
            success_threshold: Number of successful operations before growing pool
        """
        # Set initial conservative values
        self.min_browsers = 1  # Always start with 1 browser
        self.target_browsers = min_browsers  # This is what we'll grow to
        self.max_browsers = max_browsers
        self.headless = headless
        self.webdriver_path = webdriver_path
        self.max_idle_time = max_idle_time
        self.check_interval = check_interval
        self.growth_interval = growth_interval
        self.success_threshold = success_threshold
        
        # Internal state
        self.browsers = []
        self.next_id = 0
        self.available_browsers = Queue()
        self.lock = threading.RLock()
        self.monitor_thread = None
        self.stopping = False
        self.last_growth_time = 0
        self.successful_operations = 0
        self.failed_operations = 0
        self.total_urls_processed = 0
        
        # Create initial browser instance
        print(f"Initializing browser pool with target size of {self.target_browsers}")
        self._initialize_pool()
        
    def _initialize_pool(self):
        """Initialize the browser pool with a single browser instance."""
        with self.lock:
            try:
                # Start with just one browser
                browser = self._create_browser()
                if browser:
                    # Start monitor thread for health checks and growth
                    self.monitor_thread = threading.Thread(target=self._monitor_browsers)
                    self.monitor_thread.daemon = True
                    self.monitor_thread.start()
                    print(f"Browser pool started with 1/{self.target_browsers} browsers")
                else:
                    print("Failed to create initial browser for pool")
            except Exception as e:
                print(f"Error initializing browser pool: {e}")
    
    def _create_browser(self):
        """
        Create a new browser instance and add it to the pool.
        
        Returns:
            BrowserInstance: The created browser instance, or None if creation failed
        """
        with self.lock:
            if len(self.browsers) >= self.max_browsers:
                return None
                
            try:
                # Create a new browser instance
                from .driver import setup_webdriver
                driver = setup_webdriver(self.headless, self.webdriver_path)
                
                # Apply stealth mode if available
                try:
                    from .stealth import apply_stealth_mode
                    driver = apply_stealth_mode(driver)
                except ImportError:
                    print("Stealth mode not available, proceeding without it")
                
                # Create a browser instance object
                browser_id = self.next_id
                self.next_id += 1
                browser = BrowserInstance(browser_id, driver)
                
                # Add to the pool
                self.browsers.append(browser)
                self.available_browsers.put(browser)
                
                print(f"Created browser instance {browser_id}, pool size: {len(self.browsers)}/{self.target_browsers}")
                return browser
            except Exception as e:
                print(f"Error creating browser: {e}")
                return None
    
    def get_browser(self, timeout=30):
        """
        Get a browser instance from the pool.
        
        Args:
            timeout: Maximum time to wait for a browser
            
        Returns:
            BrowserInstance: A browser instance, or None if none available
        """
        try:
            # Try to get a browser from the pool
            browser = self.available_browsers.get(timeout=timeout)
            
            # Check if the browser is healthy
            if not browser.is_healthy():
                print(f"Replacing unhealthy browser {browser.browser_id}")
                
                # Try to create a replacement
                with self.lock:
                    # Remove from the browsers list
                    self.browsers = [b for b in self.browsers if b.browser_id != browser.browser_id]
                    
                    # Try to quit the driver
                    try:
                        browser.driver.quit()
                    except:
                        pass
                    
                    # Create a replacement
                    replacement = self._create_browser()
                    if replacement:
                        return replacement
                    else:
                        # Failed to create replacement
                        return None
            
            return browser
        except Empty:
            # No browser available in the queue, try to create a new one
            with self.lock:
                if len(self.browsers) < self.max_browsers:
                    return self._create_browser()
                    
            # At maximum capacity, return None
            return None
    
    def release_browser(self, browser, success=True):
        """
        Release a browser back to the pool.
        
        Args:
            browser: Browser instance to release
            success: Whether the task was completed successfully
            
        Returns:
            bool: True if release was successful, False otherwise
        """
        if not browser:
            return False
        
        with self.lock:
            # Update statistics
            if success:
                self.successful_operations += 1
                self.total_urls_processed += 1
                self.failed_operations = max(0, self.failed_operations - 1)  # Reduce failure count
            else:
                self.failed_operations += 1
                self.successful_operations = max(0, self.successful_operations - 1)  # Reduce success count
        
        # Release the browser
        release_successful = browser.release(success)
        
        # If the browser is crashed, don't return it to the pool
        if browser.status == "crashed":
            with self.lock:
                # Remove from the browsers list
                self.browsers = [b for b in self.browsers if b.browser_id != browser.browser_id]
                
                # Try to quit the driver
                try:
                    browser.driver.quit()
                except:
                    pass
                
                # Create a replacement if below minimum
                if len(self.browsers) < self.min_browsers:
                    self._create_browser()
                    
            return True
            
        # If release was successful and browser is idle, return to the pool
        if release_successful and browser.status == "idle":
            self.available_browsers.put(browser)
            return True
            
        return False
    
    def _should_grow_pool(self):
        """
        Determine if the pool should grow based on usage patterns.
        
        Returns:
            bool: True if the pool should grow, False otherwise
        """
        with self.lock:
            # Don't grow beyond target
            if self.min_browsers >= self.target_browsers:
                return False
                
            # Check if enough time has passed since last growth
            current_time = time.time()
            if current_time - self.last_growth_time < self.growth_interval:
                return False
                
            # Check if we've had enough successful operations
            if self.successful_operations < self.success_threshold:
                return False
                
            # If too many failed operations, don't grow
            if self.failed_operations > self.successful_operations / 2:
                return False
            
            # Check if there's pressure on the pool (all browsers are busy)
            idle_browsers = sum(1 for b in self.browsers if b.status == "idle")
            if idle_browsers > 0:
                # If we have idle browsers, don't grow yet
                return False
                
            # All conditions for growth are met
            return True
    
    def _monitor_browsers(self):
        """Monitor browser health and manage pool size."""
        # Start with a shorter interval for initial checks
        check_interval = 15  
        
        while not self.stopping:
            try:
                # Sleep for the check interval
                time.sleep(check_interval)
                
                # Gradually increase to normal check interval
                check_interval = min(self.check_interval, check_interval + 5)
                
                with self.lock:
                    current_time = time.time()
                    idle_browsers = []
                    crashed_browsers = []
                    
                    # Check all browsers
                    for browser in self.browsers:
                        if browser.status == "crashed":
                            crashed_browsers.append(browser)
                        elif browser.status == "idle":
                            idle_time = current_time - browser.last_activity
                            if idle_time > self.max_idle_time:
                                idle_browsers.append(browser)
                    
                    # Remove crashed browsers
                    for browser in crashed_browsers:
                        try:
                            browser.driver.quit()
                        except:
                            pass
                        
                        self.browsers.remove(browser)
                    
                    # Recycle idle browsers if pool is above minimum size
                    excess_browsers = len(self.browsers) - self.min_browsers
                    
                    if excess_browsers > 0 and idle_browsers:
                        # Sort by idle time (longest first)
                        idle_browsers.sort(key=lambda b: current_time - b.last_activity, reverse=True)
                        
                        # Recycle up to excess_browsers
                        for browser in idle_browsers[:excess_browsers]:
                            try:
                                # Remove from the pool
                                self.browsers.remove(browser)
                                
                                # Remove from the queue if present
                                try:
                                    while True:
                                        b = self.available_browsers.get_nowait()
                                        if b.browser_id != browser.browser_id:
                                            self.available_browsers.put(b)
                                except Empty:
                                    pass
                                    
                                # Quit the driver
                                browser.driver.quit()
                                print(f"Recycled idle browser {browser.browser_id}, idle for {current_time - browser.last_activity:.1f}s")
                            except:
                                pass
                    
                    # Check if we should grow the pool
                    if self._should_grow_pool():
                        # Increase min_browsers for growth
                        self.min_browsers += 1
                        self.last_growth_time = current_time
                        self.successful_operations = 0  # Reset counter
                        
                        print(f"Growing browser pool to {self.min_browsers}/{self.target_browsers} browsers")
                        
                        # Create a new browser
                        self._create_browser()
                    
                    # Create new browsers if needed to maintain minimum
                    browsers_to_create = self.min_browsers - len(self.browsers)
                    for _ in range(browsers_to_create):
                        self._create_browser()
                        
            except Exception as e:
                print(f"Error in browser monitor: {e}")
    
    def get_statistics(self):
        """
        Get statistics about the browser pool.
        
        Returns:
            dict: Pool statistics
        """
        with self.lock:
            stats = {
                'pool_size': len(self.browsers),
                'min_browsers': self.min_browsers,
                'target_browsers': self.target_browsers,
                'max_browsers': self.max_browsers,
                'idle_browsers': sum(1 for b in self.browsers if b.status == "idle"),
                'busy_browsers': sum(1 for b in self.browsers if b.status == "busy"),
                'crashed_browsers': sum(1 for b in self.browsers if b.status == "crashed"),
                'available_browsers': self.available_browsers.qsize(),
                'successful_operations': self.successful_operations,
                'failed_operations': self.failed_operations,
                'total_urls_processed': self.total_urls_processed,
                'time_since_last_growth': time.time() - self.last_growth_time
            }
            return stats
    
    def stop(self):
        """Stop the browser pool and close all browser instances."""
        with self.lock:
            self.stopping = True
            
            # Close all browser instances
            for browser in self.browsers:
                try:
                    browser.driver.quit()
                except:
                    pass
            
            # Clear the pool
            self.browsers = []
            
            # Clear the queue
            try:
                while True:
                    self.available_browsers.get_nowait()
            except Empty:
                pass
            
            # Wait for monitor thread to finish
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=5)