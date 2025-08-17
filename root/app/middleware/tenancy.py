# ==== MULTI-TENANCY MIDDLEWARE ==== #

"""
Multi-tenancy middleware for request isolation in Octup E²A.

This module provides comprehensive tenant isolation with header-based tenant
identification, request scope injection, and validation for secure multi-tenant
operations across all API endpoints.
"""

from typing import Callable, Awaitable

from fastapi import Request, HTTPException
from starlette.types import ASGIApp, Scope, Receive, Send

from app.observability.tracing import get_tracer


# ==== MODULE INITIALIZATION ==== #

tracer = get_tracer(__name__)


# ==== UTILITY FUNCTIONS ==== #

def get_tenant_id(request: Request) -> str:
    """
    Extract tenant ID from request scope.
    
    Retrieves the tenant identifier that was injected into the request
    scope by the tenancy middleware for downstream processing.
    
    Args:
        request (Request): FastAPI request object with tenant context
        
    Returns:
        str: Tenant ID string for multi-tenant operations
    """
    return request.scope.get("tenant_id", "default")


# ==== TENANCY MIDDLEWARE CLASS ==== #

class TenancyMiddleware:
    """
    Middleware to extract and validate tenant information.
    
    Provides comprehensive tenant isolation by extracting tenant identifiers
    from request headers, validating tenant access, and injecting tenant
    context into request scope for downstream processing.
    """
    
    def __init__(self, app: ASGIApp, require_tenant: bool = True):
        """
        Initialize tenancy middleware with validation configuration.
        
        Args:
            app (ASGIApp): ASGI application instance
            require_tenant (bool): Whether to require tenant header validation
        """
        self.app = app
        self.require_tenant = require_tenant
        
        # --► PATHS EXEMPT FROM TENANT VALIDATION
        self.exempt_paths = {
            "/healthz",
            "/readyz", 
            "/info",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/ws/stats"
        }


    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Process ASGI request with tenant validation and context injection.
        
        Implements comprehensive tenant validation with header extraction,
        format validation, and scope injection for multi-tenant isolation
        across all API endpoints.
        
        Args:
            scope (Scope): ASGI scope containing request metadata
            receive (Receive): ASGI receive callable for request data
            send (Send): ASGI send callable for response data
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
            
        # --► PATH AND METHOD EXTRACTION
        path = scope["path"]
        method = scope["method"]
        
        # ⚠️ Always allow OPTIONS requests (CORS preflight)
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return
            
        # Skip tenant validation for exempt paths
        if path in self.exempt_paths:
            await self.app(scope, receive, send)
            return
        
        # --► TENANT ID EXTRACTION FROM HEADERS
        headers = dict(scope["headers"])
        tenant_id = headers.get(b"x-tenant-id")
        
        if self.require_tenant and not tenant_id:
            await self._send_error_response(
                send, 
                400, 
                '{"detail":"Missing X-Tenant-Id header"}'
            )
            return
        
        # --► TENANT ID FORMAT VALIDATION
        if tenant_id and not self._is_valid_tenant_id(tenant_id.decode()):
            await self._send_error_response(
                send, 
                400, 
                '{"detail":"Invalid X-Tenant-Id format"}'
            )
            return
        
        # --► SCOPE INJECTION FOR DOWNSTREAM PROCESSING
        scope["tenant_id"] = tenant_id.decode() if tenant_id else "default"
        
        await self.app(scope, receive, send)


    async def _send_error_response(
        self, 
        send: Send, 
        status: int, 
        body: str
    ) -> None:
        """
        Send HTTP error response directly through ASGI.
        
        Args:
            send (Send): ASGI send callable
            status (int): HTTP status code
            body (str): Response body content
        """
        response = {
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"application/json"],
            ],
        }
        await send(response)
        
        await send({
            "type": "http.response.body",
            "body": body.encode(),
        })


    def _is_valid_tenant_id(self, tenant_id: str) -> bool:
        """
        Validate tenant ID format and constraints.
        
        Implements comprehensive tenant ID validation with length limits
        and character restrictions for security and consistency.
        
        Args:
            tenant_id (str): Tenant identifier to validate
            
        Returns:
            bool: True if valid format, False otherwise
        """
        if not tenant_id or len(tenant_id) > 64:
            return False
        
        # Allow alphanumeric characters, hyphens, and underscores only
        return all(c.isalnum() or c in "-_" for c in tenant_id)
