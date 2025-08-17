# ==== HEALTH CHECK AND RESILIENCE MONITORING ROUTES ==== #

"""
Health check and resilience monitoring routes for Octup E²A.

This module provides comprehensive system health monitoring with circuit breaker
status, service health checks, degraded mode detection, and resilience
management for operational visibility and automated health monitoring.
"""

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.services.resilience_manager import get_resilience_manager, ResilienceManager
from app.observability.tracing import get_tracer


# ==== ROUTER INITIALIZATION ==== #


router = APIRouter()
tracer = get_tracer(__name__)


# ==== HEALTH CHECK ENDPOINTS ==== #


@router.get("/health", response_model=Dict[str, Any])
async def get_system_health(
    force: bool = Query(False, description="Force fresh health checks"),
    resilience_manager: ResilienceManager = Depends(get_resilience_manager)
) -> Dict[str, Any]:
    """
    Get comprehensive system health information.
    
    Provides detailed system health status including service availability,
    circuit breaker states, performance metrics, and overall system health
    with optional forced refresh for real-time monitoring.
    
    Args:
        force (bool): Force fresh health checks instead of using cache
        resilience_manager (ResilienceManager): Resilience manager dependency
        
    Returns:
        Dict[str, Any]: System health summary including services and circuit breakers
    """
    with tracer.start_as_current_span("health_check_endpoint") as span:
        span.set_attribute("force_check", force)
        
        health_data = await resilience_manager.get_system_health(force_check=force)
        
        # --► HTTP STATUS BASED ON HEALTH
        if health_data["overall_healthy"]:
            return health_data
        else:
            # Return 503 Service Unavailable if system is unhealthy
            return JSONResponse(
                status_code=503,
                content=health_data
            )


@router.get("/health/{service_name}", response_model=Dict[str, Any])
async def get_service_health(
    service_name: str,
    force: bool = Query(False, description="Force fresh health check"),
    resilience_manager: ResilienceManager = Depends(get_resilience_manager)
) -> Dict[str, Any]:
    """
    Get health information for a specific service.
    
    Provides detailed health status for individual services including
    response times, error messages, and last check timestamps.
    
    Args:
        service_name (str): Name of the service to check
        force (bool): Force fresh health check instead of using cache
        resilience_manager (ResilienceManager): Resilience manager dependency
        
    Returns:
        Dict[str, Any]: Service health information with status and metrics
        
    Raises:
        HTTPException: If service not found or access denied
    """
    with tracer.start_as_current_span("service_health_check") as span:
        span.set_attribute("service", service_name)
        span.set_attribute("force_check", force)
        
        health = await resilience_manager.get_service_health(
            service_name, 
            force_check=force
        )
        
        if health is None:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_name}' not found"
            )
        
        health_data = {
            "service_name": health.service_name,
            "status": health.status.value,
            "healthy": health.is_healthy(),
            "response_time": health.response_time,
            "error_message": health.error_message,
            "last_check": health.last_check,
            "age_seconds": health.age_seconds(),
            "details": health.details
        }
        
        # Return appropriate status code
        if health.is_healthy():
            return health_data
        else:
            return JSONResponse(
                status_code=503,
                content=health_data
            )


# ==== CIRCUIT BREAKER MANAGEMENT ==== #


@router.get("/circuit-breakers", response_model=Dict[str, Any])
async def get_circuit_breaker_status(
    resilience_manager: ResilienceManager = Depends(get_resilience_manager)
) -> Dict[str, Any]:
    """
    Get status of all circuit breakers.
    
    Provides comprehensive circuit breaker status including open/closed states,
    failure counts, and summary statistics for resilience monitoring.
    
    Args:
        resilience_manager (ResilienceManager): Resilience manager dependency
        
    Returns:
        Dict[str, Any]: Circuit breaker status information with summary counts
    """
    with tracer.start_as_current_span("circuit_breaker_status"):
        health_data = await resilience_manager.get_system_health()
        
        return {
            "circuit_breakers": health_data["circuit_breakers"],
            "summary": {
                "total": len(health_data["circuit_breakers"]),
                "open": len(await resilience_manager.get_open_circuit_breakers()),
                "healthy": health_data["summary"]["healthy_circuit_breakers"]
            }
        }


