"""
Spider web crawler package.

This package provides a flexible and powerful web crawler for
searching websites for keywords or saving content as markdown.
"""

__version__ = "1.1.7"
__author__ = "Michael Elliott"

from .content.filter import ContentFilter
from .core.checkpoint import CheckpointManager
from .core.crawler import Spider
from .core.rate_controller import CrawlRateController

__all__ = ["Spider", "CrawlRateController", "CheckpointManager", "ContentFilter"]
