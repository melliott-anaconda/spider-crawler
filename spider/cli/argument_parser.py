#!/usr/bin/env python3
"""
Command-line argument parsing module.

This module provides functions for setting up and parsing command-line
arguments for the spider crawler.
"""

import argparse
import os
import sys
from urllib.parse import urlparse


def create_parser():
    """
    Create the command-line argument parser.
    
    Returns:
        argparse.ArgumentParser: Configured argument parser
    """
    parser = argparse.ArgumentParser(
        description='Spider a website for specific keywords using parallel processes with adaptive rate control'
    )
    
    # Required arguments
    parser.add_argument('url', type=str,
                        help='Starting URL to spider from')
    
    # Basic crawling options
    parser.add_argument('--max-pages', type=int, default=None, 
                        help='Maximum number of pages to spider (default: unlimited)')
    parser.add_argument('--output', type=str, default='keyword_report.csv',
                        help='Output CSV file path (default: keyword_report.csv)')
    parser.add_argument('--keywords', type=str, default="",
                        help='Comma-separated list of keywords to search for')
    parser.add_argument('--path-prefix', type=str, default=None,
                        help='Optional path prefix to restrict crawling to (e.g., /docs/)')
    
    # Browser options
    parser.add_argument('--visible', action='store_true',
                        help='Run in visible browser mode instead of headless (default: headless)')
    parser.add_argument('--webdriver-path', type=str, default=None,
                        help='Path to the webdriver executable (optional)')
    
    # Checkpoint options
    parser.add_argument('--resume', action='store_true',
                        help='Resume from checkpoint if available (default: false)')
    parser.add_argument('--max-restarts', type=int, default=3,
                        help='Maximum number of WebDriver restarts (default: 3)')
    parser.add_argument('--checkpoint-interval', type=int, default=10,
                        help='How often to save checkpoints, in minutes (default: 10)')
    
    # Rate control parameters (limits only)
    rate_group = parser.add_argument_group('Rate Control Options')
    rate_group.add_argument('--max-workers', type=int, default=8,
                        help='Maximum number of parallel workers allowed (default: 8)')
    rate_group.add_argument('--min-workers', type=int, default=1,
                        help='Minimum number of parallel workers to maintain (default: 1)')
    rate_group.add_argument('--min-delay', type=float, default=0.5,
                        help='Minimum delay between requests in seconds (default: 0.5)')
    rate_group.add_argument('--max-delay', type=float, default=30.0,
                        help='Maximum delay between requests in seconds (default: 30.0)')
    rate_group.add_argument('--initial-delay', type=float, default=1.0,
                        help='Initial delay between requests in seconds (default: 1.0)')
    rate_group.add_argument('--disable-adaptive-control', action='store_true',
                        help='Disable adaptive rate control (not recommended)')
    rate_group.add_argument('--aggressive-throttling', action='store_true',
                        help='Use more aggressive throttling when rate limiting is detected')
    
    # Content filtering options
    content_group = parser.add_argument_group('Content Filtering Options')
    content_group.add_argument('--include-headers', action='store_true',
                        help='Include header content in keyword search (default: exclude)')
    content_group.add_argument('--include-menus', action='store_true',
                        help='Include menu/navigation content in keyword search (default: exclude)')
    content_group.add_argument('--include-footers', action='store_true',
                        help='Include footer content in keyword search (default: exclude)')
    content_group.add_argument('--include-sidebars', action='store_true',
                        help='Include sidebar content in keyword search (default: exclude)')
    content_group.add_argument('--exclude-selectors', type=str, default="",
                        help='Comma-separated CSS selectors to exclude (e.g., ".ads,.comments")')
    
    # Domain crawling options
    domain_group = parser.add_argument_group('Domain Options')
    domain_group.add_argument('--allow-subdomains', action='store_true',
                        help='Allow crawling across different subdomains of the same domain (default: stay on initial subdomain)')
    domain_group.add_argument('--allowed-extensions', type=str, default="",
                        help='Comma-separated list of additional file extensions to allow (e.g., ".pdf,.docx")')
    
    # Special modes
    mode_group = parser.add_argument_group('Special Modes')
    mode_group.add_argument('--spa', action='store_true',
                        help='Enable Single Page Application (SPA) mode with enhanced JavaScript support')
    mode_group.add_argument('--markdown-mode', action='store_true',
                        help='Extract and save page content as markdown files instead of keyword searching')
    mode_group.add_argument('--include-all-content', action='store_true',
                        help='When using markdown mode, include all page content (headers, menus, etc.)')
    
    # Configuration file options
    config_group = parser.add_argument_group('Configuration Options')
    config_group.add_argument('--config', type=str, default=None,
                        help='Path to configuration file (JSON)')
    config_group.add_argument('--save-config', type=str, default=None,
                        help='Save current settings to configuration file')
    
    return parser


