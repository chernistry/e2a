# ==== OCTUP E²A MAIN APPLICATION MODULE ==== #

"""
Main FastAPI application for Octup E²A.

This module provides the core FastAPI application with comprehensive middleware,
observability, and error handling for the SLA monitoring and invoice validation platform.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.settings import settings
from app.storage.db import init_database, close_database, get_session
from app.observability.tracing import init_tracing
from app.observability.metrics import init_metrics, metrics_router
from app.observability.logging import init_logging
from app.middleware.correlation import CorrelationMiddleware
from app.middleware.tenancy import TenancyMiddleware

logger = logging.getLogger(__name__)
from app.routes import (
    ingest, exceptions, admin, health, websocket, dashboard, slack, exception_details
)


# ==== APPLICATION LIFECYCLE MANAGEMENT ==== #


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager for startup and shutdown operations.
    
    Handles initialization of logging, tracing, database connections,
    and proper cleanup during application shutdown.
    
    Args:
        app (FastAPI): FastAPI application instance
        
    Yields:
        None: Control back to FastAPI during application runtime
    """
    # --► STARTUP SEQUENCE
    init_logging(settings.LOG_LEVEL)
    init_tracing(settings.SERVICE_NAME)
    init_database()
    
    yield
    
    # --► SHUTDOWN SEQUENCE
    await close_database()


# ==== APPLICATION FACTORY ==== #


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application with comprehensive middleware stack.
    
    Initializes the application with CORS, custom middleware, observability,
    health check endpoints, and global exception handlers.
    
    Returns:
        FastAPI: Fully configured FastAPI application instance
    """
    app = FastAPI(
        title="Octup E²A",
        description="SLA Radar + Invoice Guard with AI Exception Analyst",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.APP_ENV == "dev" else None,
        redoc_url="/redoc" if settings.APP_ENV == "dev" else None
    )
    
    # --► OBSERVABILITY INITIALIZATION
    init_metrics(app)
    
    # --► MIDDLEWARE STACK CONFIGURATION
    # ⚠️ CORS middleware must be added FIRST before other middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000", 
            "http://localhost:8080", 
            "*"
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    
    # Custom middleware added AFTER CORS
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(TenancyMiddleware, require_tenant=True)
    
    # --► HEALTH CHECK ENDPOINTS
    _register_health_endpoints(app)
    
    # --► APPLICATION INFO ENDPOINT
    _register_info_endpoint(app)
    
    # --► ROUTER REGISTRATION
    _register_routers(app)
    
    # --► EXCEPTION HANDLERS
    _register_exception_handlers(app)
    
    # --► OPENTELEMETRY INSTRUMENTATION
    FastAPIInstrumentor.instrument_app(app)
    
    # --► STARTUP AND SHUTDOWN HANDLERS
    @app.on_event("startup")
    async def startup_event():
        """Initialize background processors for optimized ingestion."""
        try:
            from app.routes.ingest_optimized import start_background_processors
            await start_background_processors()
            logger.info("Started optimized ingestion background processors")
        except ImportError:
            logger.info("Optimized ingestion not available, skipping background processors")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup background processors."""
        try:
            from app.routes.ingest_optimized import stop_background_processors
            await stop_background_processors()
            logger.info("Stopped optimized ingestion background processors")
        except ImportError:
            pass
    
    return app


# ==== ENDPOINT REGISTRATION HELPERS ==== #


