"""
Spider web crawler package.

This package provides a flexible and powerful web crawler for
searching websites for keywords or saving content as markdown.
"""

__version__ = '1.0.0'
__author__ = 'Michael Elliott'

from .core.crawler import Spider
from .core.rate_controller import CrawlRateController
from .core.checkpoint import CheckpointManager
from .content.filter import ContentFilter

__all__ = [
    'Spider',
    'CrawlRateController',
    'CheckpointManager',
    'ContentFilter'
]
