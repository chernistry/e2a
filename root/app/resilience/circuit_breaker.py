"""Circuit breaker implementation for preventing cascading failures."""

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional, TypeVar, Union
from dataclasses import dataclass, field

from app.observability.tracing import get_tracer
from app.observability.metrics import Counter, Gauge

tracer = get_tracer(__name__)

# Metrics
circuit_breaker_state_changes = Counter(
    "octup_circuit_breaker_state_changes_total",
    "Total circuit breaker state changes",
    ["service", "from_state", "to_state"]
)

circuit_breaker_requests = Counter(
    "octup_circuit_breaker_requests_total", 
    "Total requests through circuit breaker",
    ["service", "state", "result"]
)

circuit_breaker_open_duration = Gauge(
    "octup_circuit_breaker_open_duration_seconds",
    "Duration circuit breaker has been open",
    ["service"]
)

T = TypeVar('T')


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    
    def __init__(self, service_name: str, message: str = None):
        self.service_name = service_name
        self.message = message or f"Circuit breaker is open for service: {service_name}"
        super().__init__(self.message)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Number of failures to open circuit
    recovery_timeout: float = 60.0  # Seconds to wait before trying half-open
    success_threshold: int = 3  # Successful calls needed to close circuit
    timeout: float = 30.0  # Request timeout in seconds
    expected_exceptions: tuple = (Exception,)  # Exceptions that count as failures


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    state: CircuitBreakerState
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    state_changed_at: float = field(default_factory=time.time)


