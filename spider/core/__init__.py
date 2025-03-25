"""
Core module containing the main crawler functionality.

This package contains the main crawler components including the Spider class,
rate controller, and checkpoint management.
"""

from .checkpoint import CheckpointManager
from .crawler import Spider
from .rate_controller import CrawlRateController

__all__ = ["Spider", "CrawlRateController", "CheckpointManager"]
