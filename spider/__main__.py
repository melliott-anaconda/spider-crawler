#!/usr/bin/env python3
"""
Main entry point for the spider crawler.

This module provides the main entry point for running the crawler
from the command line.
"""
import os

import sys
import time
import traceback
from multiprocessing import freeze_support

from .cli.argument_parser import parse_args, print_config_summary
from .cli.config import load_config_from_args, save_config
from .content.filter import ContentFilter
from .core.crawler import Spider


def main():
    """Main entry point for the spider crawler with improved shutdown handling."""
    # Support for freezing with PyInstaller
    freeze_support()

    # Create a global exit timer thread to force exit if process hangs
    def force_exit_timer():
        print("Starting emergency exit timer thread")
        last_worker_count = -1
        zero_workers_start_time = None
        
        while True:
            time.sleep(1)  # Check every second
            
            # If spider exists and we can check worker count
            if 'spider' in globals() and hasattr(spider, 'worker_pool'):
                try:
                    current_worker_count = spider.worker_pool.active_workers_count()
                    
                    # Detect transition to zero workers
                    if current_worker_count == 0 and last_worker_count > 0:
                        zero_workers_start_time = time.time()
                        print(f"Emergency timer: All workers exited at {time.strftime('%H:%M:%S')}")
                    
                    # Force exit if we've been at zero workers for too long
                    if (current_worker_count == 0 and 
                        zero_workers_start_time is not None and 
                        time.time() - zero_workers_start_time > 5):  # 5 second timeout
                        
                        print(f"EMERGENCY EXIT: Force terminating after 5 seconds with no workers at {time.strftime('%H:%M:%S')}")
                        # Use os._exit to force immediate termination without cleanup
                        os._exit(0)
                    
                    last_worker_count = current_worker_count
                except:
                    # If we can't check worker count, don't force exit
                    pass

    # Start the emergency exit timer thread
    import threading
    exit_timer = threading.Thread(target=force_exit_timer, daemon=True)
    exit_timer.start()

    try:
        # Parse command-line arguments
        args = parse_args()

        # Load or create configuration
        config = load_config_from_args(args)

        # Save configuration if requested
        if args.save_config:
            save_config(config, args.save_config)
            print(f"Configuration saved to {args.save_config}")
            # If only saving config was requested, exit
            if args.config and not args.url:
                return 0
            
        if config.browser_engine == "playwright":
            try:
                import playwright
                print("- Playwright is installed and available")
            except ImportError:
                print("- WARNING: Playwright engine selected but not installed.")
                print("- To install: pip install playwright && python -m playwright install")
                print("- Falling back to Selenium engine")
                config.browser_engine = "selenium"

        # Print configuration summary
        print_config_summary(args)

        # Create content filter
        content_filter = ContentFilter(
            include_headers=config.include_headers,
            include_menus=config.include_menus,
            include_footers=config.include_footers,
            include_sidebars=config.include_sidebars,
            custom_exclude_selectors=config.exclude_selectors,
        )

        # Create and configure spider
        spider = Spider(
            start_url=config.url,
            keywords=config.keywords,
            output_file=config.output_file,
            max_pages=config.max_pages,
            max_depth=config.depth,
            path_prefix=config.path_prefix,
            allow_subdomains=config.allow_subdomains,
            content_filter=content_filter,
            allowed_extensions=config.allowed_extensions,
            is_spa=config.spa_mode,
            markdown_mode=config.markdown_mode,
            browser_engine=config.browser_engine,
            browser_type=config.browser_type
        )

        # Configure rate controller
        spider.rate_controller.max_workers = config.max_workers
        spider.rate_controller.min_workers = config.min_workers
        spider.rate_controller.target_workers = config.initial_workers
        spider.rate_controller.current_delay = config.initial_delay
        spider.rate_controller.min_delay = config.min_delay
        spider.rate_controller.max_delay = config.max_delay
        spider.rate_controller.aggressive_throttling = config.aggressive_throttling

        # Start the spider
        try:
            spider.start(
                resume=config.resume,
                headless=config.headless,
                webdriver_path=config.webdriver_path,
                max_restarts=config.max_restarts,
            )

            # Define a shorter timeout for inactivity (reduced from 300s to 60s)
            inactivity_timeout = 60

            # Wait for user input to stop (if interactive)
            if sys.stdin.isatty():
                print("\nPress Ctrl+C to stop crawling...")
                try:
                    # Wait until interrupted or completion
                    last_check_time = time.time()
                    last_urls_count = len(spider.to_visit) + len(spider.pending_urls)
                    no_progress_count = 0  # Counter for consecutive no-progress checks

                    while spider.is_running:
                        # Sleep briefly to avoid CPU hogging, but check frequently
                        time.sleep(0.5)

                        # Check for inactivity periodically
                        current_time = time.time()
                        if current_time - last_check_time > 5:  # Check every 5 seconds (reduced from 10)
                            current_urls_count = len(spider.to_visit) + len(spider.pending_urls)

                            # More aggressive detection of completion
                            if (current_urls_count == 0 and 
                                spider.task_queue.empty() and 
                                spider.result_queue.empty()):
                                
                                # Check for worker activity
                                if hasattr(spider.worker_pool, 'are_all_workers_idle') and spider.worker_pool.are_all_workers_idle():
                                    no_progress_count += 1
                                else:
                                    no_progress_count = 0
                                    
                                # If no progress for multiple consecutive checks
                                if no_progress_count >= 3:  # After 15 seconds of no activity (3 checks * 5 seconds)
                                    print(f"\nNo URLs to process and all workers idle. Stopping crawler...")
                                    spider.stop()
                                    break
                                
                            # Check for general inactivity timeout
                            if (current_time - spider.last_activity_time > inactivity_timeout and 
                                current_urls_count == 0 and 
                                spider.task_queue.empty()):
                                print(f"\nNo activity for {inactivity_timeout} seconds. Stopping crawler...")
                                spider.stop()
                                break

                            # Update for next check
                            last_check_time = current_time
                            last_urls_count = current_urls_count
                except KeyboardInterrupt:
                    print("\nReceived keyboard interrupt. Stopping...")
            else:
                # In non-interactive mode, use same completion detection logic
                last_check_time = time.time()
                last_urls_count = len(spider.to_visit) + len(spider.pending_urls)
                no_progress_count = 0

                while spider.is_running:
                    time.sleep(0.5)

                    # Check for inactivity periodically
                    current_time = time.time()
                    if current_time - last_check_time > 5:  # Check every 5 seconds
                        current_urls_count = len(spider.to_visit) + len(spider.pending_urls)

                        # More aggressive detection of completion
                        if (current_urls_count == 0 and 
                            spider.task_queue.empty() and 
                            spider.result_queue.empty()):
                            
                            # Check for worker activity
                            if hasattr(spider.worker_pool, 'are_all_workers_idle') and spider.worker_pool.are_all_workers_idle():
                                no_progress_count += 1
                            else:
                                no_progress_count = 0
                                
                            # If no progress for multiple consecutive checks
                            if no_progress_count >= 3:  # After 15 seconds of no activity
                                print(f"\nNo URLs to process and all workers idle. Stopping crawler...")
                                spider.stop()
                                break
                                
                        # Check for general inactivity timeout
                        if (current_time - spider.last_activity_time > inactivity_timeout and 
                            current_urls_count == 0 and 
                            spider.task_queue.empty()):
                            print(f"\nNo activity for {inactivity_timeout} seconds. Stopping crawler...")
                            spider.stop()
                            break

                        # Update for next check
                        last_check_time = current_time
                        last_urls_count = current_urls_count

        finally:
            # Ensure spider is stopped properly with timeout
            if spider.is_running:
                print("Ensuring spider is stopped properly...")
                spider.stop()
                
                # If spider is still running after stop() call, force exit
                if hasattr(spider, 'is_running') and spider.is_running:
                    print("Spider still marked as running. Forcing exit...")
                    
                    # Force terminate any remaining threads
                    import threading
                    for thread in threading.enumerate():
                        # Only try to terminate non-main threads
                        if thread != threading.main_thread():
                            print(f"Forcing thread to exit: {thread.name}")
                            # We can't actually terminate threads in Python, but
                            # we can set flags they might check
                            if hasattr(thread, "stop_event"):
                                thread.stop_event.set()
                    
                    # Clear any multiprocessing resources
                    if hasattr(spider, 'manager'):
                        try:
                            print("Shutting down multiprocessing manager...")
                            spider.manager.shutdown()
                        except:
                            pass
                    
                    # Clear task and result queues
                    try:
                        while not spider.task_queue.empty():
                            try:
                                spider.task_queue.get(block=False)
                            except:
                                break
                    except:
                        pass
                    
                    try:
                        while not spider.result_queue.empty():
                            try:
                                spider.result_queue.get(block=False)
                            except:
                                break
                    except:
                        pass

        return 0

    except KeyboardInterrupt:
        print("\nCrawling interrupted by user.")
        return 130  # Standard exit code for SIGINT

    except Exception as e:
        print(f"\nError: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
