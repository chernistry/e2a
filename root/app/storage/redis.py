# ==== REDIS CLIENT FOR CACHING AND SESSION MANAGEMENT ==== #

"""
Redis client for caching and session management in Octup E²A.

This module provides comprehensive Redis connectivity with SSL support,
circuit breaker protection, connection pooling, and health monitoring
for reliable caching and session management operations.
"""

from typing import Optional

import redis.asyncio as redis

from app.settings import settings
from app.resilience.decorators import redis_resilient
from app.resilience.circuit_breaker import CircuitBreakerError


# ==== GLOBAL CLIENT INSTANCE ==== #

_redis_client: Optional[redis.Redis] = None


# ==== REDIS CLIENT FUNCTIONS ==== #

@redis_resilient("get_redis_client")
async def get_redis_client() -> redis.Redis:
    """
    Get Redis client instance with SSL and connection management.
    
    Provides comprehensive Redis client with SSL configuration for cloud
    deployments, connection pooling, health monitoring, and circuit breaker
    protection for reliable caching operations.
    
    Returns:
        redis.Redis: Redis client instance with full configuration
        
    Raises:
        CircuitBreakerError: If Redis circuit breaker is open
        redis.ConnectionError: If Redis connection fails
    """
    global _redis_client
    
    if _redis_client is None:
        # --► SSL CONFIGURATION FOR REDIS CLOUD
        ssl_config = {}
        if settings.REDIS_URL.startswith('rediss://'):
            ssl_config = {
                'ssl_cert_reqs': None,
                'ssl_check_hostname': False,
                'ssl_ca_certs': None
            }
        
        # --► CLIENT INITIALIZATION WITH COMPREHENSIVE CONFIG
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
            socket_keepalive_options={},
            health_check_interval=30,
            **ssl_config
        )
        
        # --► CONNECTION VALIDATION
        await _redis_client.ping()
    
    return _redis_client


async def close_redis_client() -> None:
    """
    Close Redis client connection and cleanup resources.
    
    Properly closes the Redis connection and resets the global client
    instance for clean shutdown and resource management.
    """
    global _redis_client
    
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
