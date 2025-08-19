"""Decorators for applying resilience patterns to functions."""

import asyncio
import functools
from typing import Callable, Optional, TypeVar

from .circuit_breaker import CircuitBreakerConfig, get_circuit_breaker
from .retry_policies import RetryPolicy, retry_async_operation, retry_sync_operation
from app.observability.tracing import get_tracer

tracer = get_tracer(__name__)

T = TypeVar('T')


def with_circuit_breaker(
    service_name: str,
    config: Optional[CircuitBreakerConfig] = None
):
    """Decorator to add circuit breaker protection to a function.
    
    Args:
        service_name: Name of the service for circuit breaker
        config: Optional circuit breaker configuration
        
    Returns:
        Decorated function with circuit breaker protection
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        circuit_breaker = get_circuit_breaker(service_name, config)
        
        # Check if it's an async context manager
        if hasattr(func, '__aenter__') and hasattr(func, '__aexit__'):
            # It's an async context manager, return it as-is
            # The circuit breaker will be applied at the session level
            return func
        elif asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                return await circuit_breaker.call(func, *args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                # For sync functions, check if we're already in an event loop
                try:
                    loop = asyncio.get_running_loop()
                    # We're in an async context, use create_task
                    import asyncio
                    task = asyncio.create_task(circuit_breaker.call(func, *args, **kwargs))
                    # This is a hack, but we need to handle this case
                    # In practice, this should be avoided by making everything async
                    return asyncio.run_coroutine_threadsafe(
                        circuit_breaker.call(func, *args, **kwargs), loop
                    ).result()
                except RuntimeError:
                    # No event loop running, safe to use run_until_complete
                    loop = asyncio.new_event_loop()
                    try:
                        return loop.run_until_complete(
                            circuit_breaker.call(func, *args, **kwargs)
                        )
                    finally:
                        loop.close()
            return sync_wrapper
    
    return decorator


def with_retry(
    policy: RetryPolicy,
    operation_name: Optional[str] = None
):
    """Decorator to add retry logic to a function.
    
    Args:
        policy: Retry policy to apply
        operation_name: Optional operation name for metrics
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op_name = operation_name or func.__name__
        
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                return await retry_async_operation(
                    func, policy, op_name, *args, **kwargs
                )
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                return retry_sync_operation(
                    func, policy, op_name, *args, **kwargs
                )
            return sync_wrapper
    
    return decorator


def with_resilience(
    service_name: str,
    retry_policy: RetryPolicy,
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    operation_name: Optional[str] = None
):
    """Decorator to add both retry and circuit breaker protection.
    
    Args:
        service_name: Name of the service
        retry_policy: Retry policy to apply
        circuit_breaker_config: Optional circuit breaker configuration
        operation_name: Optional operation name for metrics
        
    Returns:
        Decorated function with full resilience protection
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Apply retry first, then circuit breaker
        retry_decorated = with_retry(retry_policy, operation_name)(func)
        circuit_breaker_decorated = with_circuit_breaker(
            service_name, circuit_breaker_config
        )(retry_decorated)
        
        return circuit_breaker_decorated
    
    return decorator


def resilient_async(
    service_name: str,
    retry_policy: Optional[RetryPolicy] = None,
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    operation_name: Optional[str] = None
):
    """Decorator for async functions with default resilience patterns.
    
    Args:
        service_name: Name of the service
        retry_policy: Optional retry policy (uses default if None)
        circuit_breaker_config: Optional circuit breaker config
        operation_name: Optional operation name
        
    Returns:
        Decorated async function with resilience
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if not asyncio.iscoroutinefunction(func):
            raise ValueError("resilient_async can only be used with async functions")
        
        # Use default retry policy if none provided
        if retry_policy is None:
            from .retry_policies import create_http_retry_policy
            policy = create_http_retry_policy()
            policy.service_name = service_name
        else:
            policy = retry_policy
        
        return with_resilience(
            service_name, policy, circuit_breaker_config, operation_name
        )(func)
    
    return decorator


def resilient_sync(
    service_name: str,
    retry_policy: Optional[RetryPolicy] = None,
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    operation_name: Optional[str] = None
):
    """Decorator for sync functions with default resilience patterns.
    
    Args:
        service_name: Name of the service
        retry_policy: Optional retry policy (uses default if None)
        circuit_breaker_config: Optional circuit breaker config
        operation_name: Optional operation name
        
    Returns:
        Decorated sync function with resilience
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(func):
            raise ValueError("resilient_sync cannot be used with async functions")
        
        # Use default retry policy if none provided
        if retry_policy is None:
            from .retry_policies import create_http_retry_policy
            policy = create_http_retry_policy()
            policy.service_name = service_name
        else:
            policy = retry_policy
        
        return with_resilience(
            service_name, policy, circuit_breaker_config, operation_name
        )(func)
    
    return decorator


# Convenience decorators for common services

def ai_resilient(operation_name: Optional[str] = None):
    """Decorator for AI service calls with appropriate resilience."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        from .retry_policies import create_ai_retry_policy
        from .circuit_breaker import CircuitBreakerConfig
        
        policy = create_ai_retry_policy()
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30.0,
            success_threshold=2
        )
        
        return with_resilience("ai_service", policy, config, operation_name)(func)
    
    return decorator


def database_resilient(operation_name: Optional[str] = None):
    """Decorator for database operations with appropriate resilience."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        from .retry_policies import create_database_retry_policy
        from .circuit_breaker import CircuitBreakerConfig
        
        policy = create_database_retry_policy()
        config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=10.0,
            success_threshold=3
        )
        
        return with_resilience("database", policy, config, operation_name)(func)
    
    return decorator


def redis_resilient(operation_name: Optional[str] = None):
    """Decorator for Redis operations with appropriate resilience."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        from .retry_policies import create_redis_retry_policy
        from .circuit_breaker import CircuitBreakerConfig
        
        policy = create_redis_retry_policy()
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=5.0,
            success_threshold=2
        )
        
        return with_resilience("redis", policy, config, operation_name)(func)
    
    return decorator


def http_resilient(operation_name: Optional[str] = None):
    """Decorator for HTTP client calls with appropriate resilience."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        from .retry_policies import create_http_retry_policy
        from .circuit_breaker import CircuitBreakerConfig
        
        policy = create_http_retry_policy()
        config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=60.0,
            success_threshold=3
        )
        
        return with_resilience("http_client", policy, config, operation_name)(func)
    
    return decorator