def parse_args(args=None):
    """
    Parse command-line arguments.
    
    Args:
        args: Command-line arguments to parse (uses sys.argv if None)
        
    Returns:
        argparse.Namespace: Parsed arguments
        
    Raises:
        SystemExit: If required arguments are missing or invalid
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    # Validate URL
    try:
        parsed_url = urlparse(parsed_args.url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid URL format")
    except:
        parser.error("Invalid URL. Please provide a valid URL (e.g., https://example.com)")
    
    # Handle keyword requirement (except in markdown mode)
    if not parsed_args.keywords and not parsed_args.markdown_mode:
        if sys.stdin.isatty():  # Interactive mode
            keywords = input("Please enter comma-separated keywords to search for: ")
            parsed_args.keywords = keywords
        else:
            parser.error("No keywords provided. Please specify keywords with --keywords.")
    
    # Process keywords into a list
    if parsed_args.keywords:
        parsed_args.keywords = [k.strip() for k in parsed_args.keywords.split(',') if k.strip()]
    elif parsed_args.markdown_mode:
        parsed_args.keywords = ["placeholder"]  # Placeholder for markdown mode
    
    # Generate output filename if not specified
    if parsed_args.output == 'keyword_report.csv':
        # Create a filename based on the domain
        parsed_url = urlparse(parsed_args.url)
        domain = parsed_url.netloc.replace('.', '_')
        
        if parsed_args.markdown_mode:
            # In markdown mode, we don't need a CSV output file, but still need a base name for checkpoint
            parsed_args.output = f"{domain}_checkpoint_data.csv"
        else:
            parsed_args.output = f"{domain}_keyword_report.csv"
    
    # Check for checkpoint file if --resume is specified
    if parsed_args.resume:
        checkpoint_file = f"{parsed_args.output}.checkpoint.json"
        if not os.path.exists(checkpoint_file):
            print(f"Warning: No checkpoint file found at {checkpoint_file}. Starting fresh.")
            parsed_args.resume = False
    
    # Process allowed extensions
    if parsed_args.allowed_extensions:
        exts = set(ext.strip() for ext in parsed_args.allowed_extensions.split(',') if ext.strip())
        # Ensure extensions start with a dot
        parsed_args.allowed_extensions = {ext if ext.startswith('.') else '.' + ext for ext in exts}
    else:
        parsed_args.allowed_extensions = None
        
    # Process content filter exclude selectors
    if parsed_args.exclude_selectors:
        parsed_args.exclude_selectors = [s.strip() for s in parsed_args.exclude_selectors.split(',') if s.strip()]
    else:
        parsed_args.exclude_selectors = []
    
    # Validate rate control parameters
    if parsed_args.min_workers > parsed_args.max_workers:
        print(f"Warning: min_workers ({parsed_args.min_workers}) exceeds max_workers ({parsed_args.max_workers}). Setting min_workers to {parsed_args.max_workers}.")
        parsed_args.min_workers = parsed_args.max_workers
    
    if parsed_args.initial_delay < parsed_args.min_delay:
        print(f"Warning: initial_delay ({parsed_args.initial_delay}) is less than min_delay ({parsed_args.min_delay}). Setting initial_delay to {parsed_args.min_delay}.")
        parsed_args.initial_delay = parsed_args.min_delay
    
    if parsed_args.min_delay > parsed_args.max_delay:
        print(f"Warning: min_delay ({parsed_args.min_delay}) exceeds max_delay ({parsed_args.max_delay}). Setting min_delay to {parsed_args.max_delay}.")
        parsed_args.min_delay = parsed_args.max_delay
    
    return parsed_args


def print_config_summary(args):
    """
    Print a summary of the configuration.
    
    Args:
        args: Parsed arguments
    """
    print(f"\nStarting adaptive spider with the following configuration:")
    print(f"- Starting URL: {args.url}")
    
    if args.markdown_mode:
        print(f"- Mode: Markdown extraction (saving page content as .md files)")
        if args.include_all_content:
            print(f"  - Including all page content (headers, menus, footers, sidebars)")
        else:
            print(f"  - Filtering content based on content filter settings")
    else:
        print(f"- Mode: Keyword search")
        print(f"- Keywords: {args.keywords}")
        print(f"- Output file: {args.output}")
    
    print(f"- Max pages: {'Unlimited' if args.max_pages is None else args.max_pages}")
    print(f"- Rate control:")
    print(f"  - Initial workers: {args.min_workers + (args.max_workers - args.min_workers) // 2} (will adjust automatically)")
    print(f"  - Min/Max workers: {args.min_workers}-{args.max_workers}")
    print(f"  - Initial delay: {args.initial_delay}s (will adjust automatically)")
    print(f"  - Min/Max delay: {args.min_delay}s-{args.max_delay}s")
    print(f"  - Adaptive control: {'Disabled' if args.disable_adaptive_control else 'Enabled'}")
    print(f"  - Throttling strategy: {'Aggressive' if args.aggressive_throttling else 'Standard'}")
    
    if args.path_prefix:
        print(f"- Path prefix: {args.path_prefix}")
    print(f"- Browser mode: {'Visible' if args.visible else 'Headless'}")
    print(f"- Resume from checkpoint: {'Yes' if args.resume else 'No'}")
    print(f"- Max restarts: {args.max_restarts}")
    print(f"- Checkpoint interval: Every {args.checkpoint_interval} minutes")
    print(f"- Content filtering:")
    print(f"  - Include headers: {args.include_headers}")
    print(f"  - Include menus: {args.include_menus}")
    print(f"  - Include footers: {args.include_footers}")
    print(f"  - Include sidebars: {args.include_sidebars}")
    if args.exclude_selectors:
        print(f"  - Custom exclude selectors: {', '.join(args.exclude_selectors)}")
    print(f"- Allow crawling across subdomains: {args.allow_subdomains}")
    print(f"- Resource filtering:")
    print(f"  - Non-webpage resources: {'Allowed extensions: ' + ', '.join(args.allowed_extensions) if args.allowed_extensions else 'Excluded (default)'}")
    
    # Print SPA mode if enabled
    if args.spa:
        print(f"- SPA mode: Enabled (enhanced JavaScript support for single-page applications)")
    print()
