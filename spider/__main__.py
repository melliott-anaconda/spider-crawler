#!/usr/bin/env python3
"""
Main entry point for the spider crawler.

This module provides the main entry point for running the crawler
from the command line.
"""

import sys
import time
import traceback
from multiprocessing import freeze_support

from .cli.argument_parser import parse_args, print_config_summary
from .cli.config import load_config_from_args, save_config
from .content.filter import ContentFilter
from .core.crawler import Spider
from .browser.driver import ensure_no_chromedriver_zombies


def main():
    """Main entry point for the spider crawler."""
    # Support for freezing with PyInstaller
    freeze_support()
    
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
        
        # Print configuration summary
        print_config_summary(args)
        
        # Create content filter
        content_filter = ContentFilter(
            include_headers=config.include_headers,
            include_menus=config.include_menus,
            include_footers=config.include_footers,
            include_sidebars=config.include_sidebars,
            custom_exclude_selectors=config.exclude_selectors
        )
        
        # Create and configure spider
        spider = Spider(
            start_url=config.url,
            keywords=config.keywords,
            output_file=config.output_file,
            max_pages=config.max_pages,
            path_prefix=config.path_prefix,
            allow_subdomains=config.allow_subdomains,
            content_filter=content_filter,
            allowed_extensions=config.allowed_extensions,
            is_spa=config.spa_mode,
            markdown_mode=config.markdown_mode
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
                max_restarts=config.max_restarts
            )
            
            # Define a timeout for inactivity (5 minutes)
            inactivity_timeout = 300
            
            # Wait for user input to stop (if interactive)
            if sys.stdin.isatty():
                print("\nPress Ctrl+C to stop crawling...")
                try:
                    # Wait until interrupted or completion
                    last_check_time = time.time()
                    last_urls_count = len(spider.to_visit) + len(spider.pending_urls)
                    
                    while spider.is_running:
                        # Sleep briefly to avoid CPU hogging
                        time.sleep(0.1)
                        
                        # Check for inactivity periodically
                        current_time = time.time()
                        if current_time - last_check_time > 10:  # Check every 10 seconds
                            current_urls_count = len(spider.to_visit) + len(spider.pending_urls)
                            
                            # Check if no progress and no URLs to process
                            if (current_urls_count == last_urls_count == 0 and 
                                spider.task_queue.empty() and spider.result_queue.empty()):
                                # If no activity for a while, stop
                                if current_time - spider.last_activity_time > inactivity_timeout:
                                    print(f"\nNo URLs processed for {inactivity_timeout} seconds. Stopping crawler...")
                                    spider.stop()
                                    break
                            
                            # Update for next check
                            last_check_time = current_time
                            last_urls_count = current_urls_count
                except KeyboardInterrupt:
                    print("\nReceived keyboard interrupt. Stopping...")
            else:
                # In non-interactive mode, just wait for the spider to finish
                last_check_time = time.time()
                last_urls_count = len(spider.to_visit) + len(spider.pending_urls)
                
                while spider.is_running:
                    time.sleep(1)
                    
                    # Check for inactivity periodically
                    current_time = time.time()
                    if current_time - last_check_time > 10:  # Check every 10 seconds
                        current_urls_count = len(spider.to_visit) + len(spider.pending_urls)
                        
                        # Check if no progress and no URLs to process
                        if (current_urls_count == last_urls_count == 0 and 
                            spider.task_queue.empty() and spider.result_queue.empty()):
                            # If no activity for a while, stop
                            if current_time - spider.last_activity_time > inactivity_timeout:
                                print(f"\nNo URLs processed for {inactivity_timeout} seconds. Stopping crawler...")
                                spider.stop()
                                break
                        
                        # Update for next check
                        last_check_time = current_time
                        last_urls_count = current_urls_count
            
        finally:
            # Ensure spider is stopped properly
            if spider.is_running:
                spider.stop()
                
        return 0
        
    except KeyboardInterrupt:
        print("\nCrawling interrupted by user.")
        return 130  # Standard exit code for SIGINT
        
    except Exception as e:
        print(f"\nError: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # Clean up any existing ChromeDriver processes
    ensure_no_chromedriver_zombies()
    sys.exit(main())
