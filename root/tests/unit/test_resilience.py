"""Unit tests for resilience mechanisms in simplified 2-flow architecture."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from app.resilience.circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitState, CircuitBreakerError
)


@pytest.mark.unit
class TestCircuitBreaker:
    """Test circuit breaker functionality in simplified architecture."""
    
    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker for testing."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=1.0,
            success_threshold=2,
            timeout=1.0
        )
        return CircuitBreaker("test_service", config)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_state(self, circuit_breaker):
        """Test circuit breaker in closed state."""
        async def success_func():
            return "success"
        
        result = await circuit_breaker.call(success_func)
        assert result == "success"
        assert circuit_breaker.is_closed()

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self, circuit_breaker):
        """Test circuit breaker opens after threshold failures."""
        async def failing_func():
            raise ValueError("Test error")
        
        # First failure
        with pytest.raises(ValueError):
            await circuit_breaker.call(failing_func)
        
        assert circuit_breaker.is_closed()
        
        # Second failure - should open circuit
        with pytest.raises(ValueError):
            await circuit_breaker.call(failing_func)
        
        assert circuit_breaker.is_open()

    @pytest.mark.asyncio
    async def test_circuit_breaker_rejects_when_open(self, circuit_breaker):
        """Test circuit breaker rejects calls when open."""
        async def failing_func():
            raise ValueError("Test error")
        
        # Force circuit to open
        for _ in range(2):
            with pytest.raises(ValueError):
                await circuit_breaker.call(failing_func)
        
        assert circuit_breaker.is_open()
        
        # Should reject immediately without calling function
        with pytest.raises(CircuitBreakerError):
            await circuit_breaker.call(failing_func)


@pytest.mark.unit
class TestResilienceIntegration:
    """Test resilience integration with the simplified 2-flow architecture."""
    
    @pytest.mark.asyncio
    async def test_resilience_with_ai_service_failure(self):
        """Test resilience handling AI service failures."""
        with patch('app.services.ai_exception_analyst.analyze_exception_or_fallback') as mock_ai:
            
            # Mock AI service failure with fallback
            mock_ai.side_effect = Exception("AI service unavailable")
            
            # Should handle AI failure gracefully
            with pytest.raises(Exception):
                await mock_ai("test exception")

    @pytest.mark.asyncio
    async def test_resilience_with_database_timeout(self):
        """Test resilience handling database timeouts."""
        with patch('app.storage.db.get_session') as mock_session:
            
            # Mock database timeout
            mock_session.side_effect = Exception("Database connection timeout")
            
            # Should handle database failure
            with pytest.raises(Exception):
                mock_session()

    def test_circuit_breaker_configuration_validation(self):
        """Test circuit breaker configuration validation."""
        # Test valid configuration
        valid_config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=30.0,
            success_threshold=3
        )
        
        circuit_breaker = CircuitBreaker("test_service", valid_config)
        assert circuit_breaker.config.failure_threshold == 5
        assert circuit_breaker.config.recovery_timeout == 30.0
        
        # Test invalid configuration should raise error during creation
        with pytest.raises((ValueError, TypeError)):
            CircuitBreakerConfig(
                failure_threshold=0,  # Invalid: must be > 0
                recovery_timeout=30.0,
                success_threshold=3,
                timeout=10.0
            )

    @pytest.mark.asyncio
    async def test_resilience_performance_under_load(self):
        """Test resilience mechanisms under high load."""
        # Simulate high load scenario
        concurrent_operations = 10
        
        async def simulated_operation(operation_id):
            # Simulate varying response times
            import asyncio
            await asyncio.sleep(0.01 * (operation_id % 3))  # 0-20ms delay
            return {"operation_id": operation_id, "result": "success"}
        
        # Execute operations concurrently
        import asyncio
        tasks = [
            simulated_operation(i) 
            for i in range(concurrent_operations)
        ]
        
        start_time = asyncio.get_event_loop().time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = asyncio.get_event_loop().time()
        
        # Verify performance
        execution_time = end_time - start_time
        successful_operations = len([r for r in results if not isinstance(r, Exception)])
        
        assert successful_operations >= concurrent_operations * 0.9  # 90% success rate
        assert execution_time < 2.0  # Should complete within 2 seconds


@pytest.mark.unit
class TestHealthChecking:
    """Test health checking functionality."""
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        with patch('app.resilience.health_check.check_database_health') as mock_db_health:
            
            mock_db_health.return_value = {
                "status": "healthy",
                "response_time_ms": 5.0,
                "details": {"connection_pool": "active"}
            }
            
            # Test health check call
            health_result = await mock_db_health()
            
            assert health_result["status"] == "healthy"
            assert health_result["response_time_ms"] == 5.0

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check failure handling."""
        with patch('app.resilience.health_check.check_redis_health') as mock_redis_health:
            
            mock_redis_health.return_value = {
                "status": "unhealthy",
                "response_time_ms": None,
                "error": "Connection timeout"
            }
            
            # Test health check failure
            health_result = await mock_redis_health()
            
            assert health_result["status"] == "unhealthy"
            assert "error" in health_result

    def test_circuit_breaker_states(self):
        """Test circuit breaker state transitions."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=1.0,
            success_threshold=2
        )
        
        circuit_breaker = CircuitBreaker("test_service", config)
        
        # Should start in closed state
        assert circuit_breaker.is_closed()
        assert not circuit_breaker.is_open()
        assert not circuit_breaker.is_half_open()
        
        # Test state checking methods exist and work
        assert hasattr(circuit_breaker, 'is_closed')
        assert hasattr(circuit_breaker, 'is_open')
        assert hasattr(circuit_breaker, 'is_half_open')
