#!/usr/bin/env python3
"""
Configuration management module.

This module provides functionality for loading and saving configuration
files, and for managing crawler configuration.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Set, Optional
from urllib.parse import urlparse


@dataclass
class Configuration:
    """
    Configuration class for the spider crawler.
    
    This dataclass holds all configuration parameters for the crawler,
    allowing for easy serialization and deserialization.
    """
    # URL and basic parameters
    url: str
    output_file: str = "keyword_report.csv"
    keywords: List[str] = field(default_factory=list)
    max_pages: Optional[int] = None
    path_prefix: Optional[str] = None
    
    # Browser configuration
    headless: bool = True
    webdriver_path: Optional[str] = None
    max_restarts: int = 3
    
    # Checkpoint configuration
    resume: bool = False
    checkpoint_interval: int = 10  # minutes
    
    # Rate control
    min_workers: int = 1
    max_workers: int = 8
    initial_workers: int = 4
    min_delay: float = 0.5
    max_delay: float = 30.0
    initial_delay: float = 1.0
    adaptive_rate_control: bool = True
    aggressive_throttling: bool = False
    response_window_size: int = 20
    
    # Content filtering
    include_headers: bool = False
    include_menus: bool = False
    include_footers: bool = False
    include_sidebars: bool = False
    exclude_selectors: List[str] = field(default_factory=list)
    
    # Domain configuration
    allow_subdomains: bool = False
    allowed_extensions: Optional[Set[str]] = None
    
    # Special modes
    spa_mode: bool = False
    markdown_mode: bool = False
    include_all_content: bool = False
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate URL
        try:
            parsed_url = urlparse(self.url)
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValueError("Invalid URL format")
        except:
            raise ValueError(f"Invalid URL: {self.url}")
        
        # Ensure keywords are present (except in markdown mode)
        if not self.keywords and not self.markdown_mode:
            raise ValueError("Keywords are required for keyword search mode")
        
        # Ensure rate control parameters are valid
        if self.min_workers > self.max_workers:
            print(f"Warning: min_workers ({self.min_workers}) exceeds max_workers ({self.max_workers}). Setting min_workers to {self.max_workers}.")
            self.min_workers = self.max_workers
        
        if self.initial_delay < self.min_delay:
            print(f"Warning: initial_delay ({self.initial_delay}) is less than min_delay ({self.min_delay}). Setting initial_delay to {self.min_delay}.")
            self.initial_delay = self.min_delay
        
        if self.min_delay > self.max_delay:
            print(f"Warning: min_delay ({self.min_delay}) exceeds max_delay ({self.max_delay}). Setting min_delay to {self.max_delay}.")
            self.min_delay = self.max_delay
        
        # Set initial workers to a reasonable value
        self.initial_workers = min(
            self.max_workers, 
            max(self.min_workers, (self.min_workers + self.max_workers) // 2)
        )
        
        # Normalize allowed extensions
        if self.allowed_extensions:
            self.allowed_extensions = {
                ext if ext.startswith('.') else '.' + ext 
                for ext in self.allowed_extensions
            }
    
    @classmethod
    def from_args(cls, args):
        """
        Create a Configuration instance from parsed command-line arguments.
        
        Args:
            args: Parsed command-line arguments
            
        Returns:
            Configuration: Configuration instance
        """
        return cls(
            url=args.url,
            output_file=args.output,
            keywords=args.keywords,
            max_pages=args.max_pages,
            path_prefix=args.path_prefix,
            headless=not args.visible,
            webdriver_path=args.webdriver_path,
            max_restarts=args.max_restarts,
            resume=args.resume,
            checkpoint_interval=args.checkpoint_interval,
            min_workers=args.min_workers,
            max_workers=args.max_workers,
            initial_workers=args.min_workers + (args.max_workers - args.min_workers) // 2,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            initial_delay=args.initial_delay,
            adaptive_rate_control=not args.disable_adaptive_control,
            aggressive_throttling=args.aggressive_throttling,
            include_headers=args.include_headers,
            include_menus=args.include_menus,
            include_footers=args.include_footers,
            include_sidebars=args.include_sidebars,
            exclude_selectors=args.exclude_selectors,
            allow_subdomains=args.allow_subdomains,
            allowed_extensions=args.allowed_extensions,
            spa_mode=args.spa,
            markdown_mode=args.markdown_mode,
            include_all_content=args.include_all_content
        )
    
    def to_dict(self):
        """
        Convert configuration to a dictionary.
        
        Returns:
            dict: Dictionary representation of the configuration
        """
        # Use dataclasses.asdict to convert to dict
        config_dict = asdict(self)
        
        # Convert sets to lists for JSON serialization
        if config_dict['allowed_extensions']:
            config_dict['allowed_extensions'] = list(config_dict['allowed_extensions'])
        
        return config_dict
    
    @classmethod
    def from_dict(cls, config_dict):
        """
        Create a Configuration instance from a dictionary.
        
        Args:
            config_dict: Dictionary containing configuration parameters
            
        Returns:
            Configuration: Configuration instance
        """
        # Make a copy to avoid modifying the original
        config = config_dict.copy()
        
        # Convert allowed_extensions list back to set
        if 'allowed_extensions' in config and config['allowed_extensions']:
            config['allowed_extensions'] = set(config['allowed_extensions'])
        
        # Create instance
        return cls(**config)
    
    def print_summary(self):
        """Print a summary of the configuration."""
        print(f"\nSpider configuration:")
        print(f"- Starting URL: {self.url}")
        
        if self.markdown_mode:
            print(f"- Mode: Markdown extraction (saving content as .md files)")
            if self.include_all_content:
                print(f"  - Including all page content")
            else:
                print(f"  - Filtering content based on settings")
        else:
            print(f"- Mode: Keyword search")
            print(f"- Keywords: {self.keywords}")
            print(f"- Output file: {self.output_file}")
        
        print(f"- Max pages: {'Unlimited' if self.max_pages is None else self.max_pages}")
        print(f"- Rate control:")
        print(f"  - Workers: {self.min_workers}-{self.max_workers} (initial: {self.initial_workers})")
        print(f"  - Delay: {self.min_delay}s-{self.max_delay}s (initial: {self.initial_delay}s)")
        print(f"  - Adaptive control: {'Enabled' if self.adaptive_rate_control else 'Disabled'}")
        
        if self.path_prefix:
            print(f"- Path prefix: {self.path_prefix}")
        print(f"- Browser mode: {'Headless' if self.headless else 'Visible'}")
        print(f"- Resume from checkpoint: {'Yes' if self.resume else 'No'}")
        
        if self.spa_mode:
            print(f"- SPA mode: Enabled")
        
        print()


def load_config(config_file: str) -> Configuration:
    """
    Load configuration from a JSON file.
    
    Args:
        config_file: Path to the configuration file
        
    Returns:
        Configuration: Configuration instance
        
    Raises:
        FileNotFoundError: If the configuration file does not exist
        json.JSONDecodeError: If the configuration file is not valid JSON
        KeyError: If the configuration file is missing required fields
    """
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    try:
        with open(config_file, 'r') as f:
            config_dict = json.load(f)
        
        # Check for required fields
        required_fields = ['url']
        for field in required_fields:
            if field not in config_dict:
                raise KeyError(f"Missing required field in configuration: {field}")
        
        return Configuration.from_dict(config_dict)
    
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in configuration file: {e.msg}", e.doc, e.pos)


def save_config(config: Configuration, config_file: str) -> None:
    """
    Save configuration to a JSON file.
    
    Args:
        config: Configuration instance
        config_file: Path to the configuration file
        
    Raises:
        IOError: If the configuration file cannot be written
    """
    try:
        # Convert to JSON-serializable dict
        config_dict = config.to_dict()
        
        # Create directory if it doesn't exist
        directory = os.path.dirname(os.path.abspath(config_file))
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        
        # Write to file
        with open(config_file, 'w') as f:
            json.dump(config_dict, f, indent=2)
        
        print(f"Configuration saved to {config_file}")
    
    except IOError as e:
        raise IOError(f"Error saving configuration: {e}")


def load_config_from_args(args):
    """
    Load configuration from command-line arguments or a config file.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Configuration: Configuration instance
    """
    # If config file specified, load from file
    if args.config:
        try:
            config = load_config(args.config)
            print(f"Loaded configuration from {args.config}")
            
            # Override with any explicitly specified command-line arguments
            config = _override_config_from_args(config, args)
            return config
            
        except Exception as e:
            print(f"Error loading configuration file: {e}")
            print("Falling back to command-line arguments")
    
    # Create configuration from command-line arguments
    return Configuration.from_args(args)


def _override_config_from_args(config, args):
    """
    Override configuration with explicitly specified command-line arguments.
    
    Args:
        config: Existing configuration
        args: Parsed command-line arguments
        
    Returns:
        Configuration: Updated configuration
    """
    # Get default argument values
    parser = create_parser()
    defaults = vars(parser.parse_args([config.url]))
    
    # Get actual argument values
    arg_dict = vars(args)
    
    # Override config with explicitly specified arguments
    for key, value in arg_dict.items():
        # Skip if the value is the same as the default
        if value != defaults.get(key):
            # Special handling for certain fields
            if key == 'visible':
                config.headless = not value
            elif key == 'disable_adaptive_control':
                config.adaptive_rate_control = not value
            elif key == 'spa':
                config.spa_mode = value
            else:
                # For other fields, set directly if they exist in the config
                if hasattr(config, key):
                    setattr(config, key, value)
    
    return config


# Import here to avoid circular imports
from .argument_parser import create_parser
