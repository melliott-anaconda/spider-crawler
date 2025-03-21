#!/usr/bin/env python3
"""
HTTP response handling module.

This module contains functions for processing HTTP status codes
and determining appropriate handling strategies.
"""


def handle_response_code(url, response_code):
    """
    Determine if a response code indicates success or failure and provides appropriate handling recommendations.
    
    Args:
        url: The URL that was accessed
        response_code: The HTTP status code (int or None)
        
    Returns:
        dict: A dictionary with handling information including:
            - 'success': Boolean indicating if the response is successful
            - 'action': String indicating the recommended action ('process', 'retry', 'skip', etc.)
            - 'reason': String explaining the reason for the action
            - 'retry_after': Suggested delay before retry (None if not applicable)
            - 'rate_limited': Boolean indicating if this appears to be a rate limiting response
    """
    # Handle None or invalid response codes
    if response_code is None or not isinstance(response_code, int):
        # If we got a page but couldn't detect the status code, assume it's 200
        return {
            'success': True,
            'action': 'process',
            'reason': f"Undetected status code (assuming success)",
            'retry_after': None,
            'rate_limited': False
        }
    
    # Successful responses (2xx)
    if 200 <= response_code < 300:
        return {
            'success': True,
            'action': 'process',
            'reason': f"Successful response ({response_code})",
            'retry_after': None,
            'rate_limited': False
        }
    
    # Redirects (3xx) - handled by the browser, but log for completeness
    elif 300 <= response_code < 400:
        return {
            'success': True,  # Consider redirects as success since browser follows them
            'action': 'process',
            'reason': f"Redirect ({response_code})",
            'retry_after': None,
            'rate_limited': False
        }
    
    # Client errors (4xx)
    elif 400 <= response_code < 500:
        # Check for explicit rate limiting (429)
        if response_code == 429:
            return {
                'success': False,
                'action': 'throttle_and_retry',
                'reason': f"Rate limited (429 Too Many Requests)",
                'retry_after': 60,  # Default to 60 seconds if no Retry-After header
                'rate_limited': True
            }
        # Check for other potential rate limiting indicators
        elif response_code == 403:  # Forbidden can sometimes be used for rate limiting
            return {
                'success': False,
                'action': 'throttle_and_retry',
                'reason': f"Possible rate limiting (403 Forbidden)",
                'retry_after': 30,
                'rate_limited': True  # Treat as rate limiting for caution
            }
        elif response_code == 430:  # Non-standard but sometimes used for rate limiting
            return {
                'success': False,
                'action': 'throttle_and_retry',
                'reason': f"Custom rate limiting (430)",
                'retry_after': 60,
                'rate_limited': True
            }
        elif response_code == 420:  # Twitter/X's rate limit code
            return {
                'success': False,
                'action': 'throttle_and_retry',
                'reason': f"Custom rate limiting (420)",
                'retry_after': 60,
                'rate_limited': True
            }
        # Handle authentication/authorization errors
        elif response_code == 401:
            return {
                'success': False,
                'action': 'skip',
                'reason': f"Authentication required (401)",
                'retry_after': None,
                'rate_limited': False
            }
        # Handle not found
        elif response_code == 404:
            return {
                'success': False,
                'action': 'skip',
                'reason': f"Page not found (404)",
                'retry_after': None,
                'rate_limited': False
            }
        # Handle other unusual 4xx codes that might indicate rate limiting
        elif response_code in [418, 423, 425, 429, 430, 439, 440, 449]:
            return {
                'success': False,
                'action': 'throttle_and_retry',
                'reason': f"Possible custom rate limiting ({response_code})",
                'retry_after': 45,
                'rate_limited': True
            }
        # Other client errors - may be worth a single retry
        else:
            return {
                'success': False,
                'action': 'retry_once',
                'reason': f"Client error ({response_code})",
                'retry_after': 10,
                'rate_limited': False
            }
    
    # Server errors (5xx)
    elif 500 <= response_code < 600:
        # Check for overload responses (503 Service Unavailable)
        if response_code == 503:
            return {
                'success': False,
                'action': 'throttle_and_retry',
                'reason': f"Server overloaded (503 Service Unavailable)",
                'retry_after': 45,
                'rate_limited': True  # Treat server overload as a form of rate limiting
            }
        # Handle other server errors
        else:
            return {
                'success': False,
                'action': 'retry',
                'reason': f"Server error ({response_code})",
                'retry_after': 30,
                'rate_limited': False
            }
    
    # Unknown status codes
    else:
        return {
            'success': False,
            'action': 'skip',
            'reason': f"Unknown status code ({response_code})",
            'retry_after': None,
            'rate_limited': False
        }


