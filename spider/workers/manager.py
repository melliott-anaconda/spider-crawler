#!/usr/bin/env python3
"""
Worker pool manager module that handles multiple crawler workers.

This module contains the WorkerPool class that manages the lifecycle and
coordination of multiple crawler worker processes.
"""

import threading
import time
from multiprocessing import Lock, Process, Queue, Value

from .worker import Worker, worker_process


class WorkerPool:
    """
    Manages a pool of worker processes for parallel web crawling.
    
    This class handles creating, monitoring, and adjusting the number of 
    worker processes based on crawl rate controller directives.
    """

    def __init__(self, initial_workers, task_queue, result_queue, url_cache,
                base_domain, path_prefix, keywords, content_filter,
                rate_controller, headless=True, webdriver_path=None,
                max_restarts=3, allow_subdomains=False, allowed_extensions=None,
                is_spa=False, markdown_mode=False):
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
        
        # Set up worker tracking
        self.workers = []
        self.worker_processes = {}
        self.next_worker_id = 0
        
        # Create shared resources for worker coordination
        self.retry_queue = Queue()  # Queue for URLs that need to be retried
        self.active_workers = Value('i', 0)
        self.active_workers_lock = Lock()
        
        # Shared values for rate control
        self.current_delay = Value('d', self.rate_controller.current_delay)
        self.target_workers = Value('i', self.rate_controller.target_workers)

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
        
        # Create worker instance
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
            target_workers=self.target_workers
        )
        
        # Start worker process
        process = worker.start()
        
        # Track the worker
        self.workers.append(worker)
        self.worker_processes[worker_id] = worker
        
        print(f"Started worker {worker_id} with delay={self.current_delay.value:.2f}s")
        return worker_id

    def stop(self, timeout=5):
        """
        Stop all worker processes.
        
        Args:
            timeout: Timeout for joining processes
        """
        self.is_running = False
        self.stop_event.set()
        
        # Send exit signal to all workers
        for _ in range(len(self.workers)):
            self.task_queue.put(None)
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.stop(timeout=timeout)
        
        # Clear worker lists
        self.workers = []
        self.worker_processes = {}
        
        # Wait for monitor thread to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=timeout)

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
            print(f"Need to terminate {excess} workers to reduce from {current_count} to {target}")
            
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
            print(f"Need to start {to_start} new workers to increase from {current_count} to {target}")
            
            for _ in range(to_start):
                self.start_new_worker()

    def _monitor_workers(self):
        """
        Monitor worker processes and adjust as needed.
        
        This method runs in a background thread to periodically check worker
        status and restart any that have died unexpectedly.
        """
        while not self.stop_event.is_set() and self.is_running:
            try:
                # Check for completed or dead workers
                alive_workers = [w for w in self.workers if w.is_alive()]
                
                # If some workers died unexpectedly, remove them from our list
                if len(alive_workers) != len(self.workers):
                    print(f"Some workers died unexpectedly. Alive: {len(alive_workers)}/{len(self.workers)}")
                    self.workers = alive_workers
                
                # Check if we need to adjust worker count based on rate controller
                target = self.target_workers.value
                current_count = len(alive_workers)
                
                if current_count != target:
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

    def get_worker_status(self):
        """
        Get current status of worker processes.
        
        Returns:
            dict: Status information about workers
        """
        alive_count = len([w for w in self.workers if w.is_alive()])
        return {
            'target_workers': self.target_workers.value,
            'active_workers': self.active_workers.value,
            'alive_workers': alive_count,
            'total_workers_created': self.next_worker_id,
            'current_delay': self.current_delay.value
        }
