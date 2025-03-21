"""
Workers module for handling parallel crawling processes.

This package contains components for managing crawling workers and their tasks.
"""

from .worker import Worker, worker_process
from .manager import WorkerPool

__all__ = ['Worker', 'worker_process', 'WorkerPool']
