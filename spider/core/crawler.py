#!/usr/bin/env python3
"""
Main crawler module.

This module contains the Spider class that orchestrates the web crawling process,
coordinating workers, managing URLs, and processing results.
"""

import csv
import os
import signal
import threading
import time
from multiprocessing import Lock, Manager, Queue, Value
from queue import Empty
from urllib.parse import urlparse

from ..content.filter import ContentFilter
from ..workers.manager import WorkerPool
from .checkpoint import CheckpointManager
from .rate_controller import CrawlRateController


class Spider:
    """
    Main crawler class that coordinates the web crawling process.

    This class manages the overall crawling process, including:
    - URL queue management
    - Worker process coordination
    - Rate control
    - Result processing
    - Checkpoint saving/loading
    """

    def __init__(
        self,
        start_url,
        keywords=None,
        output_file=None,
        max_pages=None,
        max_depth=None,
        path_prefix=None,
        allow_subdomains=False,
        content_filter=None,
        allowed_extensions=None,
        is_spa=False,
        markdown_mode=False,
        browser_engine="selenium", 
        browser_type="chromium",
    ):
        """
        Initialize the Spider.

        Args:
            start_url: URL to start crawling from
            keywords: List of keywords to search for (optional in markdown mode)
            max_pages: Maximum number of pages to crawl (None for unlimited)
            max_depth: Maximum crawl depth from seed URL (None for unlimited)
            path_prefix: Path prefix to restrict crawling to
            allow_subdomains: Whether to allow crawling across subdomains
            content_filter: ContentFilter instance for filtering page content
            output_file: Path to output CSV file (required for keyword mode)
            allowed_extensions: Set of additional file extensions to allow
            is_spa: Whether to use SPA-specific processing
            markdown_mode: Whether to save content as markdown
        """
        self.start_url = start_url
        self.keywords = keywords or []
        self.output_file = output_file
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.path_prefix = path_prefix
        self.allow_subdomains = allow_subdomains
        self.allowed_extensions = allowed_extensions
        self.is_spa = is_spa
        self.markdown_mode = markdown_mode
        self.browser_engine = browser_engine
        self.browser_type = browser_type

        # Extract domain from start URL
        parsed_url = urlparse(start_url)
        self.base_domain = parsed_url.netloc

        # If no path_prefix specified, use the path from start_url if it's not just "/"
        if self.path_prefix is None and parsed_url.path and parsed_url.path != "/":
            self.path_prefix = parsed_url.path

        # Create a default content filter if none provided
        self.content_filter = content_filter or ContentFilter()

        # Create a multiprocessing manager
        self.manager = Manager()

        # Set up URL tracking
        self.visited = self.manager.list()
        self.to_visit = self.manager.list([(self.start_url, 0)])  # (url, depth)
        self.pending_urls = self.manager.list()
        self.retry_queue = (
            self.manager.Queue()
        )  # Queue for URLs that need to be retried
        self.url_cache = self.manager.dict()  # Deduplication cache

        # Add start URL to cache
        self.url_cache[self.start_url] = 0  # Store depth with URL (0 for seed URL)

        # Add deduplication tracking for results
        self.seen_results = self.manager.dict()

        # Create shared counters with locks
        self.pages_visited = Value("i", 0)
        self.pages_visited_lock = Lock()

        # For markdown mode, track statistics by category
        self.markdown_stats = self.manager.dict()

        # Track retry counts for URLs
        self.retry_counts = self.manager.dict()
        self.max_retries = 3

        # Create rate controller
        self.rate_controller = CrawlRateController()

        # Create checkpoint manager
        self.checkpoint_manager = CheckpointManager(
            checkpoint_file=(
                f"{self.output_file}.checkpoint.json"
                if self.output_file
                else "spider_checkpoint.json"
            )
        )

        # Set up shared values for rate control
        self.current_delay = Value("d", self.rate_controller.current_delay)
        self.target_workers = Value("i", self.rate_controller.target_workers)

        # Create job queues
        self.task_queue = Queue()
        self.result_queue = Queue()

        # Worker pool will be created during start()
        self.worker_pool = None

        # Control flags
        self.is_running = False
        self.stop_event = threading.Event()

        # Thread for processing results
        self.result_thread = None

        # Thread for retry handling
        self.retry_thread = None

        # Thread for checkpointing
        self.checkpoint_thread = None

        # Activity tracking
        self.last_activity_time = time.time()
        self.no_progress_count = 0

        # Set up signal handlers
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(sig, frame):
            print("\nReceived interrupt signal. Shutting down gracefully...")
            self.stop()

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def start(
        self,
        resume=False,
        headless=True,
        webdriver_path=None,
        max_restarts=3,
        use_undetected=False,
    ):
        """
        Start the crawling process.

        Args:
            resume: Whether to resume from checkpoint
            headless: Whether to run browsers in headless mode
            webdriver_path: Path to the WebDriver executable
            max_restarts: Maximum number of WebDriver restarts

        Returns:
            bool: True if started successfully, False otherwise
        """
        # Don't start if already running
        if self.is_running:
            print("Spider is already running")
            return False

        # Initialize output file if needed
        if not self.markdown_mode and not os.path.exists(self.output_file):
            with open(self.output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter="|")
                writer.writerow(["URL", "Keyword Found", "Context"])

        # Resume from checkpoint if requested
        if resume:
            self.resume_from_checkpoint()

        # If we have no URLs to process, add a warning
        if len(self.to_visit) == 0 and len(self.pending_urls) == 0:
            print(f"Warning: No URLs to process. Starting URL is: {self.start_url}")
            # Ensure the start URL is in the to_visit list
            if (
                self.start_url not in self.to_visit
                and self.start_url not in self.visited
            ):
                print(f"Adding start URL {self.start_url} to queue")
                self.to_visit.append(self.start_url)

        # Initialize task queue with URLs from to_visit
        self._fill_task_queue()

        # Create the worker pool
        self.worker_pool = WorkerPool(
            spider=self,
            initial_workers=self.target_workers.value,
            task_queue=self.task_queue,
            result_queue=self.result_queue,
            url_cache=self.url_cache,
            base_domain=self.base_domain,
            path_prefix=self.path_prefix,
            keywords=self.keywords,
            content_filter=self.content_filter,
            rate_controller=self.rate_controller,
            headless=headless,
            webdriver_path=webdriver_path,
            max_restarts=max_restarts,
            allow_subdomains=self.allow_subdomains,
            allowed_extensions=self.allowed_extensions,
            is_spa=self.is_spa,
            markdown_mode=self.markdown_mode,
            use_undetected=use_undetected,
            browser_engine=self.browser_engine,
            browser_type=self.browser_type
        )

        # Start the worker pool
        self.worker_pool.start()

        # Start result processing thread
        self.result_thread = threading.Thread(target=self._process_results)
        self.result_thread.daemon = True
        self.result_thread.start()

        # Start retry handling thread
        self.retry_thread = threading.Thread(target=self._process_retry_queue)
        self.retry_thread.daemon = True
        self.retry_thread.start()

        # Start checkpoint thread
        self.checkpoint_thread = threading.Thread(target=self.checkpoint_loop)
        self.checkpoint_thread.daemon = True
        self.checkpoint_thread.start()

        # Set running flag
        self.is_running = True
        self.stop_event.clear()
        self.last_activity_time = time.time()

        print(f"Spider started with {self.target_workers.value} workers")

        # Schedule a task to check progress after initial startup
        startup_check_thread = threading.Thread(target=self._check_startup_progress)
        startup_check_thread.daemon = True
        startup_check_thread.start()

        return True

    def resume_from_checkpoint(self):
        """
        Resume crawling from a checkpoint.

        Returns:
            bool: True if successfully resumed from checkpoint, False otherwise
        """
        checkpoint_data = self.checkpoint_manager.load_checkpoint()

        if not checkpoint_data:
            print("No checkpoint found, starting fresh")
            return False

        try:
            # Restore visited URLs
            self.visited[:] = checkpoint_data.get("visited", [])

            # Restore URLs to visit (including pending ones for safety)
            pending_from_checkpoint = checkpoint_data.get("pending_urls", [])
            
            # Handle both old-style (url string only) and new-style (url, depth) formats
            to_visit_list = []
            for item in checkpoint_data.get("to_visit", []):
                if isinstance(item, tuple) and len(item) == 2:
                    # This is already in the new (url, depth) format
                    to_visit_list.append(item)
                else:
                    # This is in the old format (url string only), add depth 0
                    to_visit_list.append((item, 0))
                    
            # Do the same for pending URLs
            pending_list = []
            for item in pending_from_checkpoint:
                if isinstance(item, tuple) and len(item) == 2:
                    pending_list.append(item)
                else:
                    pending_list.append((item, 0))
                    
            # Update the to_visit list
            self.to_visit[:] = pending_list + to_visit_list

            # Start with empty pending list
            self.pending_urls[:] = []

            # Restore visited pages counter
            with self.pages_visited_lock:
                self.pages_visited.value = checkpoint_data.get("pages_visited", 0)

            # Restore URL cache - ensure it uses strings as keys, not tuples or lists
            self.url_cache.clear()  # Clear existing cache
            
            # Add visited URLs to cache (with depth 0 if not specified)
            for url in self.visited:
                self.url_cache[url] = 0
                
            # Add URLs to visit to cache with their depth
            for url_info in self.to_visit:
                if isinstance(url_info, tuple) and len(url_info) == 2:
                    url, depth = url_info
                    self.url_cache[url] = depth
                else:
                    self.url_cache[url_info] = 0

            # Restore rate controller state if available
            if "rate_controller" in checkpoint_data:
                with self.rate_controller.lock:
                    self.rate_controller.from_checkpoint(
                        checkpoint_data.get("rate_controller", {})
                    )
                    # Update the shared values
                    current_settings = self.rate_controller.get_current_settings()
                    self.current_delay.value = current_settings["current_delay"]
                    self.target_workers.value = current_settings["target_workers"]

            # Restore retry counts
            if "retry_counts" in checkpoint_data:
                self.retry_counts.update(checkpoint_data.get("retry_counts", {}))

            # Restore markdown stats if available
            if "markdown_stats" in checkpoint_data and self.markdown_mode:
                self.markdown_stats.update(checkpoint_data.get("markdown_stats", {}))

            # Restore seen results to avoid duplicates
            if not self.markdown_mode and os.path.exists(self.output_file):
                with open(self.output_file, "r", newline="", encoding="utf-8") as f:
                    reader = csv.reader(f, delimiter="|")
                    next(reader)  # Skip header
                    for row in reader:
                        if len(row) >= 3:
                            key = (row[0], row[1], row[2])
                            self.seen_results[str(key)] = True

            print(
                f"Resumed from checkpoint: {len(self.visited)} visited URLs, {len(self.to_visit)} URLs to visit"
            )
            print(
                f"Current settings: {self.target_workers.value} workers, {self.current_delay.value:.2f}s delay"
            )

            return True

        except Exception as e:
            print(f"Error resuming from checkpoint: {e}")
            return False


    def _fill_task_queue(self):
        """
        Fill the task queue with URLs from to_visit.

        This method adds URLs from the to_visit list to the task queue
        to ensure workers have tasks to process.
        """
        # Determine how many URLs to add
        current_target = self.target_workers.value
        urls_to_add = max(1, current_target * 2 - len(self.pending_urls))

        added = 0
        for _ in range(min(urls_to_add, len(self.to_visit))):
            if len(self.to_visit) > 0:
                url_info = self.to_visit.pop(0)
                
                # Handle both tuple format (url, depth) and string format for backward compatibility
                if isinstance(url_info, tuple) and len(url_info) == 2:
                    url, depth = url_info
                else:
                    url = url_info
                    depth = 0  # Default to depth 0 for old format
                    
                # Skip if already visited
                if url in self.visited:
                    continue

                # Add to pending list
                self.pending_urls.append((url, depth))

                # Add to task queue - workers need both URL and depth
                self.task_queue.put((url, depth))
                added += 1

        if added > 0:
            print(f"Added {added} new URLs to the task queue")

        # If we have new links but didn't add any (they were all visited already)
        if added == 0 and len(self.to_visit) > 0:
            # Try again with the next URL
            self._fill_task_queue()

        # Update last activity time if we added URLs
        if added > 0:
            self.last_activity_time = time.time()
            self.no_progress_count = 0
        elif len(self.to_visit) == 0 and len(self.pending_urls) == 0:
            # If no URLs to process, increment no progress counter
            self.no_progress_count += 1

            # If we have worker processes but no URLs to distribute,
            # check if we've reached the end of crawling
            if self.pages_visited.value > 0 and self.worker_pool:
                # We've already crawled some pages but now have no more URLs
                print("No more URLs to distribute. Checking if crawling is complete...")

                # Wait a bit to make sure all results are processed
                time.sleep(2)

                # If still no URLs and no pending URLs, signal completion
                if len(self.to_visit) == 0 and len(self.pending_urls) == 0:
                    print(
                        "No URLs in queue and none pending. Crawling may be complete."
                    )
                    # We don't call stop() here - monitoring threads will handle shutdown
                    
    def _check_startup_progress(self):
        """
        Check if the crawler is making progress after startup.

        This method runs in a separate thread and checks if URLs are being processed
        after a short delay to allow workers to initialize.
        """
        # Wait for workers to initialize (30 seconds)
        time.sleep(30)

        # If we're still running and have made no progress
        if self.is_running and self.pages_visited.value == 0:
            # Check if we have pending URLs that haven't been processed
            if len(self.pending_urls) > 0:
                print(
                    f"Warning: {len(self.pending_urls)} URLs are pending but none have been processed yet."
                )
                print("This may indicate an issue with worker processes.")

                # Optional: Could trigger diagnostics or retry logic here

            # If we have neither visited any pages nor have any pending URLs
            if len(self.pending_urls) == 0 and len(self.to_visit) == 0:
                print(
                    "Warning: No URLs are being processed. Check if the start URL is accessible."
                )

                # Could trigger diagnostics or retry the start URL here


    def _handle_success_result(self, result):
        """
        Handle a successful crawl result.

        Args:
            result: Result dictionary from a worker
        """
        url = result["url"]
        current_depth = result.get("depth", 0)  # Get current depth, default to 0

        # Mark as visited
        if url in self.pending_urls:
            self.pending_urls.remove(url)
        self.visited.append(url)

        if self.markdown_mode and "markdown_saved" in result:
            # Handle markdown mode result
            file_path = result["markdown_saved"]
            category = result.get("category", "misc")

            # Update category statistics
            if category in self.markdown_stats:
                self.markdown_stats[category] += 1
            else:
                self.markdown_stats[category] = 1

            print(f"Saved markdown for {url} as {file_path} (category: {category})")
        else:
            # Process keyword results with deduplication
            keyword_results = result.get("keyword_results", [])
            unique_results = []

            if keyword_results:
                for row in keyword_results:
                    key = str((row[0], row[1], row[2]))
                    if key not in self.seen_results:
                        self.seen_results[key] = True
                        unique_results.append(row)

                if unique_results:
                    print(
                        f"Found {len(unique_results)} unique keyword matches on {url}"
                    )

                    # Write results to CSV
                    with open(self.output_file, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter="|")
                        writer.writerows(unique_results)
                else:
                    print(
                        f"All {len(keyword_results)} results from {url} were duplicates"
                    )

        # Process new links if we haven't reached max depth
        new_links = result.get("links", [])
        links_added = 0
        next_depth = current_depth + 1
        
        # Only add new links if we're under the max depth (or if max_depth is None)
        if self.max_depth is None or next_depth <= self.max_depth:
            for link in new_links:
                if link not in self.url_cache:
                    self.to_visit.append((link, next_depth))
                    self.url_cache[link] = next_depth
                    links_added += 1

            if links_added > 0:
                print(f"Added {links_added} new URLs to the queue from {url} (depth: {current_depth}, next depth: {next_depth})")
        else:
            print(f"Max depth ({self.max_depth}) reached for {url}, not adding {len(new_links)} discovered links")

        # Increment pages visited counter
        with self.pages_visited_lock:
            self.pages_visited.value += 1
            current_pages = self.pages_visited.value

        # Report progress
        if self.markdown_mode:
            category_counts = ", ".join(
                f"{k}: {v}" for k, v in self.markdown_stats.items()
            )
            print(
                f"Pages visited: {current_pages}"
                + (f" (max: {self.max_pages})" if self.max_pages else "")
                + (f" | Categories: {category_counts}" if category_counts else "")
            )
        else:
            print(
                f"Pages visited: {current_pages}"
                + (f" (max: {self.max_pages})" if self.max_pages else "")
                + (f" | Max depth: {self.max_depth}" if self.max_depth else "")
                + f" | Queue: {len(self.to_visit)} | Pending: {len(self.pending_urls)}"
            )

        # Update activity timestamp
        self.last_activity_time = time.time()
        self.no_progress_count = 0

    def _handle_http_error_result(self, result):
        """
        Handle an HTTP error result.

        Args:
            result: Result dictionary from a worker
        """
        url = result["url"]
        handling = result.get("handling", {})
        http_status = result.get("http_status", 0)

        print(
            f"HTTP error {http_status} for {url}: {handling.get('reason', 'Unknown error')}"
        )

        # Remove from pending list
        if url in self.pending_urls:
            self.pending_urls.remove(url)

        # Only mark as visited if we're not retrying
        if handling.get("action") not in ["retry", "retry_once", "throttle_and_retry"]:
            if url not in self.visited:
                self.visited.append(url)

        # Handle rate limiting specifically
        if handling.get("action") == "throttle_and_retry":
            print(f"RATE LIMITING DETECTED! Action: {handling.get('action')}")

            with self.rate_controller.lock:
                # Force an immediate adjustment
                changed, new_workers, new_delay, reason = (
                    self.rate_controller.adjust_rate_if_needed(force=True)
                )

                if changed:
                    print(f"Immediate rate adjustment due to rate limiting: {reason}")
                    # Update shared values
                    self.current_delay.value = new_delay
                    self.target_workers.value = new_workers
                    print(
                        f"SHARED VALUES UPDATED: target_workers={self.target_workers.value}, current_delay={self.current_delay.value:.2f}s"
                    )

        # Update activity timestamp
        self.last_activity_time = time.time()

    def _handle_skipped_result(self, result):
        """
        Handle a skipped result.

        Args:
            result: Result dictionary from a worker
        """
        url = result["url"]
        reason = result.get("reason", "Unknown reason")

        print(f"Skipped {url}: {reason}")

        # Remove from pending list
        if url in self.pending_urls:
            self.pending_urls.remove(url)

        # Mark as visited to avoid retrying
        if url not in self.visited:
            self.visited.append(url)

        # Update activity timestamp
        self.last_activity_time = time.time()

    def _handle_error_result(self, result):
        """
        Handle an error result.

        Args:
            result: Result dictionary from a worker
        """
        url = result["url"]
        error = result.get("error", "Unknown error")

        print(f"Error processing {url}: {error}")

        # Remove from pending list
        if url in self.pending_urls:
            self.pending_urls.remove(url)

        # We don't mark as visited since it might be retried

        # Update activity timestamp
        self.last_activity_time = time.time()

    def _process_retry_queue(self):
        """
        Process URLs in the retry queue.

        This method runs in a separate thread and adds URLs from the retry queue
        back to the to_visit queue after their retry delay has elapsed.
        """
        retry_status = {}  # Track scheduled retries

        while not self.stop_event.is_set():
            try:
                # Check retry queue in a non-blocking way
                try:
                    retry_item = self.retry_queue.get(timeout=1)
                except Empty:
                    # Check any scheduled retries that might be due
                    self._check_scheduled_retries(retry_status)
                    continue

                url = retry_item["url"]
                retry_after = retry_item.get("retry_after", 0)
                action = retry_item.get("action", "retry")

                # Check if URL has been retried too many times
                url_str = str(url)
                current_retries = self.retry_counts.get(url_str, 0)

                if current_retries >= self.max_retries:
                    print(f"Dropping {url} after {current_retries} retries")
                    # Mark as visited to avoid further attempts
                    if url not in self.visited:
                        self.visited.append(url)
                    continue

                # Increment retry counter
                self.retry_counts[url_str] = current_retries + 1

                # If action is 'retry_once' and already retried, skip it
                if action == "retry_once" and current_retries > 0:
                    print(f"Dropping {url} after single retry attempt")
                    if url not in self.visited:
                        self.visited.append(url)
                    continue

                # Schedule the retry
                delay_time = retry_after * (1.5**current_retries)  # Exponential backoff

                if delay_time > 0:
                    print(
                        f"Scheduling retry for {url} in {delay_time:.1f}s (attempt {current_retries+1}/{self.max_retries})"
                    )

                    # Record the scheduled retry
                    retry_time = time.time() + delay_time
                    retry_id = f"{url}_{time.time()}"

                    retry_status[url] = {
                        "scheduled": True,
                        "retry_time": retry_time,
                        "attempt": current_retries + 1,
                        "retry_id": retry_id,
                    }

                    # Create a timer thread for this retry
                    retry_thread = threading.Timer(
                        delay_time,
                        self._requeue_url,
                        args=[url, retry_id, retry_status],
                    )
                    retry_thread.daemon = True
                    retry_thread.start()
                else:
                    # Immediate retry - make sure it's not already in process
                    if url not in self.visited and url not in self.pending_urls:
                        self.to_visit.append(url)

                # Update activity timestamp
                self.last_activity_time = time.time()

            except Exception as e:
                print(f"Error in retry processing: {e}")

    def _check_scheduled_retries(self, retry_status):
        """
        Check for scheduled retries that are due and execute them.

        Args:
            retry_status: Dictionary of scheduled retries
        """
        # Nothing to do if no retries are scheduled
        if not retry_status:
            return

        now = time.time()
        due_retries = []

        # Find retries that are due
        for url, info in retry_status.items():
            if (
                info.get("scheduled", False)
                and info.get("retry_time", float("inf")) <= now
            ):
                due_retries.append((url, info))

        # Process due retries
        for url, info in due_retries:
            self._requeue_url(url, info.get("retry_id"), retry_status)

    def _requeue_url(self, url, retry_id, retry_status):
        """
        Requeue a URL after its retry delay.

        Args:
            url: URL to requeue
            retry_id: ID for this specific retry attempt
            retry_status: Dictionary of retry status information
        """
        try:
            # Check if this URL's retry was cancelled or superseded
            current_status = retry_status.get(url, {})
            if (
                current_status.get("scheduled", False)
                and current_status.get("retry_id") == retry_id
            ):
                # Check if we should still requeue this URL
                url_in_visited = url in self.visited
                url_in_pending = url in self.pending_urls
                url_in_to_visit = url in self.to_visit

                if not url_in_visited and not url_in_pending and not url_in_to_visit:
                    print(
                        f"Requeuing {url} (attempt {current_status.get('attempt', '?')})"
                    )
                    self.to_visit.append(url)

                    # Update activity timestamp
                    self.last_activity_time = time.time()
                else:
                    print(f"Not requeuing {url} - already visited/pending/queued")

                # Mark as no longer scheduled
                current_status["scheduled"] = False

        except Exception as e:
            print(f"Error requeuing URL {url}: {e}")
            # Still try to requeue in case of error
            if (
                url not in self.visited
                and url not in self.pending_urls
                and url not in self.to_visit
            ):
                self.to_visit.append(url)

                # Update activity timestamp
                self.last_activity_time = time.time()

    def _save_checkpoint(self, force=False):
        """
        Save crawler state to checkpoint file.

        Args:
            force: Whether to force a save regardless of interval

        Returns:
            bool: True if checkpoint was saved, False otherwise
        """
        try:
            # Convert to_visit and pending_urls to serializable format if needed
            to_visit_serializable = []
            for item in self.to_visit:
                if isinstance(item, tuple) and len(item) == 2:
                    # Already in (url, depth) format
                    to_visit_serializable.append(item)
                else:
                    # Convert to (url, 0) format
                    to_visit_serializable.append((item, 0))
                    
            pending_urls_serializable = []
            for item in self.pending_urls:
                if isinstance(item, tuple) and len(item) == 2:
                    # Already in (url, depth) format
                    pending_urls_serializable.append(item)
                else:
                    # Convert to (url, 0) format
                    pending_urls_serializable.append((item, 0))

            # Prepare checkpoint data
            checkpoint_data = {
                "visited": list(self.visited),
                "to_visit": to_visit_serializable,
                "pending_urls": pending_urls_serializable,
                "pages_visited": self.pages_visited.value,
                "retry_counts": dict(self.retry_counts),
                "last_activity_time": self.last_activity_time,
                "no_progress_count": self.no_progress_count,
            }

            # Add rate controller state
            with self.rate_controller.lock:
                checkpoint_data["rate_controller"] = (
                    self.rate_controller.to_checkpoint()
                )

            # Add markdown stats if in markdown mode
            if self.markdown_mode:
                checkpoint_data["markdown_stats"] = {
                    k: v for k, v in self.markdown_stats.items()
                }

            # Save checkpoint
            saved = self.checkpoint_manager.save_checkpoint(
                checkpoint_data, force=force
            )

            if saved:
                print(
                    f"Checkpoint saved: {self.pages_visited.value} pages visited, {len(self.to_visit)} URLs to visit"
                )

            return saved

        except Exception as e:
            print(f"Error saving checkpoint: {e}")
            return False
        
    def _print_summary(self):
        """Print a summary of the crawl results."""
        with self.rate_controller.lock:
            stats = self.rate_controller.get_statistics()

        print("\nCrawl summary:")
        print(f"- Total pages visited: {self.pages_visited.value}")
        print(f"- Total URLs in queue: {len(self.to_visit)}")
        print(f"- Success rate: {stats['success_rate']*100:.1f}%")
        print(f"- Rate limited requests: {stats['rate_limited_requests']}")
        print(f"- Error rate: {stats['error_rate']*100:.1f}%")

        if self.markdown_mode:
            print("\nMarkdown files by category:")
            for category, count in sorted(
                self.markdown_stats.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"- {category.capitalize()}: {count} pages")

    def _process_results(self):
        """
        Process results from worker processes with improved shutdown detection.
        """
        last_progress_check = time.time()
        last_urls_count = len(self.to_visit) + len(self.pending_urls)
        worker_status = {}  # Track worker status
        
        while not self.stop_event.is_set() or not self.result_queue.empty():
            try:
                # Get a result (with timeout to allow checking stop_event)
                try:
                    result = self.result_queue.get(timeout=1)
                except Empty:
                    # Check if crawling is complete with more aggressive timing
                    if (len(self.to_visit) == 0 and 
                        len(self.pending_urls) == 0 and 
                        self.task_queue.empty() and 
                        self.result_queue.empty()):
                        
                        current_time = time.time()
                        # Reduced wait time from 10s to 3s
                        if current_time - self.last_activity_time > 3:
                            print("Crawling appears complete - checking worker status...")
                            
                            # Check if all workers are idle
                            active_count = 0
                            idle_count = 0
                            
                            for worker_id, status in worker_status.items():
                                if status.get("active", False):
                                    active_count += 1
                                    if status.get("idle_time", 0) > 5:  # Worker idle for 5+ seconds
                                        idle_count += 1
                            
                            # If all active workers are idle, or no active workers
                            if active_count == 0 or active_count == idle_count:
                                print("All workers idle or finished. Shutting down...")
                                self.stop_event.set()
                                break
                    
                    continue
                
                # Special result types for worker status and shutdown coordination
                if "status" in result:
                    if result["status"] == "worker_status":
                        # Update worker status tracking
                        worker_id = result.get("worker_id")
                        worker_status[worker_id] = {
                            "active": True,
                            "idle_time": result.get("idle_time", 0),
                            "last_update": time.time()
                        }
                        continue
                        
                    elif result["status"] == "worker_shutdown":
                        # Worker is shutting down
                        worker_id = result.get("worker_id")
                        print(f"Worker {worker_id} is shutting down: {result.get('reason')}")
                        if worker_id in worker_status:
                            worker_status[worker_id]["active"] = False
                        continue
                        
                    elif result["status"] == "worker_shutdown_complete":
                        # Worker has completed shutdown
                        worker_id = result.get("worker_id")
                        if worker_id in worker_status:
                            del worker_status[worker_id]
                        continue
                
                # Register response with rate controller for adaptive control
                with self.rate_controller.lock:
                    self.rate_controller.register_response(result)

                # Process results based on status
                if "status" in result and result["status"] == "success":
                    self._handle_success_result(result)
                elif "status" in result and result["status"] == "http_error":
                    self._handle_http_error_result(result)
                elif "status" in result and result["status"] == "skipped":
                    self._handle_skipped_result(result)
                elif "status" in result and result["status"] == "error":
                    self._handle_error_result(result)

                # Update activity timestamp on any result processing
                self.last_activity_time = time.time()

                # Check if we've reached the maximum pages
                if (self.max_pages is not None and 
                    self.pages_visited.value >= self.max_pages):
                    print(f"Reached maximum pages limit ({self.max_pages})")
                    self.stop_event.set()
                    break

                # Fill task queue if needed
                self._fill_task_queue()

            except Exception as e:
                print(f"Error processing result: {e}")
    
    def checkpoint_loop(self):
        """
        Periodically save crawler state to checkpoint file.
        Improved shutdown detection and coordination.
        """
        # Create a local flag to track shutdown initiation
        shutdown_initiated = False
        
        while not self.stop_event.is_set():
            try:
                # Sleep for a short while to be more responsive to shutdown events
                for _ in range(6):  # Check every 0.5 seconds (6 * 0.5s = 3s)
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.5)
                
                if self.stop_event.is_set():
                    break

                # Check if we should save a checkpoint
                if self.checkpoint_manager.should_save_checkpoint(
                    self.pages_visited.value
                ):
                    self._save_checkpoint()

                # CRITICAL: Check if all workers are gone but we're still running
                if self.worker_pool and self.worker_pool.active_workers_count() == 0:
                    # If we have no active workers but the process is still running,
                    # we may be stuck. Check for remaining URLs.
                    if (len(self.to_visit) == 0 and 
                        len(self.pending_urls) == 0 and 
                        self.task_queue.empty() and 
                        self.result_queue.empty()):
                        
                        if not shutdown_initiated:
                            print("All workers have exited and no URLs remain. Initiating shutdown...")
                            shutdown_initiated = True
                        else:
                            # If shutdown was already initiated but we're still here,
                            # we need to force the issue
                            print("Forced shutdown required - all workers gone but process still running")
                            self.stop_event.set()
                            self.is_running = False
                            return  # Exit the checkpoint loop immediately

                # Regular completion check
                if (len(self.to_visit) == 0 and 
                    len(self.pending_urls) == 0 and 
                    self.task_queue.empty() and 
                    self.result_queue.empty() and
                    time.time() - self.last_activity_time > 5):
                    
                    # If shutdown was already initiated, force exit now
                    if shutdown_initiated:
                        print("Forced shutdown - process still running after shutdown initiated")
                        self.stop_event.set()
                        self.is_running = False
                        return
                    
                    print("No more URLs to process. Saving final checkpoint...")
                    self._save_checkpoint(force=True)

                    print("Crawling complete. Initiating shutdown...")
                    shutdown_initiated = True

                    # Mark as controlled shutdown
                    self.controlled_shutdown = True

                    # Send exit signals to all active workers
                    if self.worker_pool:
                        active_count = self.worker_pool.active_workers_count()
                        print(f"Sending exit signals to {active_count} active workers")
                        for _ in range(active_count * 2):  # Send extra signals to ensure delivery
                            try:
                                self.task_queue.put(None)
                            except:
                                break

                    # Set stop event
                    self.stop_event.set()
                    self.is_running = False
                    break

            except Exception as e:
                print(f"Error in checkpoint loop: {e}")
    
    def stop(self):
        """
        Stop the crawling process gracefully with improved signal handling.
        """
        if not self.is_running:
            print("Spider is not running")
            return False

        # Set stop event
        self.stop_event.set()
        self.is_running = False

        print("Stopping spider, please wait...")

        # Save final checkpoint
        self._save_checkpoint(force=True)

        # Send exit signal to each worker with a cleaner approach
        if self.worker_pool:
            num_workers = self.worker_pool.active_workers_count() 
            if num_workers > 0:
                print(f"Sending exit signals to {num_workers} active workers")
                
                # Put just enough None values in the queue
                for _ in range(num_workers):
                    try:
                        self.task_queue.put(None, block=False)
                    except:
                        break
        
        # Add a timeout for graceful shutdown
        shutdown_start = time.time()
        max_shutdown_wait = 10  # seconds
        
        # Wait briefly for workers to start shutting down
        time.sleep(1)
        
        # Stop worker pool with a shorter timeout
        if self.worker_pool:
            self.worker_pool.stop(timeout=2)
        
        # Wait for threads with timeout
        for thread in [self.result_thread, self.retry_thread, self.checkpoint_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2)
        
        # Force terminate if shutdown is taking too long
        if time.time() - shutdown_start > max_shutdown_wait:
            print("Shutdown taking too long. Forcing termination.")
            # Force process to exit
            import os
            os._exit(0)

        print("Spider stopped")

        # Print summary
        self._print_summary()

        return True