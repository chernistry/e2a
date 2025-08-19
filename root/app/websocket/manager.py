# ==== WEBSOCKET CONNECTION MANAGER ==== #

"""
WebSocket connection manager for real-time dashboard updates in Octup E²A.

This module provides comprehensive WebSocket connection management with tenant
isolation, event subscription handling, connection lifecycle management,
and real-time data broadcasting for dashboard applications.
"""

import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass

from fastapi import WebSocket

from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger


# ==== MODULE INITIALIZATION ==== #

logger = ContextualLogger(__name__)
tracer = get_tracer(__name__)


# ==== DATA STRUCTURES ==== #

@dataclass
class ConnectionInfo:
    """
    Information about a WebSocket connection.
    
    Stores comprehensive connection metadata including tenant context,
    connection timing, health monitoring, and event subscriptions
    for efficient connection management and routing.
    """
    websocket: WebSocket
    tenant: str
    connected_at: datetime
    last_ping: Optional[datetime] = None
    subscribed_events: Set[str] = None
    
    def __post_init__(self) -> None:
        """Initialize default values for optional fields."""
        if self.subscribed_events is None:
            self.subscribed_events = set()


# ==== CONNECTION MANAGER CLASS ==== #

class ConnectionManager:
    """
    Manages WebSocket connections for real-time dashboard updates.
    
    Provides comprehensive WebSocket connection management with tenant isolation,
    event subscription handling, connection health monitoring, and efficient
    message broadcasting for real-time dashboard applications.
    """
    
    def __init__(self) -> None:
        """
        Initialize connection manager with tenant-isolated storage.
        
        Sets up data structures for efficient connection management,
        tenant isolation, and concurrent access protection.
        """
        # --► TENANT-ISOLATED CONNECTION STORAGE
        # tenant -> list of connections
        self.active_connections: Dict[str, List[ConnectionInfo]] = {}
        
        # --► QUICK LOOKUP OPTIMIZATION
        # websocket -> connection info for O(1) lookup
        self.connection_lookup: Dict[WebSocket, ConnectionInfo] = {}
        
        # --► CONCURRENCY PROTECTION
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, tenant: str) -> None:
        """Accept a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            tenant: Tenant identifier
        """
        with tracer.start_as_current_span("websocket_connect") as span:
            span.set_attribute("tenant", tenant)
            
            await websocket.accept()
            
            connection_info = ConnectionInfo(
                websocket=websocket,
                tenant=tenant,
                connected_at=datetime.now(timezone.utc)
            )
            
            async with self._lock:
                if tenant not in self.active_connections:
                    self.active_connections[tenant] = []
                
                self.active_connections[tenant].append(connection_info)
                self.connection_lookup[websocket] = connection_info
            
            logger.info(f"WebSocket connected for tenant {tenant}")
            span.set_attribute("total_connections", len(self.connection_lookup))
            
            # Send welcome message
            await self._send_to_connection(websocket, {
                "type": "connection:established",
                "payload": {
                    "tenant": tenant,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                    "connection_id": id(websocket)
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection.
        
        Args:
            websocket: WebSocket connection to remove
        """
        with tracer.start_as_current_span("websocket_disconnect"):
            async with self._lock:
                connection_info = self.connection_lookup.pop(websocket, None)
                
                if connection_info:
                    tenant = connection_info.tenant
                    if tenant in self.active_connections:
                        try:
                            self.active_connections[tenant].remove(connection_info)
                            if not self.active_connections[tenant]:
                                del self.active_connections[tenant]
                        except ValueError:
                            pass  # Connection already removed
                    
                    logger.info(f"WebSocket disconnected for tenant {tenant}")
    
    async def broadcast_to_tenant(self, tenant: str, message: Dict[str, Any]) -> int:
        """Broadcast message to all connections for a tenant.
        
        Args:
            tenant: Tenant identifier
            message: Message to broadcast
            
        Returns:
            Number of successful sends
        """
        with tracer.start_as_current_span("websocket_broadcast") as span:
            span.set_attribute("tenant", tenant)
            span.set_attribute("message_type", message.get("type", "unknown"))
            
            if tenant not in self.active_connections:
                span.set_attribute("connections_count", 0)
                return 0
            
            connections = self.active_connections[tenant].copy()
            span.set_attribute("connections_count", len(connections))
            
            successful_sends = 0
            failed_connections = []
            
            for connection_info in connections:
                try:
                    await self._send_to_connection(connection_info.websocket, message)
                    successful_sends += 1
                except Exception as e:
                    logger.warning(f"Failed to send message to connection: {e}")
                    failed_connections.append(connection_info)
            
            # Clean up failed connections
            if failed_connections:
                async with self._lock:
                    for failed_conn in failed_connections:
                        try:
                            self.active_connections[tenant].remove(failed_conn)
                            self.connection_lookup.pop(failed_conn.websocket, None)
                        except (ValueError, KeyError):
                            pass
            
            span.set_attribute("successful_sends", successful_sends)
            span.set_attribute("failed_sends", len(failed_connections))
            
            return successful_sends
    
    async def broadcast_to_all(self, message: Dict[str, Any]) -> int:
        """Broadcast message to all connected clients.
        
        Args:
            message: Message to broadcast
            
        Returns:
            Total number of successful sends
        """
        with tracer.start_as_current_span("websocket_broadcast_all") as span:
            span.set_attribute("message_type", message.get("type", "unknown"))
            
            total_sends = 0
            for tenant in list(self.active_connections.keys()):
                sends = await self.broadcast_to_tenant(tenant, message)
                total_sends += sends
            
            span.set_attribute("total_sends", total_sends)
            return total_sends
    
    async def handle_message(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Handle incoming message from WebSocket client.
        
        Args:
            websocket: WebSocket connection
            message: Received message
        """
        with tracer.start_as_current_span("websocket_handle_message") as span:
            connection_info = self.connection_lookup.get(websocket)
            if not connection_info:
                return
            
            message_type = message.get("type", "unknown")
            span.set_attribute("message_type", message_type)
            span.set_attribute("tenant", connection_info.tenant)
            
            if message_type == "ping":
                await self._handle_ping(websocket, message)
            elif message_type == "subscribe":
                await self._handle_subscribe(websocket, message)
            elif message_type == "unsubscribe":
                await self._handle_unsubscribe(websocket, message)
            else:
                logger.warning(f"Unknown message type: {message_type}")
    
    async def _handle_ping(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Handle ping message and respond with pong.
        
        Args:
            websocket: WebSocket connection
            message: Ping message
        """
        connection_info = self.connection_lookup.get(websocket)
        if connection_info:
            connection_info.last_ping = datetime.now(timezone.utc)
        
        # Send pong response
        pong_message = {
            "type": "pong",
            "payload": message.get("payload", {}),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await self._send_to_connection(websocket, pong_message)
    
    async def _handle_subscribe(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Handle subscription to events.
        
        Args:
            websocket: WebSocket connection
            message: Subscribe message
        """
        connection_info = self.connection_lookup.get(websocket)
        if not connection_info:
            return
        
        events = message.get("payload", {}).get("events", [])
        if isinstance(events, list):
            connection_info.subscribed_events.update(events)
            
            # Send confirmation
            await self._send_to_connection(websocket, {
                "type": "subscription:confirmed",
                "payload": {
                    "events": list(connection_info.subscribed_events)
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    async def _handle_unsubscribe(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Handle unsubscription from events.
        
        Args:
            websocket: WebSocket connection
            message: Unsubscribe message
        """
        connection_info = self.connection_lookup.get(websocket)
        if not connection_info:
            return
        
        events = message.get("payload", {}).get("events", [])
        if isinstance(events, list):
            for event in events:
                connection_info.subscribed_events.discard(event)
    
    async def _send_to_connection(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Send message to a specific WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            message: Message to send
            
        Raises:
            Exception: If send fails
        """
        try:
            await websocket.send_text(json.dumps(message, default=str))
        except Exception as e:
            # Connection might be closed, let caller handle cleanup
            raise e
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics.
        
        Returns:
            Connection statistics
        """
        total_connections = len(self.connection_lookup)
        tenant_stats = {}
        
        for tenant, connections in self.active_connections.items():
            tenant_stats[tenant] = {
                "connection_count": len(connections),
                "oldest_connection": min(
                    (conn.connected_at for conn in connections),
                    default=None
                ),
                "latest_ping": max(
                    (conn.last_ping for conn in connections if conn.last_ping),
                    default=None
                )
            }
        
        return {
            "total_connections": total_connections,
            "tenant_count": len(self.active_connections),
            "tenant_stats": tenant_stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# Global connection manager instance
connection_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance.
    
    Returns:
        Connection manager instance
    """
    return connection_manager
