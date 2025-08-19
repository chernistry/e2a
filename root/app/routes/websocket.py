# ==== WEBSOCKET ROUTES MODULE ==== #

"""
WebSocket routes for real-time dashboard updates.

This module provides WebSocket endpoints for real-time communication
including dashboard updates, exception notifications, and health status
broadcasting with comprehensive connection management and error handling.
"""

import json
import asyncio
from typing import Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from app.websocket.manager import get_connection_manager, ConnectionManager
from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger


logger = ContextualLogger(__name__)
tracer = get_tracer(__name__)
router = APIRouter()


# ==== WEBSOCKET CONNECTION ENDPOINTS ==== #


@router.websocket("/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    tenant: str = Query("default", description="Tenant identifier"),
    manager: ConnectionManager = Depends(get_connection_manager)
) -> None:
    """
    WebSocket endpoint for real-time dashboard updates.
    
    Establishes persistent WebSocket connection for real-time dashboard
    updates including metrics, exception notifications, and health status
    changes with automatic reconnection and error handling.
    
    Args:
        websocket (WebSocket): WebSocket connection instance
        tenant (str): Tenant identifier for data isolation
        manager (ConnectionManager): WebSocket connection manager
    """
    with tracer.start_as_current_span("websocket_endpoint") as span:
        span.set_attribute("tenant", tenant)
        
        try:
            # Accept connection
            await manager.connect(websocket, tenant)
            logger.info(f"Dashboard WebSocket connected for tenant: {tenant}")
            
            # Start background tasks for this connection
            metrics_task = asyncio.create_task(
                _send_periodic_metrics(websocket, tenant, manager)
            )
            
            # Handle incoming messages
            while True:
                try:
                    # Receive message from client
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    
                    # Handle the message
                    await manager.handle_message(websocket, message)
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON received: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "payload": {"message": "Invalid JSON format"},
                        "timestamp": "2025-08-16T16:04:02.500Z"
                    }))
                
        except WebSocketDisconnect:
            logger.info(f"Dashboard WebSocket disconnected for tenant: {tenant}")
        except Exception as e:
            logger.error(f"WebSocket error for tenant {tenant}: {e}")
        finally:
            # Clean up
            if 'metrics_task' in locals():
                metrics_task.cancel()
                try:
                    await metrics_task
                except asyncio.CancelledError:
                    pass
            
            await manager.disconnect(websocket)


# ==== BACKGROUND TASKS ==== #


async def _send_periodic_metrics(
    websocket: WebSocket, 
    tenant: str, 
    manager: ConnectionManager
) -> None:
    """
    Send periodic metrics updates to WebSocket client.
    
    Background task that sends regular metrics updates including
    SLA compliance rates, exception counts, and performance metrics
    to maintain real-time dashboard synchronization.
    
    Args:
        websocket (WebSocket): WebSocket connection instance
        tenant (str): Tenant identifier for data isolation
        manager (ConnectionManager): WebSocket connection manager
    """
    try:
        while True:
            # Wait 30 seconds between updates
            await asyncio.sleep(30)
            
            # Generate mock metrics (replace with real data later)
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            metrics_message = {
                "type": "metrics:update",
                "payload": {
                    "timestamp": now_iso,
                    "sla_compliance_rate": 0.95,
                    "active_exceptions": 12,
                    "events_processed_per_minute": 150,
                    "ai_analysis_success_rate": 0.98,
                    "average_response_time": 245,
                    "tenant_metrics": [
                        {
                            "tenant": tenant,
                            "exception_count": 12,
                            "sla_compliance": 0.95,
                            "last_updated": now_iso
                        }
                    ]
                },
                "timestamp": now_iso
            }
            
            # Send to this specific tenant
            await manager.broadcast_to_tenant(tenant, metrics_message)
            
    except asyncio.CancelledError:
        # Task was cancelled, exit gracefully
        pass
    except Exception as e:
        logger.error(f"Error in periodic metrics for tenant {tenant}: {e}")


# ==== WEBSOCKET STATISTICS ==== #


@router.get("/ws/stats")
async def get_websocket_stats(
    manager: ConnectionManager = Depends(get_connection_manager)
) -> Dict[str, Any]:
    """
    Get WebSocket connection statistics.
    
    Provides comprehensive statistics on active WebSocket connections
    including connection counts, tenant distribution, and performance
    metrics for operational monitoring.
    
    Args:
        manager (ConnectionManager): WebSocket connection manager
        
    Returns:
        Dict[str, Any]: Connection statistics and performance metrics
    """
    return manager.get_connection_stats()


# ==== BROADCAST UTILITY FUNCTIONS ==== #


async def broadcast_exception_created(tenant: str, exception_data: Dict[str, Any]) -> None:
    """
    Broadcast exception created event.
    
    Sends real-time notification to all connected clients for a specific
    tenant when a new exception is created, enabling immediate dashboard
    updates and user notifications.
    
    Args:
        tenant (str): Tenant identifier for targeted broadcasting
        exception_data (Dict[str, Any]): Exception details to broadcast
    """
    manager = get_connection_manager()
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    message = {
        "type": "exception:created",
        "payload": exception_data,
        "timestamp": now_iso
    }
    await manager.broadcast_to_tenant(tenant, message)


async def broadcast_exception_updated(tenant: str, exception_data: Dict[str, Any]) -> None:
    """
    Broadcast exception updated event.
    
    Sends real-time notification to all connected clients for a specific
    tenant when an existing exception is updated, enabling immediate
    dashboard synchronization and status updates.
    
    Args:
        tenant (str): Tenant identifier for targeted broadcasting
        exception_data (Dict[str, Any]): Updated exception details
    """
    manager = get_connection_manager()
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    message = {
        "type": "exception:updated",
        "payload": exception_data,
        "timestamp": now_iso
    }
    await manager.broadcast_to_tenant(tenant, message)


async def broadcast_exception_resolved(tenant: str, exception_data: Dict[str, Any]) -> None:
    """
    Broadcast exception resolved event.
    
    Sends real-time notification to all connected clients for a specific
    tenant when an exception is resolved, enabling immediate dashboard
    updates and status synchronization.
    
    Args:
        tenant (str): Tenant identifier for targeted broadcasting
        exception_data (Dict[str, Any]): Resolved exception details
    """
    manager = get_connection_manager()
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    message = {
        "type": "exception:resolved",
        "payload": exception_data,
        "timestamp": now_iso
    }
    await manager.broadcast_to_tenant(tenant, message)


async def broadcast_health_status_change(
    service: str, 
    status: str, 
    details: Dict[str, Any] = None
) -> None:
    """
    Broadcast health status change event.
    
    Sends real-time notification to all connected clients when a service
    health status changes, enabling immediate operational awareness
    and dashboard updates across all tenants.
    
    Args:
        service (str): Service name that experienced status change
        status (str): New health status value
        details (Dict[str, Any], optional): Additional status details
    """
    manager = get_connection_manager()
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    message = {
        "type": "health:status_change",
        "payload": {
            "service": service,
            "status": status,
            "details": details or {},
            "timestamp": now_iso
        },
        "timestamp": now_iso
    }
    await manager.broadcast_to_all(message)
