"""
Core module containing the main crawler functionality.

This package contains the main crawler components including the Spider class,
rate controller, and checkpoint management.
"""

from .crawler import Spider
from .rate_controller import CrawlRateController
from .checkpoint import CheckpointManager

__all__ = [
    'Spider',
    'CrawlRateController',
    'CheckpointManager'
]
