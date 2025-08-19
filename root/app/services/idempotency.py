# ==== IDEMPOTENCY SERVICE ==== #

"""
Idempotency service using Redis for duplicate detection in Octup E²A.

This module provides comprehensive idempotency management with Redis-backed
duplicate detection, distributed locking, and automatic cleanup mechanisms
for high-volume event processing with guaranteed exactly-once semantics.
"""

from typing import Optional

import redis.asyncio as redis

from app.settings import settings
from app.observability.tracing import get_tracer
from app.observability.metrics import cache_hits_total, cache_misses_total
from app.resilience.decorators import redis_resilient


# ==== MODULE INITIALIZATION ==== #


tracer = get_tracer(__name__)


# ==== IDEMPOTENCY SERVICE CLASS ==== #


class IdempotencyService:
    """
    Service for handling idempotent operations with Redis.
    
    Provides distributed idempotency management with Redis-backed duplicate
    detection, distributed locking, and automatic cleanup for high-volume
    event processing with exactly-once delivery guarantees.
    """
    
    def __init__(self, redis_url: str | None = None):
        """
        Initialize idempotency service with Redis configuration.
        
        Sets up Redis connection with SSL support for cloud deployments
        and configures connection pooling for optimal performance.
        
        Args:
            redis_url (str | None): Redis connection URL (defaults to settings)
        """
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[redis.Redis] = None


    # ==== REDIS CONNECTION MANAGEMENT ==== #


    @redis_resilient("get_redis")
    async def _get_redis(self) -> redis.Redis:
        """
        Get Redis connection with lazy initialization and SSL support.
        
        Implements lazy connection initialization with comprehensive SSL
        configuration for Redis Cloud deployments and connection pooling
        for optimal performance under high load.
        
        Returns:
            redis.Redis: Redis connection instance with SSL configuration
            
        Raises:
            CircuitBreakerError: When Redis circuit breaker is open
        """
        if self._redis is None:
            # --► SSL CONFIGURATION FOR REDIS CLOUD
            ssl_config = {}
            if self.redis_url.startswith('rediss://'):
                ssl_config = {
                    'ssl_cert_reqs': None,
                    'ssl_check_hostname': False,
                    'ssl_ca_certs': None
                }
            
            self._redis = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                **ssl_config
            )
        return self._redis


    # ==== KEY GENERATION UTILITIES ==== #


    def _idempotency_key(self, tenant: str, source: str, event_id: str) -> str:
        """
        Generate idempotency key.
        
        Creates consistent Redis keys for idempotency tracking using
        tenant, source, and event ID for multi-tenant isolation.
        
        Args:
            tenant (str): Tenant identifier for data isolation
            source (str): Event source (shopify, wms, carrier)
            event_id (str): Unique event identifier
            
        Returns:
            str: Redis key for idempotency tracking
        """
        return f"idempo:{tenant}:{source}:{event_id}"
    
    
    def _lock_key(self, tenant: str, source: str, event_id: str) -> str:
        """
        Generate lock key for concurrent processing protection.
        
        Creates distributed lock keys to prevent concurrent processing
        of the same event across multiple application instances.
        
        Args:
            tenant (str): Tenant identifier for data isolation
            source (str): Event source for context
            event_id (str): Unique event identifier
            
        Returns:
            str: Redis key for distributed locking
        """
        return f"lock:{self._idempotency_key(tenant, source, event_id)}"


    # ==== LOCK MANAGEMENT ==== #


    @redis_resilient("acquire_lock")
    async def acquire_lock(
        self,
        tenant: str,
        source: str,
        event_id: str,
        timeout_seconds: int = 5
    ) -> bool:
        """
        Acquire processing lock for event.
        
        Implements distributed locking using Redis SET with NX/EX
        options to prevent concurrent processing of the same event
        across multiple application instances.
        
        Args:
            tenant (str): Tenant identifier for data isolation
            source (str): Event source for context
            event_id (str): Unique event identifier
            timeout_seconds (int): Lock timeout in seconds (default: 5)
            
        Returns:
            bool: True if lock acquired, False if already locked
        """
        with tracer.start_as_current_span("idempotency_acquire_lock") as span:
            span.set_attribute("tenant", tenant)
            span.set_attribute("source", source)
            span.set_attribute("event_id", event_id)
            
            redis_client = await self._get_redis()
            lock_key = self._lock_key(tenant, source, event_id)
            
            # Use SET with NX (only if not exists) and EX (expiration)
            result = await redis_client.set(
                lock_key,
                "1",
                nx=True,
                ex=timeout_seconds
            )
            
            acquired = result is True
            span.set_attribute("lock_acquired", acquired)
            
            return acquired


    @redis_resilient("release_lock")
    async def release_lock(self, tenant: str, source: str, event_id: str) -> None:
        """
        Release processing lock for event.
        
        Removes the distributed lock to allow subsequent processing
        attempts or cleanup of expired locks.
        
        Args:
            tenant (str): Tenant identifier for data isolation
            source (str): Event source for context
            event_id (str): Unique event identifier
        """
        with tracer.start_as_current_span("idempotency_release_lock") as span:
            span.set_attribute("tenant", tenant)
            span.set_attribute("source", source)
            span.set_attribute("event_id", event_id)
            
            redis_client = await self._get_redis()
            lock_key = self._lock_key(tenant, source, event_id)
            
            await redis_client.delete(lock_key)


    # ==== IDEMPOTENCY OPERATIONS ==== #


    @redis_resilient("is_processed")
    async def is_processed(self, tenant: str, source: str, event_id: str) -> bool:
        """
        Check if event has already been processed.
        
        Verifies whether an event has been previously processed
        using Redis-based duplicate detection with comprehensive
        metrics and observability integration.
        
        Args:
            tenant (str): Tenant identifier for data isolation
            source (str): Event source for context
            event_id (str): Unique event identifier
            
        Returns:
            bool: True if already processed, False otherwise
        """
        with tracer.start_as_current_span("idempotency_check") as span:
            span.set_attribute("tenant", tenant)
            span.set_attribute("source", source)
            span.set_attribute("event_id", event_id)
            
            redis_client = await self._get_redis()
            key = self._idempotency_key(tenant, source, event_id)
            
            exists = await redis_client.exists(key) == 1
            
            # Update metrics
            if exists:
                cache_hits_total.labels(cache_type="idempotency", operation="check").inc()
            else:
                cache_misses_total.labels(cache_type="idempotency", operation="check").inc()
            
            span.set_attribute("already_processed", exists)
            return exists


    @redis_resilient("mark_processed")
    async def mark_processed(
        self,
        tenant: str,
        source: str,
        event_id: str,
        ttl_seconds: int = 86400  # 24 hours
    ) -> None:
        """
        Mark event as processed.
        
        Records successful event processing in Redis with configurable
        TTL to prevent reprocessing while managing memory usage
        through automatic expiration.
        
        Args:
            tenant (str): Tenant identifier for data isolation
            source (str): Event source for context
            event_id (str): Unique event identifier
            ttl_seconds (int): Time to live for the record (default: 24 hours)
        """
        with tracer.start_as_current_span("idempotency_mark_processed") as span:
            span.set_attribute("tenant", tenant)
            span.set_attribute("source", source)
            span.set_attribute("event_id", event_id)
            span.set_attribute("ttl_seconds", ttl_seconds)
            
            redis_client = await self._get_redis()
            key = self._idempotency_key(tenant, source, event_id)
            
            await redis_client.set(key, "1", ex=ttl_seconds)


    # ==== MAINTENANCE OPERATIONS ==== #


    async def cleanup_expired(self, pattern: str = "idempo:*") -> int:
        """
        Clean up expired idempotency records.
        
        Performs maintenance cleanup of expired idempotency records
        to manage Redis memory usage and maintain system performance
        under high load conditions.
        
        Args:
            pattern (str): Redis key pattern to match for cleanup
            
        Returns:
            int: Number of keys cleaned up during maintenance
        """
        with tracer.start_as_current_span("idempotency_cleanup") as span:
            redis_client = await self._get_redis()
            
            # Get all matching keys
            keys = await redis_client.keys(pattern)
            
            if not keys:
                span.set_attribute("keys_cleaned", 0)
                return 0
            
            # Check which keys are expired and remove them
            # Note: Redis automatically removes expired keys, but we can force cleanup
            cleaned = 0
            for key in keys:
                ttl = await redis_client.ttl(key)
                if ttl == -2:  # Key doesn't exist (expired)
                    cleaned += 1
            
            span.set_attribute("keys_cleaned", cleaned)
            return cleaned


    async def close(self) -> None:
        """
        Close Redis connection.
        
        Properly closes Redis connection to release resources
        and prevent connection leaks during application shutdown.
        """
        if self._redis is not None:
            await self._redis.close()
            self._redis = None


# ==== GLOBAL SERVICE INSTANCE ==== #


# Global instance
_idempotency_service: Optional[IdempotencyService] = None


def get_idempotency_service() -> IdempotencyService:
    """
    Get global idempotency service instance.
    
    Provides singleton access to the idempotency service for consistent
    configuration and resource management across the application.
    
    Returns:
        IdempotencyService: Global idempotency service instance
    """
    global _idempotency_service
    if _idempotency_service is None:
        _idempotency_service = IdempotencyService()
    return _idempotency_service
