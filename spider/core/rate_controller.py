#!/usr/bin/env python3
"""
Rate controller module for managing crawler speed.

This module contains the CrawlRateController class that implements adaptive throttling
to avoid overwhelming target servers while maximizing crawl efficiency.
"""

import threading
import time


class CrawlRateController:
    """
    Controls crawl rate by managing worker count and request delays based on server responses.
    Implements adaptive throttling to avoid rate limiting and maximize throughput.
    """
    def __init__(self, initial_workers=4, max_workers=8, min_workers=1, 
                 initial_delay=1.0, min_delay=0.5, max_delay=30.0,
                 response_window_size=20, adjustment_interval=30,
                 aggressive_throttling=True):
        """
        Initialize the rate controller with the specified parameters.
        
        Args:
            initial_workers: Starting number of workers
            max_workers: Maximum number of workers to allow
            min_workers: Minimum number of workers to maintain
            initial_delay: Starting delay between requests in seconds
            min_delay: Minimum delay between requests in seconds
            max_delay: Maximum delay between requests in seconds
            response_window_size: Number of recent responses to consider for adjustments
            adjustment_interval: Minimum seconds between adjustments
            aggressive_throttling: Whether to respond more aggressively to rate limiting
        """
        # Worker settings
        self.target_workers = initial_workers
        self.max_workers = max_workers
        self.min_workers = min_workers
        
        # Delay settings
        self.current_delay = initial_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        
        # Adjustment settings
        self.response_window_size = response_window_size
        self.adjustment_interval = adjustment_interval
        self.aggressive_throttling = aggressive_throttling
        
        # Response tracking
        self.recent_responses = []
        self.last_adjustment_time = time.time()
        
        # Rate limit cooldown tracking
        self._last_rate_limit_action = None
        self._rate_limit_cooldown = 300  # 5 minutes cooldown after rate limiting
        
        # Stats tracking
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'rate_limited_requests': 0,
            'server_errors': 0,
            'client_errors': 0,
            'adjustments_made': 0,
            'last_adjustment_reason': "Initial settings"
        }
        
        # Status tracking
        self._throttling_active = False
        self._recovery_mode = False
        self._recovery_start_time = None
        self._consecutive_successes = 0
        self._consecutive_failures = 0
        self._rate_limit_detected_time = None
        self._recovery_level = 0  # 0=none, 1=light, 2=moderate, 3=severe
        
        # Lock for thread safety
        self.lock = threading.RLock()
    
    def register_response(self, response_data):
        """
        Register a response for rate control decision making.
        
        Args:
            response_data: Dictionary containing response information with at least:
                           - 'status': String status ('success', 'http_error', 'error', etc.)
                           - 'http_status': Integer HTTP status code (optional)
                           - 'handling': Response handling info (optional)
                           
        Returns:
            bool: True if the response was successfully registered
        """
        with self.lock:
            self.stats['total_requests'] += 1
            
            # Create response summary for rate control
            response_summary = {
                'success': response_data.get('status') == 'success',
                'action': 'process',
                'reason': f"Status: {response_data.get('status')}",
                'timestamp': time.time(),
                'rate_limited': False  # Default to not rate limited
            }
            
            # Default status is success unless proven otherwise
            is_success = True
            
            # Handle HTTP errors specifically
            if response_data.get('status') == 'http_error':
                http_status = response_data.get('http_status', 0)
                handling = response_data.get('handling', {})
                
                response_summary['success'] = False
                response_summary['action'] = handling.get('action', 'skip')
                response_summary['reason'] = handling.get('reason', 'HTTP error')
                response_summary['http_status'] = http_status
                
                is_success = False
                
                # Check if this is a rate limiting response
                is_rate_limited = (handling.get('action') == 'throttle_and_retry' or 
                                  http_status == 429 or 
                                  handling.get('rate_limited', False))
                
                response_summary['rate_limited'] = is_rate_limited
                
                # Update error stats
                if is_rate_limited:
                    self.stats['rate_limited_requests'] += 1
                    self._consecutive_failures += 1
                    self._consecutive_successes = 0
                    self._throttling_active = True
                    
                    # Record rate limiting time
                    self._rate_limit_detected_time = time.time()
                    
                    # Enter recovery mode with appropriate severity
                    if not self._recovery_mode:
                        self._recovery_mode = True
                        self._recovery_start_time = time.time()
                        self._recovery_level = 2  # Moderate recovery
                    else:
                        # Increase severity if we're seeing more rate limiting while already in recovery
                        self._recovery_level = min(3, self._recovery_level + 1)  # Increase up to severe
                        
                elif 400 <= http_status < 500:
                    self.stats['client_errors'] += 1
                    is_success = False
                elif 500 <= http_status < 600:
                    self.stats['server_errors'] += 1
                    is_success = False
                    
                    # Modest throttling for server errors
                    if self.stats['server_errors'] > 5 and not self._recovery_mode:
                        self._recovery_mode = True
                        self._recovery_start_time = time.time()
                        self._recovery_level = 1  # Light recovery
                    
            elif response_data.get('status') == 'success':
                self.stats['successful_requests'] += 1
                is_success = True
                
                if is_success:
                    self._consecutive_successes += 1
                    self._consecutive_failures = 0
                    
                    # Check if we can reduce recovery severity
                    if self._recovery_mode:
                        recovery_time = time.time() - self._recovery_start_time
                        
                        # Gradually step down recovery level based on consecutive successes
                        if self._consecutive_successes >= 20:
                            # After 20 consecutive successes, reduce severity
                            self._recovery_level = max(0, self._recovery_level - 1)
                            
                            # Reset consecutive counter after taking action
                            self._consecutive_successes = 0
                            
                            if self._recovery_level == 0:
                                self._recovery_mode = False
                                self._throttling_active = False
                                print(f"Exiting recovery mode after {recovery_time:.1f}s and {self._consecutive_successes} consecutive successes")
            
            # Add to recent responses window
            self.recent_responses.append(response_summary)
            if len(self.recent_responses) > self.response_window_size:
                # Remove oldest responses 
                self.recent_responses = self.recent_responses[-self.response_window_size:]
            
            return True
    
    def should_adjust_now(self):
        """
        Determine if it's time to consider a rate adjustment.
        
        Returns:
            bool: True if adjustment should be considered
        """
        with self.lock:
            now = time.time()
            
            # Check if we're in rate limit cooldown
            if self._last_rate_limit_action is not None:
                cooldown_remaining = self._rate_limit_cooldown - (now - self._last_rate_limit_action)
                if cooldown_remaining > 0:
                    return False  # Still in cooldown
            
            # Always consider adjustment immediately after rate limiting
            if self._throttling_active and self.stats['rate_limited_requests'] > 0:
                if self._rate_limit_detected_time and now - self._rate_limit_detected_time < 10:
                    return True
                
            # More frequent adjustments during recovery
            if self._recovery_mode:
                # The higher the recovery level, the more frequent the adjustments
                dynamic_interval = max(5, self.adjustment_interval / (self._recovery_level + 1))
                return now - self.last_adjustment_time >= dynamic_interval
                
            # Otherwise respect the standard adjustment interval
            return (now - self.last_adjustment_time >= self.adjustment_interval and 
                    len(self.recent_responses) >= min(5, self.response_window_size))
    
    def force_worker_reduction(self, reason="Emergency worker reduction"):
        """
        Force an immediate reduction in worker count, typically in response to rate limiting.
        
        Args:
            reason: Reason for the emergency reduction
            
        Returns:
            tuple: (new_worker_count, new_delay, reason)
        """
        with self.lock:
            original_workers = self.target_workers
            original_delay = self.current_delay
            
            print(f"FORCE_WORKER_REDUCTION called: current workers={original_workers}, current delay={original_delay:.2f}s")
            print(f"Recovery level: {self._recovery_level}, Recovery mode: {self._recovery_mode}")
            
            # Calculate reduction based on recovery level
            if self._recovery_level >= 3:  # Severe
                # Drastic reduction - minimum workers and long delay
                self.target_workers = self.min_workers
                self.current_delay = min(self.max_delay, self.current_delay * 3.0)
                print(f"SEVERE REDUCTION: min workers and 3x delay")
            elif self._recovery_level == 2:  # Moderate
                # Significant reduction
                self.target_workers = max(self.min_workers, self.target_workers // 2)
                self.current_delay = min(self.max_delay, self.current_delay * 2.0)
                print(f"MODERATE REDUCTION: halving workers and doubling delay")
            else:  # Light
                # Moderate reduction
                self.target_workers = max(self.min_workers, self.target_workers - 1)
                self.current_delay = min(self.max_delay, self.current_delay * 1.5)
                print(f"LIGHT REDUCTION: removing 1 worker and increasing delay by 50%")
            
            # Enter or increase recovery mode
            self._recovery_mode = True
            self._throttling_active = True
            self._recovery_start_time = time.time()
            
            # Set rate limit cooldown timestamp
            self._last_rate_limit_action = time.time()
            
            print(f"FORCED REDUCTION RESULT: workers {original_workers} → {self.target_workers}, delay {original_delay:.2f}s → {self.current_delay:.2f}s")
            
            # Update stats
            self.last_adjustment_time = time.time()
            self.stats['adjustments_made'] += 1
            self.stats['last_adjustment_reason'] = reason
            
            # Clear rate limiting responses from window to avoid repeated triggers
            self.recent_responses = [r for r in self.recent_responses if not r.get('rate_limited', False)]
            
            return self.target_workers, self.current_delay, reason
    
    def adjust_rate_if_needed(self, force=False):
        """
        Adjust crawl rate parameters if needed based on recent responses.
        
        Args:
            force: Whether to force an adjustment regardless of timing
            
        Returns:
            tuple: (changed, new_workers, new_delay, reason)
                   - changed: Boolean indicating if parameters were changed
                   - new_workers: Updated target worker count
                   - new_delay: Updated delay value
                   - reason: String explaining the adjustment reason
        """
        # Check cooldown period for rate limit actions unless forced
        if not force and self._last_rate_limit_action is not None:
            cooldown_remaining = self._rate_limit_cooldown - (time.time() - self._last_rate_limit_action)
            if cooldown_remaining > 0:
                return False, self.target_workers, self.current_delay, f"In rate limit cooldown (for {int(cooldown_remaining)}s more)"
            
        if not force and not self.should_adjust_now():
            return False, self.target_workers, self.current_delay, "No adjustment needed"
            
        with self.lock:
            # Calculate success metrics
            total_responses = len(self.recent_responses)
            if total_responses == 0:
                return False, self.target_workers, self.current_delay, "No responses to analyze"
            
            # Count different types of responses
            success_count = sum(1 for r in self.recent_responses if r.get('success', False))
            rate_limited_count = sum(1 for r in self.recent_responses if r.get('rate_limited', False))
            server_error_count = sum(1 for r in self.recent_responses 
                                    if not r.get('success', False) and
                                    400 <= r.get('http_status', 0) < 600)
            
            # Calculate success rate
            success_rate = success_count / total_responses
            
            # Original values for comparison
            original_workers = self.target_workers
            original_delay = self.current_delay
            
            # Determine new settings
            # Check for rate limiting
            if rate_limited_count > 0:
                # Any rate limiting means we need to throttle back significantly
                # Defer to force_worker_reduction for the specific strategy
                changed, new_workers, new_delay, reason = True, *self.force_worker_reduction(f"Rate limiting detected ({rate_limited_count}/{total_responses})")
                
                # Clear rate limiting responses from window to avoid repeated triggers
                self.recent_responses = [r for r in self.recent_responses if not r.get('rate_limited', False)]
                
                return changed, new_workers, new_delay, reason
            
            # Check for high server error rate  
            elif server_error_count / total_responses > 0.2:  # More than 20% server errors
                # Server might be overloaded, throttle back moderately
                self.target_workers = max(self.min_workers, self.target_workers - 1)
                self.current_delay = min(self.max_delay, self.current_delay * 1.3)
                
                # Enter light recovery mode if not already in recovery
                if not self._recovery_mode:
                    self._recovery_mode = True
                    self._recovery_start_time = time.time()
                    self._recovery_level = 1  # Light recovery
                
                reason = (f"High server error rate ({server_error_count}/{total_responses}), "
                          f"reducing workers to {self.target_workers} and "
                          f"increasing delay to {self.current_delay:.1f}s")
            
            # If in recovery mode, be more conservative with scaling up
            elif self._recovery_mode:
                recovery_time = time.time() - self._recovery_start_time
                
                # Different behavior based on recovery level
                if self._recovery_level >= 2:  # Moderate or Severe
                    # Very cautious, only adjust if perfect success rate for a while
                    if success_rate >= 0.98 and self._consecutive_successes >= 30 and recovery_time > 120:
                        # Very slight easing of restrictions
                        if self.target_workers < self.max_workers:
                            self.target_workers += 1
                            reason = (f"Careful recovery after {recovery_time:.0f}s, "
                                      f"slightly increasing workers to {self.target_workers}")
                        elif self.current_delay > self.min_delay * 2:
                            self.current_delay = max(self.min_delay, self.current_delay / 1.1)
                            reason = (f"Careful recovery after {recovery_time:.0f}s, "
                                     f"slightly decreasing delay to {self.current_delay:.1f}s")
                        else:
                            # Step down recovery level
                            self._recovery_level = 1  # Move to light recovery
                            reason = (f"Stepping down to light recovery after {recovery_time:.0f}s")
                    else:
                        reason = (f"Maintaining restrictive parameters during recovery "
                                 f"(level {self._recovery_level}, time: {recovery_time:.0f}s)")
                        return False, self.target_workers, self.current_delay, reason
                
                else:  # Light recovery (level 1)
                    # More willing to adjust, but still cautious
                    if success_rate >= 0.95 and self._consecutive_successes >= 15:
                        if self.target_workers < self.max_workers:
                            self.target_workers += 1
                            reason = (f"Recovery mode (light), cautiously increasing workers to {self.target_workers}")
                        elif self.current_delay > self.min_delay:
                            self.current_delay = max(self.min_delay, self.current_delay / 1.2)
                            reason = (f"Recovery mode (light), cautiously decreasing delay to {self.current_delay:.1f}s")
                        else:
                            # Exit recovery mode
                            self._recovery_mode = False
                            self._throttling_active = False
                            reason = (f"Exiting recovery mode after {recovery_time:.0f}s with "
                                     f"high success rate ({success_rate:.1%})")
                    else:
                        reason = (f"Maintaining parameters during light recovery "
                                 f"(success rate: {success_rate:.1%})")
                        return False, self.target_workers, self.current_delay, reason
            
            # Adjust based on success rate when not in recovery
            elif success_rate >= 0.95:  # Very high success rate
                # If things are going well, cautiously increase throughput
                if self.target_workers < self.max_workers:
                    self.target_workers += 1
                    reason = (f"High success rate ({success_rate:.1%}), "
                             f"increasing workers to {self.target_workers}")
                elif self.current_delay > self.min_delay:
                    # If at max workers but delay is high, reduce delay
                    self.current_delay = max(self.min_delay, self.current_delay / 1.2)
                    reason = (f"High success rate ({success_rate:.1%}) at max workers, "
                             f"decreasing delay to {self.current_delay:.1f}s")
                else:
                    reason = (f"Maintaining parameters at optimal performance "
                             f"(success rate: {success_rate:.1%})")
                    return False, self.target_workers, self.current_delay, reason
            
            elif success_rate >= 0.8:  # Good success rate
                # Maintain current settings
                reason = f"Good success rate ({success_rate:.1%}), maintaining current parameters"
                return False, self.target_workers, self.current_delay, reason
            
            elif success_rate >= 0.5:  # Moderate success rate
                # Minor throttling
                if self.target_workers > self.min_workers + 1:
                    self.target_workers -= 1
                    reason = (f"Moderate success rate ({success_rate:.1%}), "
                             f"slightly reducing workers to {self.target_workers}")
                else:
                    self.current_delay = min(self.max_delay, self.current_delay * 1.2)
                    reason = (f"Moderate success rate ({success_rate:.1%}) at near-minimum workers, "
                             f"increasing delay to {self.current_delay:.1f}s")
            
            else:  # Poor success rate
                # Significant throttling
                prev_target = self.target_workers
                self.target_workers = max(self.min_workers, self.target_workers - max(1, self.target_workers // 3))
                self.current_delay = min(self.max_delay, self.current_delay * 1.5)
                
                # Enter light recovery mode
                if not self._recovery_mode:
                    self._recovery_mode = True
                    self._recovery_start_time = time.time()
                    self._recovery_level = 1  # Light recovery
                
                reason = (f"Low success rate ({success_rate:.1%}), reducing workers from {prev_target} to "
                         f"{self.target_workers} and increasing delay to {self.current_delay:.1f}s")
            
            # Update adjustment time and stats
            self.last_adjustment_time = time.time()
            self.stats['adjustments_made'] += 1
            self.stats['last_adjustment_reason'] = reason
            
            # Check if we actually changed settings
            changed = (original_workers != self.target_workers or 
                       abs(original_delay - self.current_delay) > 0.1)
                       
            return changed, self.target_workers, self.current_delay, reason
    
    def get_current_settings(self):
        """
        Get the current crawl rate settings.
        
        Returns:
            dict: Current settings including worker count and delay
        """
        with self.lock:
            return {
                'target_workers': self.target_workers,
                'current_delay': self.current_delay,
                'in_recovery_mode': self._recovery_mode,
                'recovery_level': self._recovery_level,
                'throttling_active': self._throttling_active
            }
    
    def get_statistics(self):
        """
        Get the current statistics.
        
        Returns:
            dict: Current statistics about requests and adjustments
        """
        with self.lock:
            stats = self.stats.copy()
            
            # Add derived statistics
            total = max(1, stats['total_requests'])
            stats['success_rate'] = stats['successful_requests'] / total
            stats['rate_limited_rate'] = stats['rate_limited_requests'] / total
            stats['error_rate'] = (stats['server_errors'] + stats['client_errors']) / total
            
            # Add current settings
            stats.update(self.get_current_settings())
            
            # Add status information
            stats['consecutive_successes'] = self._consecutive_successes
            stats['consecutive_failures'] = self._consecutive_failures
            
            if self._recovery_mode and self._recovery_start_time:
                stats['recovery_time'] = time.time() - self._recovery_start_time
            
            # Add cooldown information
            if self._last_rate_limit_action:
                cooldown_elapsed = time.time() - self._last_rate_limit_action
                stats['cooldown_elapsed'] = cooldown_elapsed
                stats['cooldown_remaining'] = max(0, self._rate_limit_cooldown - cooldown_elapsed)
            
            return stats
    
    def from_checkpoint(self, checkpoint_data):
        """
        Restore rate controller state from checkpoint data.
        
        Args:
            checkpoint_data: Dictionary containing saved state
            
        Returns:
            bool: True if state was successfully restored
        """
        with self.lock:
            try:
                if 'target_workers' in checkpoint_data:
                    self.target_workers = max(
                        self.min_workers, 
                        min(self.max_workers, checkpoint_data['target_workers'])
                    )
                
                if 'current_delay' in checkpoint_data:
                    self.current_delay = max(
                        self.min_delay, 
                        min(self.max_delay, checkpoint_data['current_delay'])
                    )
                
                # Restore recovery mode state
                if 'in_recovery_mode' in checkpoint_data:
                    self._recovery_mode = checkpoint_data['in_recovery_mode']
                
                if 'throttling_active' in checkpoint_data:
                    self._throttling_active = checkpoint_data['throttling_active']
                
                if 'recovery_level' in checkpoint_data:
                    self._recovery_level = checkpoint_data['recovery_level']
                else:
                    # Default to mild recovery level if not specified
                    self._recovery_level = 1
                
                # Always restart recovery timer
                self._recovery_start_time = time.time()
                
                # Start with 0 consecutive successes/failures
                self._consecutive_successes = 0
                self._consecutive_failures = 0
                
                # Reset rate limit cooldown
                self._last_rate_limit_action = None
                
                # If restoring from a checkpoint during active throttling,
                # be more conservative initially
                if self._throttling_active:
                    self.current_delay = min(self.max_delay, self.current_delay * 1.2)
                    self.target_workers = max(
                        self.min_workers,
                        self.target_workers - 1
                    )
                
                # Restore stats if available
                if 'stats' in checkpoint_data:
                    saved_stats = checkpoint_data['stats']
                    # Only copy valid keys to avoid corruption
                    for key in self.stats.keys():
                        if key in saved_stats:
                            self.stats[key] = saved_stats[key]
                
                print(f"Restored rate controller from checkpoint: "
                      f"{self.target_workers} workers, {self.current_delay:.1f}s delay "
                      f"(recovery mode: {'Yes' if self._recovery_mode else 'No'}, "
                      f"level: {self._recovery_level})")
                return True
                
            except Exception as e:
                print(f"Error restoring rate controller state: {e}")
                return False
    
    def to_checkpoint(self):
        """
        Generate checkpoint data for saving.
        
        Returns:
            dict: Rate controller state for checkpoint
        """
        with self.lock:
            return {
                'target_workers': self.target_workers,
                'current_delay': self.current_delay,
                'last_adjustment_time': self.last_adjustment_time,
                'last_adjustment_reason': self.stats['last_adjustment_reason'],
                'in_recovery_mode': self._recovery_mode,
                'throttling_active': self._throttling_active,
                'recovery_level': self._recovery_level,
                'stats': self.stats.copy()
            }
