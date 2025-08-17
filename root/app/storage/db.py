# ==== DATABASE CONNECTION AND SESSION MANAGEMENT ==== #

"""
Database connection and session management for Supabase in Octup E²A.

This module provides comprehensive database connectivity with async SQLAlchemy,
connection pooling, circuit breaker protection, and session lifecycle
management for reliable database operations.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    create_async_engine, 
    async_sessionmaker, 
    AsyncSession,
    AsyncEngine
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from app.settings import settings
from app.observability.metrics import db_connections_active
from app.resilience.decorators import database_resilient
from app.resilience.circuit_breaker import CircuitBreakerError


# ==== SQLALCHEMY CONFIGURATION ==== #

# SQLAlchemy base for model definitions
Base = declarative_base()

# Global engine and session factory instances
engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


# ==== DATABASE INITIALIZATION ==== #

def init_database() -> None:
    """
    Initialize database engine and session factory.
    
    Sets up async SQLAlchemy engine with connection pooling, circuit breaker
    protection, and proper driver configuration for Supabase connectivity
    with comprehensive error handling and observability.
    """
    global engine, SessionLocal
    
    if engine is not None:
        return
    
    # --► DATABASE URL VALIDATION AND DRIVER SETUP
    db_url = settings.DATABASE_URL
    if not db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    
    # Fix SSL parameter for asyncpg compatibility
    if "sslmode=require" in db_url:
        db_url = db_url.replace("sslmode=require", "ssl=require")
    
    # Check if this is a pooler connection
    is_pooler = "pooler" in db_url
    
    # PgBouncer compatibility - use unique statement names to avoid collisions
    try:
        import asyncpg
        
        class _UniqueStmtConnection(asyncpg.Connection):
            """asyncpg Connection with UUID-based prepared-statement IDs."""
            
            def _get_unique_id(self, prefix: str) -> str:
                return f"__asyncpg_{prefix}_{uuid4().hex}__"
        
        connect_args = {
            "statement_cache_size": 0,  # Disable statement cache for PgBouncer
            "connection_class": _UniqueStmtConnection,
            "server_settings": {
                "application_name": "oktup_api",
                "timezone": "UTC"
            }
        }
        
    except ImportError:
        # Fallback if asyncpg not available
        connect_args = {}
    
    # Create async engine with proper pooler configuration
    engine = create_async_engine(
        db_url,
        echo=settings.APP_ENV == "dev",
        # Use NullPool for PgBouncer to avoid double pooling
        poolclass=NullPool if is_pooler else None,
        # Use AUTOCOMMIT isolation for pooler compatibility
        isolation_level="AUTOCOMMIT" if is_pooler else "READ_COMMITTED",
        connect_args=connect_args,
    )
    
    # Create session factory
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False
    )


# @database_resilient("get_session")  # Temporarily disabled for Prefect compatibility
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session with automatic cleanup.
    
    Yields:
        AsyncSession: Database session
        
    Raises:
        Exception: If database connection fails
    """
    if SessionLocal is None:
        init_database()
    
    async with SessionLocal() as session:
        try:
            # Update connection metrics
            db_connections_active.inc()
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            db_connections_active.dec()
            await session.close()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.
    
    Yields:
        AsyncSession: Database session for request handling
    """
    # Create session directly to avoid event loop issues in FastAPI
    session = AsyncSession(engine)
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def close_database() -> None:
    """Close database connections on shutdown."""
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None
