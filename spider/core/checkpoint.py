#!/usr/bin/env python3
"""
Checkpoint management module.

This module contains functionality for saving and loading crawler state,
enabling resumption of crawling after interruption.
"""

import json
import os
import time


class CheckpointManager:
    """
    Handles saving and loading crawler checkpoints to enable resumable crawling.

    This class provides methods for serializing crawler state to disk and
    restoring it later, enabling crawls to be interrupted and resumed.
    """

    def __init__(self, checkpoint_file, auto_save_interval=300):
        """
        Initialize the checkpoint manager.

        Args:
            checkpoint_file: Path to the checkpoint file
            auto_save_interval: Seconds between automatic checkpoint saves
        """
        self.checkpoint_file = checkpoint_file
        self.auto_save_interval = auto_save_interval
        self.last_save_time = 0
        self.last_save_pages = 0

    def save_checkpoint(self, data, force=False):
        """
        Save crawler state to checkpoint file.

        Args:
            data: Dictionary containing crawler state
            force: Whether to force a save regardless of interval

        Returns:
            bool: True if checkpoint was saved, False otherwise
        """
        current_time = time.time()
        pages_visited = data.get("pages_visited", 0)

        # Only save if forced or enough time has passed
        if not force and (current_time - self.last_save_time < self.auto_save_interval):
            # Also save if we've processed many more pages
            if pages_visited - self.last_save_pages < max(10, pages_visited * 0.05):
                return False

        try:
            # Add timestamp to data
            data["checkpoint_time"] = current_time
            data["checkpoint_version"] = "1.0"

            # Use atomic write to prevent corruption
            tmp_file = f"{self.checkpoint_file}.tmp"
            with open(tmp_file, "w") as f:
                json.dump(data, f)

                # Ensure data is written to disk
                f.flush()
                os.fsync(f.fileno())

            # Rename for atomic replace
            os.replace(tmp_file, self.checkpoint_file)

            # Update last save info
            self.last_save_time = current_time
            self.last_save_pages = pages_visited

            return True

        except Exception as e:
            # Try direct write if atomic operation failed
            try:
                print(f"Error with atomic checkpoint save: {e}")
                with open(self.checkpoint_file, "w") as f:
                    json.dump(data, f)

                # Update last save info
                self.last_save_time = current_time
                self.last_save_pages = pages_visited

                return True
            except Exception as e2:
                print(f"Critical error saving checkpoint: {e2}")
                return False

    def load_checkpoint(self):
        """
        Load crawler state from checkpoint file.

        Returns:
            dict: Loaded checkpoint data or None if no checkpoint exists or loading failed
        """
        if not os.path.exists(self.checkpoint_file):
            return None

        try:
            with open(self.checkpoint_file, "r") as f:
                checkpoint_data = json.load(f)

            # Check data validity
            if "checkpoint_time" not in checkpoint_data:
                print("Invalid checkpoint file (missing timestamp)")
                return None

            # Check for required fields
            required_fields = ["visited", "to_visit", "pages_visited"]
            for field in required_fields:
                if field not in checkpoint_data:
                    print(f"Invalid checkpoint file (missing {field})")
                    return None

            print(f"Loaded checkpoint from {self.checkpoint_file}")
            print(f"Checkpoint time: {time.ctime(checkpoint_data['checkpoint_time'])}")
            print(f"Pages visited: {checkpoint_data['pages_visited']}")
            print(f"URLs to visit: {len(checkpoint_data['to_visit'])}")

            return checkpoint_data

        except json.JSONDecodeError:
            print("Error decoding checkpoint file (invalid JSON)")
            return None
        except Exception as e:
            print(f"Error loading checkpoint: {e}")
            return None

    def should_save_checkpoint(self, pages_visited):
        """
        Determine if it's time to save a checkpoint based on time or progress.

        Args:
            pages_visited: Current number of pages visited

        Returns:
            bool: True if checkpoint should be saved, False otherwise
        """
        current_time = time.time()

        # Check time-based interval
        if current_time - self.last_save_time >= self.auto_save_interval:
            return True

        # Check progress-based interval (5% more pages or at least 10 pages)
        pages_threshold = max(10, self.last_save_pages * 0.05)
        if pages_visited - self.last_save_pages >= pages_threshold:
            return True

        # No need to save yet
        return False
