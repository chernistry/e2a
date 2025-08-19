"""Health checking for external services."""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Callable, Any

import httpx
import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.tracing import get_tracer
from app.observability.metrics import Gauge, Counter

tracer = get_tracer(__name__)

# Metrics
service_health_status = Gauge(
    "octup_service_health_status",
    "Service health status (1=healthy, 0=unhealthy)",
    ["service", "check_type"]
)

health_check_duration = Gauge(
    "octup_health_check_duration_seconds",
    "Duration of health checks",
    ["service", "check_type"]
)

health_check_failures = Counter(
    "octup_health_check_failures_total",
    "Total health check failures",
    ["service", "check_type", "error_type"]
)


class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Health information for a service."""
    service_name: str
    status: HealthStatus
    last_check: float = field(default_factory=time.time)
    response_time: Optional[float] = None
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self.status == HealthStatus.HEALTHY
    
    def age_seconds(self) -> float:
        """Get age of health check in seconds."""
        return time.time() - self.last_check


class HealthChecker:
    """Health checker for external services."""
    
    def __init__(self):
        """Initialize health checker."""
        self._health_cache: Dict[str, ServiceHealth] = {}
        self._check_functions: Dict[str, Callable] = {}
        self._lock = asyncio.Lock()
    
    def register_check(self, service_name: str, check_function: Callable):
        """Register health check function for a service.
        
        Args:
            service_name: Name of the service
            check_function: Async function that returns ServiceHealth
        """
        self._check_functions[service_name] = check_function
    
    async def check_service(self, service_name: str, force: bool = False) -> ServiceHealth:
        """Check health of a specific service.
        
        Args:
            service_name: Name of the service to check
            force: Force check even if cached result is recent
            
        Returns:
            Service health information
        """
        async with self._lock:
            # Check if we have recent cached result
            if not force and service_name in self._health_cache:
                cached = self._health_cache[service_name]
                if cached.age_seconds() < 30:  # 30 second cache
                    return cached
            
            # Perform health check
            if service_name not in self._check_functions:
                return ServiceHealth(
                    service_name=service_name,
                    status=HealthStatus.UNKNOWN,
                    error_message="No health check registered"
                )
            
            try:
                start_time = time.time()
                health = await self._check_functions[service_name]()
                duration = time.time() - start_time
                
                health.response_time = duration
                health.last_check = time.time()
                
                # Update metrics
                status_value = 1 if health.is_healthy() else 0
                service_health_status.labels(
                    service=service_name,
                    check_type="full"
                ).set(status_value)
                
                health_check_duration.labels(
                    service=service_name,
                    check_type="full"
                ).set(duration)
                
                # Cache result
                self._health_cache[service_name] = health
                return health
                
            except Exception as e:
                # Record failure
                health_check_failures.labels(
                    service=service_name,
                    check_type="full",
                    error_type=type(e).__name__
                ).inc()
                
                health = ServiceHealth(
                    service_name=service_name,
                    status=HealthStatus.UNHEALTHY,
                    error_message=str(e)
                )
                
                service_health_status.labels(
                    service=service_name,
                    check_type="full"
                ).set(0)
                
                self._health_cache[service_name] = health
                return health
    
    async def check_all_services(self, force: bool = False) -> Dict[str, ServiceHealth]:
        """Check health of all registered services.
        
        Args:
            force: Force check even if cached results are recent
            
        Returns:
            Dictionary of service name to health information
        """
        results = {}
        
        # Run all checks concurrently
        tasks = [
            self.check_service(service_name, force)
            for service_name in self._check_functions.keys()
        ]
        
        if tasks:
            health_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(health_results):
                service_name = list(self._check_functions.keys())[i]
                if isinstance(result, Exception):
                    results[service_name] = ServiceHealth(
                        service_name=service_name,
                        status=HealthStatus.UNHEALTHY,
                        error_message=str(result)
                    )
                else:
                    results[service_name] = result
        
        return results
    
    def get_cached_health(self, service_name: str) -> Optional[ServiceHealth]:
        """Get cached health information for a service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            Cached health information or None
        """
        return self._health_cache.get(service_name)
    
    def get_all_cached_health(self) -> Dict[str, ServiceHealth]:
        """Get all cached health information.
        
        Returns:
            Dictionary of service name to cached health
        """
        return self._health_cache.copy()


# Global health checker instance
_health_checker = HealthChecker()


def get_health_checker() -> HealthChecker:
    """Get global health checker instance.
    
    Returns:
        Health checker instance
    """
    return _health_checker


# Predefined health check functions

async def check_database_health(db_session: AsyncSession) -> ServiceHealth:
    """Check database health.
    
    Args:
        db_session: Database session
        
    Returns:
        Database health information
    """
    try:
        start_time = time.time()
        
        # Simple query to check connectivity
        result = await db_session.execute(text("SELECT 1"))
        result.scalar()
        
        response_time = time.time() - start_time
        
        return ServiceHealth(
            service_name="database",
            status=HealthStatus.HEALTHY,
            response_time=response_time,
            details={"query": "SELECT 1"}
        )
        
    except Exception as e:
        return ServiceHealth(
            service_name="database",
            status=HealthStatus.UNHEALTHY,
            error_message=str(e)
        )


async def check_redis_health(redis_client: redis.Redis) -> ServiceHealth:
    """Check Redis health.
    
    Args:
        redis_client: Redis client
        
    Returns:
        Redis health information
    """
    try:
        start_time = time.time()
        
        # Ping Redis
        await redis_client.ping()
        
        response_time = time.time() - start_time
        
        # Get some basic info
        info = await redis_client.info()
        
        return ServiceHealth(
            service_name="redis",
            status=HealthStatus.HEALTHY,
            response_time=response_time,
            details={
                "version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory": info.get("used_memory_human")
            }
        )
        
    except Exception as e:
        return ServiceHealth(
            service_name="redis",
            status=HealthStatus.UNHEALTHY,
            error_message=str(e)
        )


async def check_ai_service_health(base_url: str, api_key: str) -> ServiceHealth:
    """Check AI service health.
    
    Args:
        base_url: AI service base URL
        api_key: API key for authentication
        
    Returns:
        AI service health information
    """
    try:
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try to get models list or make a simple request
            headers = {"Authorization": f"Bearer {api_key}"}
            
            response = await client.get(
                f"{base_url}/models",
                headers=headers
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                return ServiceHealth(
                    service_name="ai_service",
                    status=HealthStatus.HEALTHY,
                    response_time=response_time,
                    details={
                        "models_available": len(data.get("data", [])),
                        "status_code": response.status_code
                    }
                )
            else:
                return ServiceHealth(
                    service_name="ai_service",
                    status=HealthStatus.DEGRADED,
                    response_time=response_time,
                    error_message=f"HTTP {response.status_code}"
                )
                
    except Exception as e:
        return ServiceHealth(
            service_name="ai_service",
            status=HealthStatus.UNHEALTHY,
            error_message=str(e)
        )


async def check_http_endpoint_health(url: str, expected_status: int = 200) -> ServiceHealth:
    """Check HTTP endpoint health.
    
    Args:
        url: URL to check
        expected_status: Expected HTTP status code
        
    Returns:
        HTTP endpoint health information
    """
    try:
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            
            response_time = time.time() - start_time
            
            if response.status_code == expected_status:
                status = HealthStatus.HEALTHY
            elif 200 <= response.status_code < 300:
                status = HealthStatus.HEALTHY
            elif 400 <= response.status_code < 500:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY
            
            return ServiceHealth(
                service_name=f"http_endpoint_{url}",
                status=status,
                response_time=response_time,
                details={
                    "status_code": response.status_code,
                    "url": url
                }
            )
            
    except Exception as e:
        return ServiceHealth(
            service_name=f"http_endpoint_{url}",
            status=HealthStatus.UNHEALTHY,
            error_message=str(e)
        )
