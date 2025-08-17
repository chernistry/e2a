"""Unit tests for idempotency service functionality."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.idempotency import IdempotencyService, get_idempotency_service


@pytest.mark.unit
@pytest.mark.redis
class TestIdempotencyService:
    """Test cases for idempotency service."""
    
    @pytest.fixture
    def idempotency_service(self):
        """Create idempotency service instance."""
        return IdempotencyService("redis://localhost:6379")
    
    @pytest.fixture
    def sample_event_data(self):
        """Sample event data for testing."""
        return {
            "tenant": "test-tenant",
            "source": "shopify",
            "event_id": "evt-12345"
        }

    def test_idempotency_key_generation(self, idempotency_service):
        """Test idempotency key generation."""
        key = idempotency_service._idempotency_key("test-tenant", "shopify", "evt-12345")
        
        assert key == "idempo:test-tenant:shopify:evt-12345"

    def test_lock_key_generation(self, idempotency_service):
        """Test lock key generation."""
        key = idempotency_service._lock_key("test-tenant", "shopify", "evt-12345")
        
        assert key == "lock:idempo:test-tenant:shopify:evt-12345"

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, idempotency_service):
        """Test successful lock acquisition."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.set.return_value = True
            mock_get_redis.return_value = mock_redis
            
            result = await idempotency_service.acquire_lock("test-tenant", "shopify", "evt-12345")
            
            assert result is True
            mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_lock_failure(self, idempotency_service):
        """Test failed lock acquisition."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.set.return_value = None  # Lock already exists
            mock_get_redis.return_value = mock_redis
            
            result = await idempotency_service.acquire_lock("test-tenant", "shopify", "evt-12345")
            
            assert result is False

    @pytest.mark.asyncio
    async def test_release_lock(self, idempotency_service):
        """Test lock release."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            
            await idempotency_service.release_lock("test-tenant", "shopify", "evt-12345")
            
            mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_processed_true(self, idempotency_service):
        """Test checking if event is already processed (true case)."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.exists.return_value = 1  # Key exists
            mock_get_redis.return_value = mock_redis
            
            result = await idempotency_service.is_processed("test-tenant", "shopify", "evt-12345")
            
            assert result is True

    @pytest.mark.asyncio
    async def test_is_processed_false(self, idempotency_service):
        """Test checking if event is already processed (false case)."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.exists.return_value = 0  # Key doesn't exist
            mock_get_redis.return_value = mock_redis
            
            result = await idempotency_service.is_processed("test-tenant", "shopify", "evt-12345")
            
            assert result is False

    @pytest.mark.asyncio
    async def test_mark_processed(self, idempotency_service):
        """Test marking event as processed."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            
            await idempotency_service.mark_processed("test-tenant", "shopify", "evt-12345")
            
            mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_processed_custom_ttl(self, idempotency_service):
        """Test marking event as processed with custom TTL."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            
            await idempotency_service.mark_processed("test-tenant", "shopify", "evt-12345", ttl_seconds=3600)
            
            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            assert call_args[1]['ex'] == 3600  # TTL should be 3600 seconds

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, idempotency_service):
        """Test cleanup of expired keys."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.keys.return_value = ["key1", "key2", "key3"]
            mock_redis.ttl.side_effect = [-2, 100, -2]  # key1 and key3 are expired
            mock_get_redis.return_value = mock_redis
            
            result = await idempotency_service.cleanup_expired()
            
            assert result == 2  # Two expired keys

    @pytest.mark.asyncio
    async def test_close_connection(self, idempotency_service):
        """Test closing Redis connection."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            idempotency_service._redis = mock_redis
            
            await idempotency_service.close()
            
            mock_redis.close.assert_called_once()
            assert idempotency_service._redis is None

    def test_get_idempotency_service_singleton(self):
        """Test idempotency service singleton pattern."""
        service1 = get_idempotency_service()
        service2 = get_idempotency_service()
        
        assert service1 is service2  # Should be the same instance

    @pytest.mark.asyncio
    async def test_concurrent_lock_acquisition(self, idempotency_service):
        """Test concurrent lock acquisition."""
        with patch.object(idempotency_service, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            # First call succeeds, second fails
            mock_redis.set.side_effect = [True, None]
            mock_get_redis.return_value = mock_redis
            
            # Simulate concurrent requests
            tasks = [
                idempotency_service.acquire_lock("test-tenant", "shopify", "evt-12345"),
                idempotency_service.acquire_lock("test-tenant", "shopify", "evt-12345")
            ]
            
            results = await asyncio.gather(*tasks)
            
            # One should succeed, one should fail
            assert True in results
            assert False in results
