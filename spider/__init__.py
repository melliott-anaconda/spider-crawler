"""
Spider web crawler package.

This package provides a flexible and powerful web crawler for
searching websites for keywords or saving content as markdown.
"""

__version__ = "1.1.5"
__author__ = "Michael Elliott"

import atexit
import os
import threading
from .content.filter import ContentFilter
from .core.checkpoint import CheckpointManager
from .core.crawler import Spider
from .core.rate_controller import CrawlRateController

def emergency_exit_handler():
    """Force exit if the process is still running after 60 seconds."""
    def _exit_timer():
        import time
        time.sleep(60)  # Wait 60 seconds max
        print("Emergency exit handler forcing termination")
        os._exit(0)
    
    # Start a daemon thread that will force exit
    t = threading.Thread(target=_exit_timer, daemon=True)
    t.start()

# Register the emergency exit handler
atexit.register(emergency_exit_handler)

__all__ = ["Spider", "CrawlRateController", "CheckpointManager", "ContentFilter"]
