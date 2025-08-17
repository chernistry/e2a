# ==== CORRELATION ID MIDDLEWARE ==== #

"""
Correlation ID middleware for request tracing in Octup E²A.

This module provides comprehensive request correlation tracking with automatic
ID generation, distributed tracing integration, and performance metrics
collection for end-to-end request observability.
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.metrics import ingest_latency_seconds
from app.observability.tracing import get_tracer


# ==== MODULE INITIALIZATION ==== #

tracer = get_tracer(__name__)


# ==== CORRELATION MIDDLEWARE CLASS ==== #

class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add correlation IDs to requests and responses.
    
    Provides comprehensive request correlation tracking with automatic ID
    generation, distributed tracing integration, and performance metrics
    collection for complete request lifecycle observability.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with correlation ID tracking and observability.
        
        Implements comprehensive request processing with correlation ID
        management, distributed tracing, performance metrics collection,
        and response header injection for end-to-end traceability.
        
        Args:
            request (Request): Incoming HTTP request
            call_next (Callable): Next middleware/handler in chain
            
        Returns:
            Response: HTTP response with correlation ID header and metrics
        """
        # --► CORRELATION ID MANAGEMENT
        correlation_id = request.headers.get(
            "X-Correlation-Id", 
            str(uuid.uuid4())
        )
        
        # Store in request state for downstream access
        request.state.correlation_id = correlation_id
        
        # --► PERFORMANCE TIMING
        start_time = time.perf_counter()
        
        # --► DISTRIBUTED TRACING
        with tracer.start_as_current_span("http_request") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("correlation_id", correlation_id)
            
            # Process request through middleware chain
            response = await call_next(request)
            
            # --► RESPONSE HEADER INJECTION
            response.headers["X-Correlation-Id"] = correlation_id
            
            # --► METRICS COLLECTION
            duration = time.perf_counter() - start_time
            
            # Extract context for metrics labeling
            tenant = getattr(request.state, 'tenant_id', 'unknown')
            source = 'unknown'
            event_type = 'unknown'
            
            # ⚠️ Extract source from ingest endpoints
            if request.url.path.startswith('/ingest/'):
                source = request.url.path.split('/')[-1]
                event_type = 'api_request'
            
            # Record latency metrics
            ingest_latency_seconds.labels(
                tenant=tenant,
                source=source, 
                event_type=event_type
            ).observe(duration)
            
            # --► SPAN COMPLETION
            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute(
                "http.response_size", 
                len(response.body) if hasattr(response, 'body') else 0
            )
            
            return response


# ==== STANDALONE MIDDLEWARE FUNCTION ==== #

async def with_correlation_id(request: Request, call_next: Callable) -> Response:
    """
    Standalone correlation ID middleware function.
    
    Provides correlation ID functionality as a standalone function
    for use in custom middleware stacks or testing scenarios.
    
    Args:
        request (Request): Incoming HTTP request
        call_next (Callable): Next handler in chain
        
    Returns:
        Response: HTTP response with correlation ID
    """
    middleware = CorrelationMiddleware(None)
    return await middleware.dispatch(request, call_next)
