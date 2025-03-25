"""
Workers module for handling parallel crawling processes.

This package contains components for managing crawling workers and their tasks.
"""

from .manager import WorkerPool
from .worker import Worker, worker_process

__all__ = ["Worker", "worker_process", "WorkerPool"]
