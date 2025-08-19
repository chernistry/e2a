"""
Resilience patterns for high-availability systems.

This module provides implementations of common resilience patterns:
- Circuit Breaker: Prevents cascading failures
- Rate Limiter: Controls request rate to prevent overload
- Retry: Automatic retry with exponential backoff
- Timeout: Request timeout handling
"""

from .circuit_breaker import (
    CircuitBreaker, 
    CircuitBreakerError, 
    CircuitState, 
    CircuitBreakerConfig, 
    get_circuit_breaker,
    get_all_circuit_breakers,
    reset_circuit_breaker,
    get_circuit_breaker_stats
)
from .rate_limiter import RateLimiter, TokenBucketRateLimiter

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerError", 
    "CircuitState",
    "CircuitBreakerConfig",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "reset_circuit_breaker", 
    "get_circuit_breaker_stats",
    "RateLimiter",
    "TokenBucketRateLimiter"
]
