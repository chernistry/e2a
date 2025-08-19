"""
Rate limiter implementation using sliding window algorithm.

Prevents system overload by limiting requests per time window.
"""

import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, Deque, Tuple


class RateLimiter:
    """
    Sliding window rate limiter.
    
    Uses a sliding window approach to track requests over time,
    providing smooth rate limiting without burst allowances.
    """
    
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        
        # Track requests per key (tenant, endpoint, etc.)
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
    
    async def allow_request(self, key: str) -> bool:
        """
        Check if request is allowed for the given key.
        
        Args:
            key: Identifier for rate limiting (e.g., tenant_id, user_id)
            
        Returns:
            True if request is allowed, False if rate limited
        """
        async with self._lock:
            current_time = time.time()
            request_times = self._requests[key]
            
            # Remove old requests outside the window
            while request_times and current_time - request_times[0] > self.window_seconds:
                request_times.popleft()
            
            # Check if we're under the limit
            if len(request_times) < self.max_requests:
                request_times.append(current_time)
                return True
            
            return False
    
    async def get_remaining_requests(self, key: str) -> int:
        """Get number of remaining requests for the key."""
        async with self._lock:
            current_time = time.time()
            request_times = self._requests[key]
            
            # Remove old requests
            while request_times and current_time - request_times[0] > self.window_seconds:
                request_times.popleft()
            
            return max(0, self.max_requests - len(request_times))
    
    async def get_reset_time(self, key: str) -> float:
        """Get time when rate limit resets for the key."""
        async with self._lock:
            request_times = self._requests[key]
            if not request_times:
                return 0.0
            
            return request_times[0] + self.window_seconds
    
    async def clear_key(self, key: str):
        """Clear rate limit data for a specific key."""
        async with self._lock:
            if key in self._requests:
                del self._requests[key]
    
    async def get_stats(self) -> Dict[str, any]:
        """Get rate limiter statistics."""
        async with self._lock:
            current_time = time.time()
            active_keys = 0
            total_requests = 0
            
            for key, request_times in self._requests.items():
                # Clean old requests
                while request_times and current_time - request_times[0] > self.window_seconds:
                    request_times.popleft()
                
                if request_times:
                    active_keys += 1
                    total_requests += len(request_times)
            
            return {
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
                "active_keys": active_keys,
                "total_active_requests": total_requests
            }


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter for burst handling.
    
    Allows bursts up to bucket capacity while maintaining
    average rate over time.
    """
    
    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # tokens per second
        self.capacity = capacity  # max tokens in bucket
        
        self._buckets: Dict[str, Tuple[float, float]] = {}  # key -> (tokens, last_update)
        self._lock = asyncio.Lock()
    
    async def allow_request(self, key: str, tokens_required: int = 1) -> bool:
        """Check if request is allowed and consume tokens."""
        async with self._lock:
            current_time = time.time()
            
            if key not in self._buckets:
                self._buckets[key] = (self.capacity, current_time)
            
            tokens, last_update = self._buckets[key]
            
            # Add tokens based on elapsed time
            elapsed = current_time - last_update
            tokens = min(self.capacity, tokens + elapsed * self.rate)
            
            if tokens >= tokens_required:
                tokens -= tokens_required
                self._buckets[key] = (tokens, current_time)
                return True
            else:
                self._buckets[key] = (tokens, current_time)
                return False
    
    async def get_available_tokens(self, key: str) -> float:
        """Get number of available tokens for the key."""
        async with self._lock:
            current_time = time.time()
            
            if key not in self._buckets:
                return self.capacity
            
            tokens, last_update = self._buckets[key]
            elapsed = current_time - last_update
            tokens = min(self.capacity, tokens + elapsed * self.rate)
            
            return tokens