def extract_retry_after(response_headers):
    """
    Extract Retry-After value from response headers.
    
    Args:
        response_headers: Dictionary of HTTP response headers
        
    Returns:
        int: Retry-After value in seconds, or None if not present
    """
    retry_after = None
    
    # Check if headers dictionary is provided
    if not response_headers:
        return None
        
    # Look for Retry-After header (case-insensitive)
    for header, value in response_headers.items():
        if header.lower() == 'retry-after':
            try:
                # First try to parse as integer (seconds)
                retry_after = int(value)
            except ValueError:
                # If that fails, try to parse as HTTP date
                try:
                    import email.utils
                    import time
                    parsed_date = email.utils.parsedate(value)
                    if parsed_date:
                        retry_time = time.mktime(parsed_date)
                        current_time = time.time()
                        retry_after = int(retry_time - current_time)
                        # Ensure it's positive
                        retry_after = max(1, retry_after)
                except:
                    pass
            break
    
    return retry_after


def get_response_category(response_code):
    """
    Get the category of an HTTP response code.
    
    Args:
        response_code: HTTP status code
        
    Returns:
        str: Category name (informational, success, redirect, client_error, server_error, unknown)
    """
    if not isinstance(response_code, int):
        return 'unknown'
        
    if 100 <= response_code < 200:
        return 'informational'
    elif 200 <= response_code < 300:
        return 'success'
    elif 300 <= response_code < 400:
        return 'redirect'
    elif 400 <= response_code < 500:
        return 'client_error'
    elif 500 <= response_code < 600:
        return 'server_error'
    else:
        return 'unknown'


def is_rate_limited(response_code, response_headers=None, body_content=None):
    """
    Determine if a response indicates rate limiting.
    
    Args:
        response_code: HTTP status code
        response_headers: Optional dictionary of response headers
        body_content: Optional response body content
        
    Returns:
        bool: True if rate limiting is detected, False otherwise
    """
    # Explicit rate limit status codes
    if response_code in [429, 420, 430]:
        return True
        
    # Check headers for rate limit indicators
    if response_headers:
        rate_limit_headers = [
            'x-rate-limit-remaining', 'x-rate-limit-reset',
            'retry-after', 'x-ratelimit-remaining',
            'ratelimit-remaining', 'x-rate-limit-limit'
        ]
        
        for header in rate_limit_headers:
            if any(h.lower() == header for h in response_headers.keys()):
                # If any rate limit header is present with a zero or low value
                try:
                    header_value = next(v for k, v in response_headers.items() if k.lower() == header)
                    if header.endswith('remaining') and str(header_value).strip() in ['0', '1', '2']:
                        return True
                except:
                    pass
    
    # Check body content for rate limit indicators
    if body_content and isinstance(body_content, str):
        rate_limit_phrases = [
            'rate limit', 'rate limited', 'too many requests',
            'throttled', 'quota exceeded', 'usage limit',
            'limit exceeded', 'too frequent'
        ]
        
        body_lower = body_content.lower()
        if any(phrase in body_lower for phrase in rate_limit_phrases):
            return True
    
    # Some servers use 403 for rate limiting
    if response_code == 403 and (
        response_headers and any('limit' in k.lower() for k in response_headers.keys())
    ):
        return True
    
    return False


def should_retry(response_code, retry_count=0, max_retries=3):
    """
    Determine if a request should be retried based on the response code.
    
    Args:
        response_code: HTTP status code
        retry_count: Current retry count
        max_retries: Maximum number of retries
        
    Returns:
        bool: True if the request should be retried, False otherwise
    """
    # Don't retry if we've reached the maximum
    if retry_count >= max_retries:
        return False
    
    # Always retry rate limit responses
    if response_code == 429:
        return True
    
    # Retry server errors
    if 500 <= response_code < 600:
        return True
    
    # Retry some specific client errors
    if response_code in [408, 425, 449]:  # Request Timeout, Too Early, Retry With
        return True
    
    # Don't retry other client errors
    if 400 <= response_code < 500:
        return False
    
    # Don't retry success responses
    if 200 <= response_code < 400:
        return False
    
    # Default: don't retry
    return False
