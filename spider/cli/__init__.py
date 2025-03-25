"""
Command-line interface module for the spider crawler.

This package contains modules for parsing command-line arguments
and managing configuration for the spider crawler.
"""

from .argument_parser import create_parser, parse_args
from .config import Configuration, load_config, save_config

__all__ = ["create_parser", "parse_args", "Configuration", "load_config", "save_config"]
