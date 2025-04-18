#!/usr/bin/env python3
"""
Worker pool manager module that handles multiple crawler workers.

This module contains the WorkerPool class that manages the lifecycle and
coordination of multiple crawler worker processes.
"""

import threading
import time
from multiprocessing import Lock, Queue, Value

from .worker import Worker


class WorkerPool:
    """
    Manages a pool of worker processes for parallel web crawling.

    This class handles creating, monitoring, and adjusting the number of
    worker processes based on crawl rate controller directives.
    """

    def __init__(
        self,
        spider,
        initial_workers,
        task_queue,
        result_queue,
        url_cache,
        base_domain,
        path_prefix,
        keywords,
        content_filter,
        rate_controller,
        headless=True,
        webdriver_path=None,
        max_restarts=3,
        allow_subdomains=False,
        allowed_extensions=None,
        is_spa=False,
        markdown_mode=False,
        use_undetected=False,
        browser_engine="selenium",
        browser_type="chromium",
    ):
        """
        Initialize the worker pool.

        Args:
            initial_workers: Initial number of workers to start
            task_queue: Queue for distributing URLs to workers
            result_queue: Queue for collecting results from workers
            url_cache: Shared dictionary for tracking visited URLs
            base_domain: Base domain for crawling
            path_prefix: Path prefix to restrict crawling
            keywords: List of keywords to search for
            content_filter: ContentFilter instance
            rate_controller: RateController instance
            headless: Whether to run browsers in headless mode
            webdriver_path: Path to WebDriver executable
            max_restarts: Maximum WebDriver restarts per worker
            allow_subdomains: Whether to crawl across subdomains
            allowed_extensions: Additional file extensions to allow
            is_spa: Whether to use SPA-specific processing
            markdown_mode: Whether to save content as markdown
        """
        """Initialize the worker pool."""
        self.spider = spider
        self.initial_workers = initial_workers
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.url_cache = url_cache
        self.base_domain = base_domain
        self.path_prefix = path_prefix
        self.keywords = keywords
        self.content_filter = content_filter
        self.rate_controller = rate_controller
        self.headless = headless
        self.webdriver_path = webdriver_path
        self.max_restarts = max_restarts
        self.allow_subdomains = allow_subdomains
        self.allowed_extensions = allowed_extensions
        self.is_spa = is_spa
        self.markdown_mode = markdown_mode
        self.use_undetected = use_undetected
        self.browser_engine = browser_engine
        self.browser_type = browser_type

        # Set up worker tracking
        self.workers = []
        self.worker_processes = {}
        self.next_worker_id = 0

        # Create shared resources for worker coordination
        self.retry_queue = Queue()  # Queue for URLs that need to be retried
        self.active_workers = Value("i", 0)
        self.active_workers_lock = Lock()

        # Shared values for rate control
        self.current_delay = Value("d", self.rate_controller.current_delay)
        self.target_workers = Value("i", self.rate_controller.target_workers)

        # Thread for monitoring and adjusting workers
        self.monitor_thread = None
        self.is_running = False
        self.stop_event = threading.Event()

    def start(self):
        """Start the worker pool with the initial number of workers."""
        self.is_running = True
        self.active_workers.value = 0

        # Initialize current rate control values
        with self.rate_controller.lock:
            self.current_delay.value = self.rate_controller.current_delay
            self.target_workers.value = self.rate_controller.target_workers

        # Start initial workers
        for _ in range(self.target_workers.value):
            self.start_new_worker()

        # Start monitor thread
        self.monitor_thread = threading.Thread(target=self._monitor_workers)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        return self.workers

    def start_new_worker(self):
        """
        Start a new worker process.

        Returns:
            int: Worker ID of the new worker
        """
        worker_id = self.next_worker_id
        self.next_worker_id += 1

        # Create worker instance with browser_engine parameter
        worker = Worker(
            worker_id=worker_id,
            task_queue=self.task_queue,
            result_queue=self.result_queue,
            url_cache=self.url_cache,
            base_domain=self.base_domain,
            path_prefix=self.path_prefix,
            keywords=self.keywords,
            content_filter=self.content_filter,
            initial_delay=self.current_delay.value,
            headless=self.headless,
            webdriver_path=self.webdriver_path,
            max_restarts=self.max_restarts,
            allow_subdomains=self.allow_subdomains,
            allowed_extensions=self.allowed_extensions,
            is_spa=self.is_spa,
            markdown_mode=self.markdown_mode,
            retry_queue=self.retry_queue,
            active_workers=self.active_workers,
            active_workers_lock=self.active_workers_lock,
            target_workers=self.target_workers,
            browser_engine=self.browser_engine, 
            browser_type=self.browser_type,
        )

        # Start worker process
        process = worker.start()

        # Track the worker
        self.workers.append(worker)
        self.worker_processes[worker_id] = worker

        print(f"Started worker {worker_id} with delay={self.current_delay.value:.2f}s using {self.browser_engine} engine")
        return worker_id

    def adjust_worker_count(self):
        """
        Adjust the number of workers based on target worker count.

        This method adds or removes workers to match the target count.
        """
        # Get current target from rate controller
        target = self.target_workers.value

        # Get a list of currently alive workers
        alive_workers = [w for w in self.workers if w.is_alive()]
        current_count = len(alive_workers)

        print(f"Adjusting worker count: current={current_count}, target={target}")

        # If we need fewer workers, terminate excess workers
        if current_count > target:
            excess = current_count - target
            print(
                f"Need to terminate {excess} workers to reduce from {current_count} to {target}"
            )

            # Create a list of workers to terminate (last 'excess' workers)
            workers_to_terminate = alive_workers[-excess:]

            # Terminate these workers
            for worker in workers_to_terminate:
                print(f"Terminating worker {worker.worker_id}")
                worker.stop()

            # Update the workers list
            self.workers = [w for w in self.workers if w.is_alive()]

        # If we need more workers, start new ones
        elif current_count < target:
            to_start = target - current_count
            print(
                f"Need to start {to_start} new workers to increase from {current_count} to {target}"
            )

            for _ in range(to_start):
                self.start_new_worker()
        """
        Monitor worker processes and adjust as needed.
        """
        while not self.stop_event.is_set() and self.spider.is_running:
            try:
                # Check for completed or dead workers
                alive_workers = [w for w in self.workers if w.is_alive()]

                # If some workers died unexpectedly, remove them from our list
                if len(alive_workers) != len(self.workers):
                    # Only treat as unexpected death if we're not in controlled shutdown
                    if not self.spider.controlled_shutdown:
                        print(
                            f"Some workers died unexpectedly. Alive: {len(alive_workers)}/{len(self.workers)}"
                        )
                        self.workers = alive_workers
                    else:
                        # In controlled shutdown, just update the list
                        self.workers = alive_workers

                # Check if we need to adjust worker count based on rate controller
                target = self.target_workers.value
                current_count = len(alive_workers)

                # Only adjust if not in controlled shutdown
                if current_count != target and not self.spider.controlled_shutdown:
                    self.adjust_worker_count()

                # Update current delay value from rate controller
                with self.rate_controller.lock:
                    new_delay = self.rate_controller.current_delay
                    if abs(new_delay - self.current_delay.value) > 0.1:
                        self.current_delay.value = new_delay
                        print(f"Updated shared delay value to {new_delay:.2f}s")

                # Process retry queue
                self._process_retry_queue()

                # Wait before next check
                time.sleep(5)

            except Exception as e:
                print(f"Error in worker monitor thread: {e}")
                time.sleep(10)  # Wait longer on error

    def _process_retry_queue(self):
        """Process URLs in the retry queue."""
        # This would handle transferring items from retry queue back to task queue
        # when their retry delay has elapsed
        pass

    def active_workers_count(self):
        """
        Get the current number of active workers.

        Returns:
            int: Number of active workers
        """
        alive_workers = [w for w in self.workers if w.is_alive()]
        return len(alive_workers)

    def stop(self, timeout=3):  # Reduced timeout from 5s to 3s
        """
        Stop all worker processes with improved termination.
        """
        self.is_running = False
        self.stop_event.set()

        # Quick check for any active workers
        alive_workers = [w for w in self.workers if w.is_alive()]
        if not alive_workers:
            print("No active workers to stop")
            return

        print(f"Stopping {len(alive_workers)} worker processes")

        # Clear the task queue to prevent workers from getting stuck on new tasks
        try:
            while not self.task_queue.empty():
                try:
                    self.task_queue.get(block=False)
                except:
                    break
        except:
            pass

        # Send exit signal to each worker (more than needed to ensure delivery)
        for _ in range(len(alive_workers) * 2):
            try:
                self.task_queue.put(None)
            except:
                break

        # First, try graceful shutdown with a short timeout
        graceful_timeout = min(1.0, timeout / 3)
        start_time = time.time()
        
        while time.time() - start_time < graceful_timeout:
            alive_workers = [w for w in self.workers if w.is_alive()]
            if not alive_workers:
                break
            time.sleep(0.1)
            
        # For any remaining workers, stop them individually
        for worker in self.workers:
            if worker.is_alive():
                worker.stop(timeout=max(0.5, timeout/2))

        # Clear worker lists
        self.workers = []
        self.worker_processes = {}

        # Wait for monitor thread to finish (reduced timeout)
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)

    def _monitor_workers(self):
        """
        Monitor worker processes and adjust as needed.
        With improved shutdown handling.
        """
        print(f"Monitor thread starting. Stop event: {self.stop_event.is_set()}, Spider running: {self.spider.is_running}")
        
        check_interval = 2.0
        zero_workers_time = None
        shutdown_initiated_time = None
        
        # Continue monitoring even if spider.is_running is false
        while not self.stop_event.is_set() and (self.spider.is_running or len(self.workers) > 0):
            try:
                # Check for completed or dead workers
                alive_workers = [w for w in self.workers if w.is_alive()]

                # If all workers are gone, track when this happened
                if len(alive_workers) == 0 and len(self.workers) > 0:
                    if zero_workers_time is None:
                        zero_workers_time = time.time()
                        print(f"All workers have exited at {time.strftime('%H:%M:%S')}")
                    
                    # After 5 seconds of zero workers, initiate graceful shutdown
                    elapsed = time.time() - zero_workers_time
                    if elapsed >= 5 and shutdown_initiated_time is None:
                        print(f"All workers gone for {elapsed:.1f}s. Initiating graceful shutdown.")
                        shutdown_initiated_time = time.time()
                        
                        # Try graceful shutdown first
                        self.stop_event.set()
                        if hasattr(self.spider, 'is_running'):
                            self.spider.is_running = False
                        if hasattr(self.spider, 'stop_event') and hasattr(self.spider.stop_event, 'set'):
                            self.spider.stop_event.set()
                        
                        # Print summary here before potential forced exit
                        if hasattr(self.spider, '_print_summary') and callable(self.spider._print_summary):
                            try:
                                print("\nPrinting crawl summary before exit:")
                                self.spider._print_summary()
                                # Force flush stdout to ensure summary is displayed
                                import sys
                                sys.stdout.flush()
                            except Exception as e:
                                print(f"Error printing summary: {e}")
                        
                        # Save checkpoint if possible
                        if hasattr(self.spider, '_save_checkpoint') and callable(self.spider._save_checkpoint):
                            try:
                                self.spider._save_checkpoint(force=True)
                            except Exception as e:
                                print(f"Error saving checkpoint: {e}")
                    
                    # If graceful shutdown doesn't complete within 8 more seconds, force exit
                    if shutdown_initiated_time is not None:
                        shutdown_elapsed = time.time() - shutdown_initiated_time
                        
                        # At 8 seconds, force exit
                        if shutdown_elapsed >= 8:
                            print(f"Graceful shutdown not completing after {shutdown_elapsed:.1f}s. Forcing exit.")
                            print("Goodbye!")
                            # Flush stdout to ensure all messages are displayed
                            import sys
                            sys.stdout.flush()
                            # Give a moment for output to flush
                            time.sleep(0.5)
                            import os
                            os._exit(0)
                else:
                    # Reset zero workers time if we have workers
                    zero_workers_time = None
                    
                # Process other monitoring tasks as normal...
                
                time.sleep(check_interval)

            except Exception as e:
                print(f"Error in worker monitor thread: {e}")
                time.sleep(check_interval)
                
        print("Worker monitor thread exiting.")
    # New method to check if all workers are idle
    def are_all_workers_idle(self, idle_threshold=5):
        """
        Check if all workers appear to be idle.
        
        Args:
            idle_threshold: Number of seconds of inactivity to consider a worker idle
            
        Returns:
            bool: True if all workers appear idle or no workers exist
        """
        alive_workers = [w for w in self.workers if w.is_alive()]
        
        if not alive_workers:
            return True
            
        # If there are active workers but no URLs to process,
        # and we haven't had activity recently, consider them idle
        if (self.task_queue.empty() and 
            len(self.spider.to_visit) == 0 and 
            len(self.spider.pending_urls) == 0 and
            time.time() - self.spider.last_activity_time > idle_threshold):
            
            return True
            
        return False