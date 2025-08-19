"""Retry policies for different types of operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    wait_random_exponential,
    retry_if_exception_type
)
import httpx
import redis.asyncio as redis
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError, TimeoutError as SQLTimeoutError

# Handle both psycopg and psycopg-binary installations
try:
    from psycopg import OperationalError as PsycopgOperationalError
except ImportError:
    try:
        from psycopg2 import OperationalError as PsycopgOperationalError
    except ImportError:
        # Fallback to SQLAlchemy's generic error if neither is available
        PsycopgOperationalError = SQLAlchemyError

from app.observability.tracing import get_tracer
from app.observability.metrics import Counter

tracer = get_tracer(__name__)

# Metrics
retry_attempts_total = Counter(
    "octup_retry_attempts_total",
    "Total retry attempts",
    ["service", "operation", "attempt"]
)

retry_failures_total = Counter(
    "octup_retry_failures_total",
    "Total retry failures after all attempts",
    ["service", "operation", "error_type"]
)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    timeout: Optional[float] = None


class RetryPolicy(ABC):
    """Abstract base class for retry policies."""
    
    def __init__(self, config: RetryConfig, service_name: str = "unknown"):
        self.config = config
        self.service_name = service_name
    
    @abstractmethod
    def get_tenacity_decorator(self, operation_name: str = "unknown"):
        """Get tenacity decorator for this policy."""
        pass
    
    def should_retry(self, exception: Exception) -> bool:
        """Determine if exception should trigger retry."""
        return True


class ExponentialBackoffPolicy(RetryPolicy):
    """Exponential backoff retry policy."""
    
    def __init__(
        self, 
        config: RetryConfig,
        service_name: str = "unknown",
        retryable_exceptions: tuple = (Exception,)
    ):
        super().__init__(config, service_name)
        self.retryable_exceptions = retryable_exceptions
    
    def get_tenacity_decorator(self, operation_name: str = "unknown"):
        """Get tenacity decorator with exponential backoff."""
        wait_strategy = wait_exponential(
            multiplier=self.config.base_delay,
            max=self.config.max_delay,
            exp_base=self.config.exponential_base
        )
        
        if self.config.jitter:
            wait_strategy = wait_random_exponential(
                multiplier=self.config.base_delay,
                max=self.config.max_delay
            )
        
        return retry(
            stop=stop_after_attempt(self.config.max_attempts),
            wait=wait_strategy,
            retry=retry_if_exception_type(self.retryable_exceptions),
            before_sleep=self._before_sleep_callback(operation_name),
            after=self._after_callback(operation_name)
        )
    
    def _before_sleep_callback(self, operation_name: str):
        """Callback before sleep between retries."""
        def callback(retry_state):
            attempt = retry_state.attempt_number
            retry_attempts_total.labels(
                service=self.service_name,
                operation=operation_name,
                attempt=str(attempt)
            ).inc()
            
            with tracer.start_as_current_span("retry_attempt") as span:
                span.set_attribute("service", self.service_name)
                span.set_attribute("operation", operation_name)
                span.set_attribute("attempt", attempt)
                span.set_attribute("exception", str(retry_state.outcome.exception()))
        
        return callback
    
    def _after_callback(self, operation_name: str):
        """Callback after all retry attempts."""
        def callback(retry_state):
            if retry_state.outcome.failed:
                exception = retry_state.outcome.exception()
                retry_failures_total.labels(
                    service=self.service_name,
                    operation=operation_name,
                    error_type=type(exception).__name__
                ).inc()
        
        return callback


class FixedDelayPolicy(RetryPolicy):
    """Fixed delay retry policy."""
    
    def __init__(
        self,
        config: RetryConfig,
        service_name: str = "unknown", 
        retryable_exceptions: tuple = (Exception,)
    ):
        super().__init__(config, service_name)
        self.retryable_exceptions = retryable_exceptions
    
    def get_tenacity_decorator(self, operation_name: str = "unknown"):
        """Get tenacity decorator with fixed delay."""
        wait_strategy = wait_fixed(self.config.base_delay)
        
        if self.config.jitter:
            # Add jitter to fixed delay
            wait_strategy = wait_fixed(self.config.base_delay) + wait_random_exponential(
                multiplier=0.1, max=self.config.base_delay * 0.5
            )
        
        return retry(
            stop=stop_after_attempt(self.config.max_attempts),
            wait=wait_strategy,
            retry=retry_if_exception_type(self.retryable_exceptions),
            before_sleep=self._before_sleep_callback(operation_name),
            after=self._after_callback(operation_name)
        )
    
    def _before_sleep_callback(self, operation_name: str):
        """Callback before sleep between retries."""
        def callback(retry_state):
            attempt = retry_state.attempt_number
            retry_attempts_total.labels(
                service=self.service_name,
                operation=operation_name,
                attempt=str(attempt)
            ).inc()
        
        return callback
    
    def _after_callback(self, operation_name: str):
        """Callback after all retry attempts."""
        def callback(retry_state):
            if retry_state.outcome.failed:
                exception = retry_state.outcome.exception()
                retry_failures_total.labels(
                    service=self.service_name,
                    operation=operation_name,
                    error_type=type(exception).__name__
                ).inc()
        
        return callback


# Predefined retry policies for common services

def create_ai_retry_policy() -> ExponentialBackoffPolicy:
    """Create retry policy for AI service calls."""
    config = RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        max_delay=10.0,
        exponential_base=2.0,
        jitter=True,
        timeout=30.0
    )
    
    retryable_exceptions = (
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        ConnectionError,
        TimeoutError
    )
    
    return ExponentialBackoffPolicy(
        config=config,
        service_name="ai_service",
        retryable_exceptions=retryable_exceptions
    )


def create_database_retry_policy() -> ExponentialBackoffPolicy:
    """Create retry policy for database operations."""
    config = RetryConfig(
        max_attempts=3,
        base_delay=0.1,
        max_delay=5.0,
        exponential_base=2.0,
        jitter=True,
        timeout=10.0
    )
    
    retryable_exceptions = (
        DisconnectionError,
        SQLTimeoutError,
        PsycopgOperationalError,
        ConnectionError,
        OSError  # Network-related errors
    )
    
    return ExponentialBackoffPolicy(
        config=config,
        service_name="database",
        retryable_exceptions=retryable_exceptions
    )


def create_redis_retry_policy() -> ExponentialBackoffPolicy:
    """Create retry policy for Redis operations."""
    config = RetryConfig(
        max_attempts=3,
        base_delay=0.1,
        max_delay=2.0,
        exponential_base=2.0,
        jitter=True,
        timeout=5.0
    )
    
    retryable_exceptions = (
        redis.ConnectionError,
        redis.TimeoutError,
        redis.BusyLoadingError,
        ConnectionError,
        TimeoutError,
        OSError
    )
    
    return ExponentialBackoffPolicy(
        config=config,
        service_name="redis",
        retryable_exceptions=retryable_exceptions
    )


def create_http_retry_policy() -> ExponentialBackoffPolicy:
    """Create retry policy for HTTP client operations."""
    config = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
        timeout=30.0
    )
    
    retryable_exceptions = (
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        httpx.HTTPStatusError,  # For 5xx errors
        ConnectionError,
        TimeoutError
    )
    
    return ExponentialBackoffPolicy(
        config=config,
        service_name="http_client",
        retryable_exceptions=retryable_exceptions
    )


def create_observability_retry_policy() -> FixedDelayPolicy:
    """Create retry policy for observability exports (less aggressive)."""
    config = RetryConfig(
        max_attempts=2,  # Don't retry too much for observability
        base_delay=1.0,
        max_delay=5.0,
        jitter=True,
        timeout=10.0
    )
    
    retryable_exceptions = (
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.ConnectError,
        ConnectionError,
        TimeoutError
    )
    
    return FixedDelayPolicy(
        config=config,
        service_name="observability",
        retryable_exceptions=retryable_exceptions
    )


# Utility functions for custom retry logic

async def retry_async_operation(
    operation: Callable,
    policy: RetryPolicy,
    operation_name: str = "unknown",
    *args,
    **kwargs
) -> Any:
    """Retry async operation with given policy.
    
    Args:
        operation: Async function to retry
        policy: Retry policy to use
        operation_name: Name for metrics/logging
        *args: Operation arguments
        **kwargs: Operation keyword arguments
        
    Returns:
        Operation result
        
    Raises:
        Exception: Last exception if all retries failed
    """
    decorator = policy.get_tenacity_decorator(operation_name)
    decorated_operation = decorator(operation)
    
    return await decorated_operation(*args, **kwargs)


def retry_sync_operation(
    operation: Callable,
    policy: RetryPolicy,
    operation_name: str = "unknown",
    *args,
    **kwargs
) -> Any:
    """Retry sync operation with given policy.
    
    Args:
        operation: Sync function to retry
        policy: Retry policy to use
        operation_name: Name for metrics/logging
        *args: Operation arguments
        **kwargs: Operation keyword arguments
        
    Returns:
        Operation result
        
    Raises:
        Exception: Last exception if all retries failed
    """
    decorator = policy.get_tenacity_decorator(operation_name)
    decorated_operation = decorator(operation)
    
    return decorated_operation(*args, **kwargs)