def _register_health_endpoints(app: FastAPI) -> None:
    """
    Register health check endpoints for liveness and readiness probes.
    
    Args:
        app (FastAPI): FastAPI application instance
    """
    @app.get("/healthz", tags=["health"])
    async def health_check() -> dict:
        """
        Liveness probe endpoint for container orchestration.
        
        Returns:
            dict: Health status with timestamp and service information
        """
        return {
            "status": "ok", 
            "service": settings.SERVICE_NAME,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    
    @app.options("/healthz", tags=["health"])
    async def health_check_options() -> JSONResponse:
        """
        OPTIONS handler for healthz endpoint with CORS headers.
        
        Returns:
            JSONResponse: Empty response with CORS headers
        """
        response = JSONResponse(content={})
        response.headers["access-control-allow-origin"] = "*"
        response.headers["access-control-allow-methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        response.headers["access-control-allow-headers"] = "*"
        return response
    
    
    @app.get("/readyz", tags=["health"])
    async def readiness_check() -> dict:
        """
        Readiness probe endpoint for container orchestration.
        
        Returns:
            dict: Readiness status with environment information
        """
        return {
            "status": "ready",
            "service": settings.SERVICE_NAME,
            "environment": settings.APP_ENV
        }
    
    
    @app.options("/readyz", tags=["health"])
    async def readiness_check_options() -> JSONResponse:
        """
        OPTIONS handler for readyz endpoint with CORS headers.
        
        Returns:
            JSONResponse: Empty response with CORS headers
        """
        response = JSONResponse(content={})
        response.headers["access-control-allow-origin"] = "*"
        response.headers["access-control-allow-methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        response.headers["access-control-allow-headers"] = "*"
        return response


def _register_info_endpoint(app: FastAPI) -> None:
    """
    Register application information endpoint with service status checks.
    
    Args:
        app (FastAPI): FastAPI application instance
    """
    @app.get("/info", tags=["info"])
    async def app_info() -> dict:
        """
        Application information endpoint with dependency health checks.
        
        Provides comprehensive service status including database and Redis
        connectivity, AI service availability, and configuration details.
        
        Returns:
            dict: Application metadata and dependency status
        """
        # --► DATABASE STATUS CHECK
        database_status = "unknown"
        try:
            async with get_session() as db:
                await db.execute("SELECT 1")
                database_status = "connected"
        except Exception:
            database_status = "disconnected"
        
        # --► REDIS STATUS CHECK
        redis_status = "unknown"
        try:
            from app.storage.redis import get_redis_client
            redis_client = get_redis_client()
            await redis_client.ping()
            redis_status = "connected"
        except Exception:
            redis_status = "disconnected"
        
        return {
            "service": settings.SERVICE_NAME,
            "version": "0.1.0",
            "environment": settings.APP_ENV,
            "database_status": database_status,
            "redis_status": redis_status,
            "observability_provider": settings.OBSERVABILITY_PROVIDER,
            "ai_provider": "enabled" if settings.AI_API_KEY else "disabled"
        }


def _register_routers(app: FastAPI) -> None:
    """
    Register all application routers with appropriate prefixes and tags.
    
    Args:
        app (FastAPI): FastAPI application instance
    """
    app.include_router(metrics_router, prefix="", tags=["monitoring"])
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(exception_details.router, prefix="/api", tags=["exception-details"])
    app.include_router(websocket.router, prefix="/api", tags=["websocket"])
    app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
    
    # Add optimized ingestion routes
    try:
        from app.routes import ingest_optimized
        app.include_router(ingest_optimized.router, prefix="", tags=["ingest-optimized"])
    except ImportError:
        logger.warning("Optimized ingestion routes not available")
    
    app.include_router(exceptions.router, prefix="/exceptions", tags=["exceptions"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(slack.router, prefix="/api", tags=["slack"])


# ==== EXCEPTION HANDLERS ==== #


def _register_exception_handlers(app: FastAPI) -> None:
    """
    Register global exception handlers for comprehensive error handling.
    
    Args:
        app (FastAPI): FastAPI application instance
    """
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, 
        exc: Exception
    ) -> JSONResponse:
        """
        Global exception handler for unhandled errors.
        
        Provides consistent error response format with correlation ID
        for debugging and request tracing.
        
        Args:
            request (Request): HTTP request that caused the exception
            exc (Exception): Exception that occurred
            
        Returns:
            JSONResponse: Standardized error response
        """
        correlation_id = getattr(request.state, 'correlation_id', 'unknown')
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id,
                "code": "INTERNAL_ERROR"
            }
        )
    
    
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc) -> JSONResponse:
        """
        Handle 404 Not Found errors with consistent response format.
        
        Args:
            request (Request): HTTP request that caused the exception
            exc: Exception that occurred
            
        Returns:
            JSONResponse: Standardized 404 error response
        """
        correlation_id = getattr(request.state, 'correlation_id', 'unknown')
        
        return JSONResponse(
            status_code=404,
            content={
                "error": "Not found",
                "detail": "The requested resource was not found",
                "message": "The requested resource was not found",
                "correlation_id": correlation_id,
                "code": "NOT_FOUND"
            }
        )
    
    
    @app.exception_handler(405)
    async def method_not_allowed_handler(
        request: Request, 
        exc
    ) -> JSONResponse:
        """
        Handle 405 Method Not Allowed errors with authentication check.
        
        For admin endpoints, returns 401 if no authorization header is present.
        
        Args:
            request (Request): HTTP request that caused the exception
            exc: Exception that occurred
            
        Returns:
            JSONResponse: Standardized 405 or 401 error response
        """
        correlation_id = getattr(request.state, 'correlation_id', 'unknown')
        
        # ⚠️ SPECIAL HANDLING FOR ADMIN ENDPOINTS
        if request.url.path.startswith("/admin/"):
            auth_header = request.headers.get("authorization")
            if not auth_header:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "Unauthorized",
                        "detail": "Authorization header required",
                        "message": "Authentication required",
                        "correlation_id": correlation_id,
                        "code": "UNAUTHORIZED"
                    }
                )
        
        return JSONResponse(
            status_code=405,
            content={
                "error": "Method not allowed",
                "detail": "The requested method is not allowed for this resource",
                "message": "Method not allowed",
                "correlation_id": correlation_id,
                "code": "METHOD_NOT_ALLOWED"
            }
        )


# ==== APPLICATION INSTANCE ==== #


# Create application instance for deployment
app = create_app()