class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures."""
    
    def __init__(self, service_name: str, config: CircuitBreakerConfig = None):
        """Initialize circuit breaker.
        
        Args:
            service_name: Name of the service being protected
            config: Circuit breaker configuration
        """
        self.service_name = service_name
        self.config = config or CircuitBreakerConfig()
        self.stats = CircuitBreakerStats(state=CircuitBreakerState.CLOSED)
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Original function exceptions
        """
        async with self._lock:
            await self._update_state()
            
            if self.stats.state == CircuitBreakerState.OPEN:
                circuit_breaker_requests.labels(
                    service=self.service_name,
                    state="open", 
                    result="rejected"
                ).inc()
                raise CircuitBreakerError(self.service_name)
        
        # Execute the function
        start_time = time.time()
        
        with tracer.start_as_current_span("circuit_breaker_call") as span:
            span.set_attribute("service", self.service_name)
            span.set_attribute("state", self.stats.state.value)
            
            try:
                # Apply timeout if function is async
                if asyncio.iscoroutinefunction(func):
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=self.config.timeout
                    )
                else:
                    result = func(*args, **kwargs)
                
                # Record success
                await self._record_success()
                
                circuit_breaker_requests.labels(
                    service=self.service_name,
                    state=self.stats.state.value,
                    result="success"
                ).inc()
                
                span.set_attribute("result", "success")
                return result
                
            except self.config.expected_exceptions as e:
                # Record failure
                await self._record_failure()
                
                circuit_breaker_requests.labels(
                    service=self.service_name,
                    state=self.stats.state.value,
                    result="failure"
                ).inc()
                
                span.set_attribute("result", "failure")
                span.set_attribute("error", str(e))
                raise
            
            except asyncio.TimeoutError:
                # Timeout counts as failure
                await self._record_failure()
                
                circuit_breaker_requests.labels(
                    service=self.service_name,
                    state=self.stats.state.value,
                    result="timeout"
                ).inc()
                
                span.set_attribute("result", "timeout")
                raise
    
    async def _update_state(self) -> None:
        """Update circuit breaker state based on current conditions."""
        current_time = time.time()
        old_state = self.stats.state
        
        if self.stats.state == CircuitBreakerState.CLOSED:
            # Check if we should open due to failures
            if self.stats.failure_count >= self.config.failure_threshold:
                await self._change_state(CircuitBreakerState.OPEN)
                
        elif self.stats.state == CircuitBreakerState.OPEN:
            # Check if we should try half-open
            if (self.stats.last_failure_time and 
                current_time - self.stats.last_failure_time >= self.config.recovery_timeout):
                await self._change_state(CircuitBreakerState.HALF_OPEN)
                
        elif self.stats.state == CircuitBreakerState.HALF_OPEN:
            # Check if we should close due to successes
            if self.stats.success_count >= self.config.success_threshold:
                await self._change_state(CircuitBreakerState.CLOSED)
            # Check if we should open due to failure
            elif self.stats.failure_count > 0:
                await self._change_state(CircuitBreakerState.OPEN)
    
    async def _change_state(self, new_state: CircuitBreakerState) -> None:
        """Change circuit breaker state.
        
        Args:
            new_state: New state to transition to
        """
        old_state = self.stats.state
        self.stats.state = new_state
        self.stats.state_changed_at = time.time()
        
        # Reset counters on state change
        if new_state == CircuitBreakerState.CLOSED:
            self.stats.failure_count = 0
            self.stats.success_count = 0
        elif new_state == CircuitBreakerState.HALF_OPEN:
            self.stats.failure_count = 0
            self.stats.success_count = 0
        
        # Update metrics
        circuit_breaker_state_changes.labels(
            service=self.service_name,
            from_state=old_state.value,
            to_state=new_state.value
        ).inc()
        
        if new_state == CircuitBreakerState.OPEN:
            circuit_breaker_open_duration.labels(
                service=self.service_name
            ).set_to_current_time()
    
    async def _record_success(self) -> None:
        """Record successful operation."""
        self.stats.success_count += 1
        self.stats.total_successes += 1
        self.stats.total_requests += 1
        self.stats.last_success_time = time.time()
        
        # Reset failure count on success in closed state
        if self.stats.state == CircuitBreakerState.CLOSED:
            self.stats.failure_count = 0
    
    async def _record_failure(self) -> None:
        """Record failed operation."""
        self.stats.failure_count += 1
        self.stats.total_failures += 1
        self.stats.total_requests += 1
        self.stats.last_failure_time = time.time()
        
        # Reset success count on failure in half-open state
        if self.stats.state == CircuitBreakerState.HALF_OPEN:
            self.stats.success_count = 0
    
    def get_stats(self) -> CircuitBreakerStats:
        """Get current circuit breaker statistics.
        
        Returns:
            Current statistics
        """
        return self.stats
    
    def is_closed(self) -> bool:
        """Check if circuit breaker is closed (normal operation).
        
        Returns:
            True if circuit is closed
        """
        return self.stats.state == CircuitBreakerState.CLOSED
    
    def is_open(self) -> bool:
        """Check if circuit breaker is open (failing).
        
        Returns:
            True if circuit is open
        """
        return self.stats.state == CircuitBreakerState.OPEN
    
    def is_half_open(self) -> bool:
        """Check if circuit breaker is half-open (testing).
        
        Returns:
            True if circuit is half-open
        """
        return self.stats.state == CircuitBreakerState.HALF_OPEN


# Global circuit breakers for common services
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(service_name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
    """Get or create circuit breaker for service.
    
    Args:
        service_name: Name of the service
        config: Optional configuration
        
    Returns:
        Circuit breaker instance
    """
    if service_name not in _circuit_breakers:
        _circuit_breakers[service_name] = CircuitBreaker(service_name, config)
    return _circuit_breakers[service_name]


def reset_circuit_breaker(service_name: str) -> None:
    """Reset circuit breaker to closed state.
    
    Args:
        service_name: Name of the service
    """
    if service_name in _circuit_breakers:
        cb = _circuit_breakers[service_name]
        cb.stats = CircuitBreakerStats(state=CircuitBreakerState.CLOSED)


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Get all registered circuit breakers.
    
    Returns:
        Dictionary of service name to circuit breaker
    """
    return _circuit_breakers.copy()
