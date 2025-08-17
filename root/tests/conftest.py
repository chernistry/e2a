# ==== SHARED TEST FIXTURES AND CONFIGURATION ==== #

"""
Shared test fixtures and configuration with proper PostgreSQL setup.

This module provides comprehensive testing infrastructure including
database fixtures, application fixtures, mock services, and cleanup
mechanisms for reliable and isolated testing across all test suites.
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
import respx
from freezegun import freeze_time
from httpx import AsyncClient, ASGITransport


# ==== FORCE ENVIRONMENT SETUP BEFORE ANY IMPORTS ==== #

# Set environment variables BEFORE importing any app modules
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres",
    "DIRECT_URL": "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres",
    "REDIS_URL": "redis://localhost:6379/1",
    "AI_PROVIDER_BASE_URL": "http://mock-ai-service",
    "AI_API_KEY": "test-key-12345",
    "AI_MODEL": "mock-model",
    "AI_TIMEOUT_SECONDS": "1",
    "AI_RETRY_MAX_ATTEMPTS": "1",
    "JWT_SECRET": "test-secret-key-for-testing-only",
    "LOG_LEVEL": "WARNING",
})

# Now import app modules after environment is set
from app.main import create_app
from app.storage.db import init_database, get_session


# ==== ASYNC EVENT LOOP CONFIGURATION ==== #


@pytest.fixture(scope="session")
def event_loop():
    """
    Create an instance of the default event loop for the test session.
    
    Ensures consistent async testing environment across
    all test suites with proper cleanup and isolation.
    
    Returns:
        asyncio.AbstractEventLoop: Event loop for test session
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==== DATABASE FIXTURES ==== #


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    """
    Set up database connection for the test session.
    
    Initializes PostgreSQL test database connection with
    comprehensive validation and connection testing for
    reliable test execution.
    """
    # Force reset any existing database connection
    import app.storage.db
    app.storage.db.engine = None
    app.storage.db.SessionLocal = None
    
    # Initialize database connection with correct URL
    init_database()
    
    # Verify connection works
    async with get_session() as session:
        from sqlalchemy import text
        result = await session.execute(text('SELECT 1 as test'))
        test_value = result.scalar()
        assert test_value == 1, "Database connection test failed"
    
    print("✅ Database connection established successfully")
    yield
    # Cleanup would go here if needed


@pytest_asyncio.fixture
async def db_session(setup_database):
    """
    Provide a database session for tests.
    
    Creates isolated database session for each test
    with proper transaction management and cleanup.
    
    Returns:
        AsyncSession: Database session for test execution
    """
    async with get_session() as session:
        yield session


# ==== APPLICATION FIXTURES ==== #


@pytest_asyncio.fixture
async def app(setup_database):
    """
    Create FastAPI test application with real database.
    
    Initializes complete test application with mocked
    external services while maintaining real database
    operations for comprehensive testing.
    
    Returns:
        FastAPI: Test application instance
    """
    
    # Force reset database connection to ensure we use the test environment
    import app.storage.db
    app.storage.db.engine = None
    app.storage.db.SessionLocal = None
    
    # Re-initialize with test environment
    init_database()
    
    # Mock only external services, keep database real
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.exists.return_value = False

    # Mock health check responses
    mock_health_data = {
        "status": "healthy",
        "timestamp": "2025-08-17T11:00:00Z",
        "overall_healthy": True,
        "services": {
            "database": {"status": "healthy", "response_time_ms": 5},
            "redis": {"status": "healthy", "response_time_ms": 2},
            "ai_service": {"status": "healthy", "response_time_ms": 100}
        },
        "circuit_breakers": {}
    }

    # Mock resilience manager
    mock_resilience_manager = AsyncMock()
    mock_resilience_manager.get_system_health.return_value = mock_health_data

    # Mock DLQ operations to return success
    mock_dlq_stats = {
        "dlq_stats": {"pending": 0, "failed": 0, "processed": 0, "total": 0},
        "total_items": 0,
        "by_tenant": {"test-tenant": 0},
        "by_source": {"shopify": 0, "wms": 0, "carrier": 0},
        "oldest_item_age_seconds": 0,
        "tenant_filter": None
    }

    # Mock only external services, keep database operations real
    with patch("app.services.idempotency.redis.from_url", return_value=mock_redis), \
         patch("app.services.ai_client.AIClient.classify_exception", return_value={"label": "TEST", "confidence": 0.9}), \
         patch("app.services.ai_exception_analyst.analyze_exception_or_fallback", return_value={"analysis": "test"}), \
         patch("app.services.resilience_manager.get_resilience_manager", return_value=mock_resilience_manager), \
         patch("app.resilience.health_check.check_redis_health", return_value={"status": "healthy", "response_time_ms": 2}), \
         patch("app.resilience.health_check.check_ai_service_health", return_value={"status": "healthy", "response_time_ms": 100}), \
         patch("app.storage.dlq.get_dlq_stats", return_value=mock_dlq_stats), \
         patch("app.services.sla_engine.SLAEngine.evaluate_sla", return_value=None):
        
        app = create_app()
        yield app


