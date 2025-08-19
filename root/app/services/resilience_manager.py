# ==== RESILIENCE MANAGER SERVICE ==== #

"""
Resilience manager for monitoring and managing circuit breakers and health checks.

This module provides comprehensive resilience management including health
monitoring, circuit breaker management, and system availability tracking
with comprehensive observability and metrics integration.
"""

import asyncio
from typing import Dict, Any, Optional


from app.settings import settings
from app.storage.redis import get_redis_client
from app.storage.db import get_session
from app.resilience.health_check import (
    get_health_checker, 
    check_database_health,
    check_redis_health,
    check_ai_service_health,
    ServiceHealth,
    HealthStatus
)
from app.resilience.circuit_breaker import get_all_circuit_breakers, reset_circuit_breaker
from app.observability.tracing import get_tracer
from app.observability.metrics import Gauge


tracer = get_tracer(__name__)

# Metrics
overall_system_health = Gauge(
    "octup_overall_system_health",
    "Overall system health status (1=healthy, 0=unhealthy)"
)

service_availability = Gauge(
    "octup_service_availability_ratio",
    "Service availability ratio over time",
    ["service"]
)


# ==== RESILIENCE MANAGER CLASS ==== #


class ResilienceManager:
    """
    Manager for resilience patterns and health monitoring.
    
    Provides comprehensive resilience management including health checks,
    circuit breaker monitoring, and system availability tracking with
    automatic monitoring loops and metrics integration.
    """
    
    def __init__(self):
        """
        Initialize resilience manager.
        
        Sets up health check functions for all critical services
        and configures monitoring infrastructure.
        """
        self.health_checker = get_health_checker()
        self._setup_health_checks()
    
    def _setup_health_checks(self) -> None:
        """
        Setup health check functions for all services.
        
        Configures health check functions for database, Redis, and AI
        services with comprehensive error handling and fallback mechanisms.
        """
        
        # Database health check
        async def db_health_check() -> ServiceHealth:
            try:
                async with get_session() as db:
                    return await check_database_health(db)
            except Exception as e:
                return ServiceHealth(
                    service_name="database",
                    status=HealthStatus.UNHEALTHY,
                    error_message=str(e)
                )
        
        # Redis health check
        async def redis_health_check() -> ServiceHealth:
            try:
                redis_client = await get_redis_client()
                return await check_redis_health(redis_client)
            except Exception as e:
                return ServiceHealth(
                    service_name="redis",
                    status=HealthStatus.UNHEALTHY,
                    error_message=str(e)
                )
        
        # AI service health check
        async def ai_health_check() -> ServiceHealth:
            if not settings.AI_API_KEY or settings.AI_PROVIDER_BASE_URL == "disabled":
                return ServiceHealth(
                    service_name="ai_service",
                    status=HealthStatus.UNHEALTHY,
                    error_message="AI service disabled"
                )
            
            return await check_ai_service_health(
                settings.AI_PROVIDER_BASE_URL,
                settings.AI_API_KEY
            )
        
        # Register health checks
        self.health_checker.register_check("database", db_health_check)
        self.health_checker.register_check("redis", redis_health_check)
        self.health_checker.register_check("ai_service", ai_health_check)
    
    # ==== SYSTEM HEALTH MONITORING ==== #
    
    async def get_system_health(self, force_check: bool = False) -> Dict[str, Any]:
        """
        Get comprehensive system health information.
        
        Provides complete system health overview including service status,
        circuit breaker states, and overall availability metrics with
        comprehensive observability integration.
        
        Args:
            force_check (bool): Force fresh health checks instead of using cache
            
        Returns:
            Dict[str, Any]: System health summary with detailed service information
        """
        with tracer.start_as_current_span("get_system_health") as span:
            # Get health of all services
            service_health = await self.health_checker.check_all_services(force_check)
            
            # Get circuit breaker states
            circuit_breakers = get_all_circuit_breakers()
            circuit_breaker_states = {
                name: {
                    "state": cb.state.value,
                    "failure_count": cb.failure_count,
                    "success_count": cb.success_count,
                    "is_healthy": cb.is_closed
                }
                for name, cb in circuit_breakers.items()
            }
            
            # Calculate overall health
            healthy_services = sum(1 for health in service_health.values() if health.is_healthy())
            total_services = len(service_health)
            healthy_circuit_breakers = sum(1 for cb in circuit_breakers.values() if cb.is_closed)
            total_circuit_breakers = len(circuit_breakers)
            
            overall_healthy = (
                healthy_services == total_services and 
                healthy_circuit_breakers == total_circuit_breakers
            )
            
            # Update metrics
            overall_system_health.set(1 if overall_healthy else 0)
            
            for service_name, health in service_health.items():
                availability = 1.0 if health.is_healthy() else 0.0
                service_availability.labels(service=service_name).set(availability)
            
            span.set_attribute("overall_healthy", overall_healthy)
            span.set_attribute("healthy_services", healthy_services)
            span.set_attribute("total_services", total_services)
            
            return {
                "overall_healthy": overall_healthy,
                "services": {
                    name: {
                        "status": health.status.value,
                        "healthy": health.is_healthy(),
                        "response_time": health.response_time,
                        "error_message": health.error_message,
                        "last_check": health.last_check,
                        "details": health.details
                    }
                    for name, health in service_health.items()
                },
                "circuit_breakers": circuit_breaker_states,
                "summary": {
                    "healthy_services": healthy_services,
                    "total_services": total_services,
                    "healthy_circuit_breakers": healthy_circuit_breakers,
                    "total_circuit_breakers": total_circuit_breakers,
                    "availability_ratio": healthy_services / max(total_services, 1)
                }
            }
    
    # ==== CIRCUIT BREAKER MANAGEMENT ==== #
    
    async def reset_service_circuit_breaker(self, service_name: str) -> bool:
        """
        Reset circuit breaker for a specific service.
        
        Manually resets circuit breaker state to allow service recovery
        and restore normal operation after resolving underlying issues.
        
        Args:
            service_name (str): Name of the service to reset
            
        Returns:
            bool: True if circuit breaker was reset, False if not found
        """
        with tracer.start_as_current_span("reset_circuit_breaker") as span:
            span.set_attribute("service", service_name)
            
            circuit_breakers = get_all_circuit_breakers()
            if service_name in circuit_breakers:
                reset_circuit_breaker(service_name)
                span.set_attribute("reset_successful", True)
                return True
            
            span.set_attribute("reset_successful", False)
            return False
    
    # ==== SERVICE HEALTH QUERIES ==== #
    
    async def get_service_health(
        self, 
        service_name: str, 
        force_check: bool = False
    ) -> Optional[ServiceHealth]:
        """
        Get health information for a specific service.
        
        Retrieves detailed health status for individual services
        with optional forced refresh for real-time monitoring.
        
        Args:
            service_name (str): Name of the service to check
            force_check (bool): Force fresh health check instead of using cache
            
        Returns:
            Optional[ServiceHealth]: Service health information or None if not found
        """
        return await self.health_checker.check_service(service_name, force_check)
    
    async def get_degraded_services(self) -> Dict[str, ServiceHealth]:
        """
        Get list of services that are degraded or unhealthy.
        
        Identifies services requiring attention or intervention
        based on health status and performance metrics.
        
        Returns:
            Dict[str, ServiceHealth]: Dictionary of degraded/unhealthy services
        """
        all_health = await self.health_checker.check_all_services()
        
        return {
            name: health
            for name, health in all_health.items()
            if health.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        }
    
    async def get_open_circuit_breakers(self) -> Dict[str, Any]:
        """
        Get list of circuit breakers that are open.
        
        Identifies circuit breakers in open state indicating
        service failures requiring attention and intervention.
        
        Returns:
            Dict[str, Any]: Dictionary of open circuit breakers with their stats
        """
        circuit_breakers = get_all_circuit_breakers()
        
        return {
            name: {
                "state": cb.stats.state.value,
                "failure_count": cb.stats.failure_count,
                "last_failure_time": cb.stats.last_failure_time,
                "state_changed_at": cb.stats.state_changed_at
            }
            for name, cb in circuit_breakers.items()
            if cb.is_open()
        }
    
    # ==== CONTINUOUS MONITORING ==== #
    
    async def run_health_monitoring_loop(self, interval_seconds: int = 30) -> None:
        """
        Run continuous health monitoring loop.
        
        Executes continuous health monitoring with configurable intervals
        to provide real-time system status and alerting capabilities.
        
        Args:
            interval_seconds (int): Interval between health checks in seconds
        """
        while True:
            try:
                with tracer.start_as_current_span("health_monitoring_cycle"):
                    # Check system health
                    health_summary = await self.get_system_health(force_check=True)
                    
                    # Log degraded services
                    degraded = await self.get_degraded_services()
                    if degraded:
                        print(f"Degraded services detected: {list(degraded.keys())}")
                    
                    # Log open circuit breakers
                    open_circuits = await self.get_open_circuit_breakers()
                    if open_circuits:
                        print(f"Open circuit breakers: {list(open_circuits.keys())}")
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                print(f"Health monitoring error: {e}")
                await asyncio.sleep(interval_seconds)


# ==== GLOBAL SERVICE INSTANCE ==== #


# Global resilience manager instance
_resilience_manager: Optional[ResilienceManager] = None


def get_resilience_manager() -> ResilienceManager:
    """
    Get global resilience manager instance.
    
    Provides singleton access to the resilience manager for consistent
    configuration and resource management across the application.
    
    Returns:
        ResilienceManager: Global resilience manager instance
    """
    global _resilience_manager
    if _resilience_manager is None:
        _resilience_manager = ResilienceManager()
    return _resilience_manager