@router.post("/circuit-breakers/{service_name}/reset")
async def reset_circuit_breaker(
    service_name: str,
    resilience_manager: ResilienceManager = Depends(get_resilience_manager)
) -> Dict[str, Any]:
    """
    Reset circuit breaker for a specific service.
    
    Allows manual reset of circuit breakers to restore service connectivity
    after resolving underlying issues or for testing purposes.
    
    Args:
        service_name (str): Name of the service to reset circuit breaker for
        resilience_manager (ResilienceManager): Resilience manager dependency
        
    Returns:
        Dict[str, Any]: Reset operation result with confirmation
        
    Raises:
        HTTPException: If service not found or reset operation fails
    """
    with tracer.start_as_current_span("reset_circuit_breaker") as span:
        span.set_attribute("service", service_name)
        
        success = await resilience_manager.reset_service_circuit_breaker(service_name)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Circuit breaker for service '{service_name}' not found"
            )
        
        return {
            "service": service_name,
            "reset": True,
            "message": f"Circuit breaker for {service_name} has been reset"
        }


# ==== SYSTEM STATUS MONITORING ==== #


@router.get("/degraded", response_model=Dict[str, Any])
async def get_degraded_services(
    resilience_manager: ResilienceManager = Depends(get_resilience_manager)
) -> Dict[str, Any]:
    """
    Get list of degraded or unhealthy services.
    
    Provides comprehensive view of services experiencing issues including
    error details, response times, and circuit breaker states for
    operational monitoring and alerting.
    
    Args:
        resilience_manager (ResilienceManager): Resilience manager dependency
        
    Returns:
        Dict[str, Any]: List of degraded services with detailed status information
    """
    with tracer.start_as_current_span("get_degraded_services"):
        degraded = await resilience_manager.get_degraded_services()
        open_circuits = await resilience_manager.get_open_circuit_breakers()
        
        return {
            "degraded_services": {
                name: {
                    "status": health.status.value,
                    "error_message": health.error_message,
                    "last_check": health.last_check,
                    "response_time": health.response_time
                }
                for name, health in degraded.items()
            },
            "open_circuit_breakers": open_circuits,
            "summary": {
                "degraded_count": len(degraded),
                "open_circuits_count": len(open_circuits),
                "needs_attention": len(degraded) > 0 or len(open_circuits) > 0
            }
        }


# ==== KUBERNETES PROBE ENDPOINTS ==== #


@router.get("/readiness")
async def readiness_check(
    resilience_manager: ResilienceManager = Depends(get_resilience_manager)
) -> Dict[str, Any]:
    """
    Kubernetes readiness probe endpoint.
    
    Determines if the application is ready to receive traffic by checking
    critical service dependencies and overall system health status.
    
    Args:
        resilience_manager (ResilienceManager): Resilience manager dependency
        
    Returns:
        Dict[str, Any]: Readiness status with detailed service information
    """
    with tracer.start_as_current_span("readiness_check"):
        health_data = await resilience_manager.get_system_health()
        
        # Consider system ready if critical services are healthy
        critical_services = ["database", "redis"]
        critical_healthy = all(
            health_data["services"].get(service, {}).get("healthy", False)
            for service in critical_services
        )
        
        if critical_healthy:
            return {"status": "ready", "timestamp": health_data["summary"]}
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "reason": "Critical services unhealthy",
                    "services": health_data["services"]
                }
            )


@router.get("/liveness")
async def liveness_check() -> Dict[str, str]:
    """
    Kubernetes liveness probe endpoint.
    
    Simple endpoint to verify the application process is running and
    responsive to HTTP requests.
    
    Returns:
        Dict[str, str]: Liveness status (always healthy if endpoint responds)
    """
    return {"status": "alive"}