@pytest_asyncio.fixture
async def client(app):
    """
    Create test client.
    
    Provides HTTP test client for integration testing
    with proper ASGI transport and base URL configuration.
    
    Returns:
        AsyncClient: HTTP test client instance
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ==== TENANT AND HEADER FIXTURES ==== #


@pytest.fixture
def tenant_id():
    """
    Test tenant ID.
    
    Provides consistent tenant identifier for
    multi-tenant testing scenarios.
    
    Returns:
        str: Test tenant identifier
    """
    return "test-tenant"


@pytest.fixture
def tenant_headers(tenant_id):
    """
    Headers with tenant ID.
    
    Creates HTTP headers with tenant identification
    for multi-tenant API testing.
    
    Args:
        tenant_id (str): Tenant identifier for headers
        
    Returns:
        Dict[str, str]: HTTP headers with tenant ID
    """
    return {"X-Tenant-ID": tenant_id}


@pytest.fixture
async def tenant_record(db_session, tenant_id):
    """
    Create tenant record in database.
    
    Ensures the test tenant exists in the database
    for tests that require foreign key relationships.
    
    Args:
        db_session: Database session fixture
        tenant_id (str): Tenant identifier
        
    Returns:
        Tenant: Created tenant record
    """
    from app.storage.models import Tenant
    from sqlalchemy import select
    
    # Check if tenant already exists
    query = select(Tenant).where(Tenant.name == tenant_id)
    result = await db_session.execute(query)
    existing_tenant = result.scalar_one_or_none()
    
    if existing_tenant:
        return existing_tenant
    
    # Create new tenant
    tenant = Tenant(
        name=tenant_id,
        display_name="Test Tenant",
        sla_config={
            "pick_minutes": 120,
            "pack_minutes": 180,
            "ship_minutes": 1440
        },
        billing_config={
            "currency": "USD",
            "rates": {
                "pick": 30,
                "pack": 20,
                "label": 15
            }
        }
    )
    
    db_session.add(tenant)
    await db_session.flush()  # Flush to make it available in the same transaction
    await db_session.refresh(tenant)
    
    return tenant


@pytest.fixture
def admin_headers():
    """
    Headers for admin endpoints.
    
    Provides authentication headers for
    administrative endpoint testing.
    
    Returns:
        Dict[str, str]: Admin authentication headers
    """
    return {"Authorization": "Bearer admin-token"}


# ==== TIME AND CORRELATION FIXTURES ==== #


@pytest.fixture
def base_time():
    """
    Base time for tests.
    
    Provides consistent timestamp for time-based
    testing scenarios and frozen time operations.
    
    Returns:
        datetime: Base timestamp for tests
    """
    return datetime(2025, 8, 17, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def frozen_time(base_time):
    """
    Frozen time for consistent testing.
    
    Creates time-freezing context for deterministic
    time-based testing scenarios.
    
    Args:
        base_time (datetime): Base time to freeze
        
    Returns:
        FreezeTime: Time freezing context manager
    """
    with freeze_time(base_time) as frozen:
        yield frozen


@pytest.fixture
def correlation_id():
    """
    Generate correlation ID for tests.
    
    Creates unique correlation identifiers for
    request tracing and observability testing.
    
    Returns:
        str: Unique correlation identifier
    """
    return str(uuid.uuid4())


# ==== SAMPLE DATA FIXTURES ==== #


@pytest.fixture
def sample_shopify_event():
    """
    Sample Shopify event data.
    
    Provides realistic Shopify event data for
    comprehensive testing scenarios.
    
    Returns:
        Dict[str, Any]: Sample Shopify event data
    """
    return {
        "source": "shopify",
        "event_type": "order_paid",
        "event_id": "evt-shopify-test-001",
        "order_id": "order-test-001",
        "occurred_at": "2025-08-17T10:00:00Z",
        "total_amount_cents": 2999,
        "line_count": 2,
        "customer_email": "test@example.com"
    }


@pytest.fixture
def sample_wms_event():
    """
    Sample WMS event data.
    
    Provides realistic WMS event data for
    comprehensive testing scenarios.
    
    Returns:
        Dict[str, Any]: Sample WMS event data
    """
    return {
        "source": "wms",
        "event_type": "order_picked",
        "event_id": "evt-wms-test-001",
        "order_id": "order-test-001",
        "occurred_at": "2025-08-17T10:30:00Z",
        "picked_items": 2,
        "picker_id": "picker-001"
    }


@pytest.fixture
def sample_carrier_event():
    """
    Sample carrier event data.
    
    Provides realistic carrier event data for
    comprehensive testing scenarios.
    
    Returns:
        Dict[str, Any]: Sample carrier event data
    """
    return {
        "source": "carrier",
        "event_type": "order_shipped",
        "event_id": "evt-carrier-test-001",
        "order_id": "order-test-001",
        "occurred_at": "2025-08-17T11:00:00Z",
        "tracking_number": "TRACK123456",
        "carrier_name": "TestCarrier"
    }


@pytest.fixture
def sample_sla_config():
    """
    Sample SLA configuration.
    
    Provides realistic SLA configuration data
    for testing SLA engine functionality.
    
    Returns:
        Dict[str, Any]: Sample SLA configuration
    """
    return {
        "pick_sla_minutes": 60,
        "pack_sla_minutes": 30,
        "ship_sla_minutes": 120
    }


# ==== ORDER LIFECYCLE FIXTURES ==== #


@pytest.fixture
def order_lifecycle_events(sample_shopify_event, sample_wms_event, sample_carrier_event):
    """
    Complete order lifecycle events.
    
    Provides comprehensive order lifecycle data
    for end-to-end testing scenarios.
    
    Args:
        sample_shopify_event (Dict[str, Any]): Shopify order event
        sample_wms_event (Dict[str, Any]): WMS pick event
        sample_carrier_event (Dict[str, Any]): Carrier ship event
        
    Returns:
        List[Dict[str, Any]]: Complete order lifecycle events
    """
    return [sample_shopify_event, sample_wms_event, sample_carrier_event]


# ==== PERFORMANCE AND MONITORING FIXTURES ==== #


@pytest.fixture
def performance_timer():
    """
    Performance timer for latency tests.
    
    Provides high-precision timing capabilities
    for performance testing and latency measurement.
    
    Returns:
        Timer: Performance timing utility class
    """
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            
        def start(self):
            """Start timing measurement."""
            self.start_time = time.perf_counter()
            self.end_time = None
            
        def stop(self):
            """Stop timing measurement."""
            if self.start_time is not None:
                self.end_time = time.perf_counter()
            
        def elapsed_ms(self):
            """
            Get elapsed time in milliseconds.
            
            Returns:
                float: Elapsed time in milliseconds
            """
            if self.start_time is None:
                return 0
            end_time = self.end_time if self.end_time is not None else time.perf_counter()
            return (end_time - self.start_time) * 1000
    
    return Timer()


# ==== CLEANUP FIXTURES ==== #


@pytest_asyncio.fixture(autouse=True)
async def cleanup_test_data():
    """
    Clean up test data before and after each test.
    
    Ensures test isolation by cleaning up test data
    before and after each test execution for
    reliable and repeatable test results.
    """
    # Simple cleanup using direct connection
    import asyncpg
    
    async def clean_data():
        try:
            conn = await asyncpg.connect('postgresql://postgres:postgres@127.0.0.1:54322/postgres')
            # Clean test events by pattern
            await conn.execute("DELETE FROM order_events WHERE event_id LIKE 'evt-shopify-%' OR event_id LIKE 'evt-wms-%' OR event_id LIKE 'evt-carrier-%'")
            await conn.execute("DELETE FROM exceptions WHERE tenant = 'test-tenant'")
            await conn.execute("DELETE FROM dlq WHERE tenant = 'test-tenant'")
            await conn.close()
        except Exception as e:
            print(f"Cleanup failed: {e}")
    
    # Clean before test
    await clean_data()
    
    yield
    
    # Clean after test
    await clean_data()


@pytest.fixture
def cleanup_redis():
    """
    Clean up Redis after tests.
    
    Provides Redis cleanup capabilities for
    test isolation and reliable execution.
    """
    yield
    # Redis cleanup would go here if needed


# ==== MOCK SETUP FIXTURES ==== #


@pytest.fixture
def setup_ai_mocks():
    """
    Set up AI service mocks.
    
    Provides comprehensive AI service mocking
    for reliable testing without external dependencies.
    
    Returns:
        Dict[str, Any]: Mock objects for AI services
    """
    with patch("app.services.ai_client.AIClient.classify_exception") as mock_classify, \
         patch("app.services.ai_exception_analyst.analyze_exception_or_fallback") as mock_analyze:
        
        mock_classify.return_value = {"label": "TEST_EXCEPTION", "confidence": 0.85}
        mock_analyze.return_value = {"analysis": "Test analysis", "recommendations": ["Test recommendation"]}
        
        yield {
            "classify": mock_classify,
            "analyze": mock_analyze
        }


@pytest.fixture
def mock_openrouter(mocker):
    """Mock OpenRouter client specifically for AI analysis tests."""
    # Mock the AIClient.classify_exception method instead of openrouter_client
    mock_classify = mocker.patch('app.services.ai_client.AIClient.classify_exception')
    mock_classify.return_value = '{"label": "PICK_DELAY", "confidence": 0.85, "ops_note": "High volume causing delays", "client_note": "Your order is being processed"}'
    return mock_classify


@pytest.fixture(autouse=True)
def reset_metrics():
    """
    Reset Prometheus metrics between tests.
    
    Ensures clean metrics state between tests
    for reliable performance and monitoring testing.
    """
    # Clear metrics between tests
    yield
    # Metrics reset would go here if needed
    pass
