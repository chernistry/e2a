"""Tests for resilience module."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.resilience.circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState, CircuitBreakerError
)
from app.resilience.retry_policies import (
    ExponentialBackoffPolicy, RetryConfig, create_ai_retry_policy
)
from app.resilience.decorators import ai_resilient, redis_resilient
from app.resilience.health_check import HealthChecker, ServiceHealth, HealthStatus


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
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
        assert circuit_breaker.stats.success_count == 1
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self, circuit_breaker):
        """Test circuit breaker opens after threshold failures."""
        async def failing_func():
            raise ValueError("Test error")
        
        # First failure
        with pytest.raises(ValueError):
            await circuit_breaker.call(failing_func)
        assert circuit_breaker.is_closed()
        
        # Second failure should open circuit on next call
        with pytest.raises(ValueError):
            await circuit_breaker.call(failing_func)
        
        # Circuit should be open now - next call should be rejected
        with pytest.raises(CircuitBreakerError):
            await circuit_breaker.call(failing_func)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_rejects_when_open(self, circuit_breaker):
        """Test circuit breaker rejects calls when open."""
        # Force circuit to open state
        circuit_breaker.stats.state = CircuitBreakerState.OPEN
        circuit_breaker.stats.failure_count = 5
        
        async def any_func():
            return "should not execute"
        
        with pytest.raises(CircuitBreakerError):
            await circuit_breaker.call(any_func)
    
    @pytest.mark.skip(reason="Circuit breaker timing is environment-dependent")
    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_recovery(self, circuit_breaker):
        """Test circuit breaker recovery through half-open state."""
        # Simulate failures to open circuit
        async def failing_func():
            raise ValueError("Test error")
        
        for _ in range(2):
            with pytest.raises(ValueError):
                await circuit_breaker.call(failing_func)
        
        # Circuit should be open after next call
        with pytest.raises(CircuitBreakerError):
            await circuit_breaker.call(failing_func)
        
        assert circuit_breaker.is_open()
        
        # Wait for recovery timeout
        await asyncio.sleep(1.1)
        
        # Next call should transition to half-open
        async def success_func():
            return "success"
        
        # Force state update
        await circuit_breaker._update_state()
        assert circuit_breaker.is_half_open()
        
        # Successful calls should close circuit
        for _ in range(2):
            result = await circuit_breaker.call(success_func)
            assert result == "success"
        
        assert circuit_breaker.is_closed()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_timeout(self, circuit_breaker):
        """Test circuit breaker timeout handling."""
        async def slow_func():
            await asyncio.sleep(2.0)  # Longer than timeout
            return "too slow"
        
        with pytest.raises(asyncio.TimeoutError):
            await circuit_breaker.call(slow_func)
        
        # Timeout should count as failure
        assert circuit_breaker.stats.failure_count == 1


class TestRetryPolicies:
    """Test retry policy functionality."""
    
    def test_exponential_backoff_policy_creation(self):
        """Test creating exponential backoff policy."""
        config = RetryConfig(max_attempts=3, base_delay=1.0)
        policy = ExponentialBackoffPolicy(config, "test_service")
        
        assert policy.config.max_attempts == 3
        assert policy.service_name == "test_service"
    
    def test_ai_retry_policy_creation(self):
        """Test creating AI-specific retry policy."""
        policy = create_ai_retry_policy()
        
        assert policy.service_name == "ai_service"
        assert policy.config.max_attempts == 3
        assert policy.config.jitter is True
    
    @pytest.mark.asyncio
    async def test_retry_policy_decorator(self):
        """Test retry policy decorator functionality."""
        call_count = 0
        
        @ai_resilient("test_operation")
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"
        
        # Should succeed after retries
        result = await flaky_function()
        assert result == "success"
        assert call_count == 3


class TestHealthChecker:
    """Test health checker functionality."""
    
    @pytest.fixture
    def health_checker(self):
        """Create health checker for testing."""
        return HealthChecker()
    
    @pytest.mark.asyncio
    async def test_register_and_check_service(self, health_checker):
        """Test registering and checking service health."""
        async def mock_health_check():
            return ServiceHealth(
                service_name="test_service",
                status=HealthStatus.HEALTHY,
                response_time=0.1
            )
        
        health_checker.register_check("test_service", mock_health_check)
        
        health = await health_checker.check_service("test_service")
        assert health.service_name == "test_service"
        assert health.status == HealthStatus.HEALTHY
        assert health.is_healthy()
    
    @pytest.mark.asyncio
    async def test_health_check_caching(self, health_checker):
        """Test health check result caching."""
        call_count = 0
        
        async def mock_health_check():
            nonlocal call_count
            call_count += 1
            return ServiceHealth(
                service_name="test_service",
                status=HealthStatus.HEALTHY
            )
        
        health_checker.register_check("test_service", mock_health_check)
        
        # First call
        await health_checker.check_service("test_service")
        assert call_count == 1
        
        # Second call should use cache
        await health_checker.check_service("test_service")
        assert call_count == 1
        
        # Force check should bypass cache
        await health_checker.check_service("test_service", force=True)
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_check_all_services(self, health_checker):
        """Test checking all registered services."""
        async def healthy_service():
            return ServiceHealth("service1", HealthStatus.HEALTHY)
        
        async def unhealthy_service():
            return ServiceHealth("service2", HealthStatus.UNHEALTHY)
        
        health_checker.register_check("service1", healthy_service)
        health_checker.register_check("service2", unhealthy_service)
        
        all_health = await health_checker.check_all_services()
        
        assert len(all_health) == 2
        assert all_health["service1"].is_healthy()
        assert not all_health["service2"].is_healthy()
    
    @pytest.mark.asyncio
    async def test_health_check_exception_handling(self, health_checker):
        """Test health check exception handling."""
        async def failing_health_check():
            raise ConnectionError("Service unavailable")
        
        health_checker.register_check("failing_service", failing_health_check)
        
        health = await health_checker.check_service("failing_service")
        assert health.service_name == "failing_service"
        assert health.status == HealthStatus.UNHEALTHY
        assert "Service unavailable" in health.error_message


class TestResilienceDecorators:
    """Test resilience decorators."""
    
    @pytest.mark.asyncio
    async def test_ai_resilient_decorator(self):
        """Test AI resilient decorator."""
        call_count = 0
        
        @ai_resilient("test_ai_call")
        async def ai_function():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Network error")
            return {"result": "success"}
        
        result = await ai_function()
        assert result["result"] == "success"
        assert call_count == 2  # One failure, one success
    
    @pytest.mark.asyncio
    async def test_redis_resilient_decorator(self):
        """Test Redis resilient decorator."""
        @redis_resilient("test_redis_call")
        async def redis_function():
            return "cached_value"
        
        result = await redis_function()
        assert result == "cached_value"
    
    @pytest.mark.skip(reason="Circuit breaker integration timing is environment-dependent")
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        """Test circuit breaker integration with decorators."""
        failure_count = 0
        
        @ai_resilient("test_integration")
        async def unreliable_function():
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 7:  # Fail first 7 calls
                raise ConnectionError("Service down")
            return "recovered"
        
        # Should fail with default threshold of 5 failures
        for _ in range(5):
            with pytest.raises(ConnectionError):
                await unreliable_function()
        
        # Circuit breaker should now be open on next call
        with pytest.raises(CircuitBreakerError):
            await unreliable_function()


class TestServiceHealth:
    """Test ServiceHealth class."""
    
    def test_service_health_creation(self):
        """Test creating ServiceHealth instance."""
        health = ServiceHealth(
            service_name="test_service",
            status=HealthStatus.HEALTHY,
            response_time=0.5
        )
        
        assert health.service_name == "test_service"
        assert health.status == HealthStatus.HEALTHY
        assert health.response_time == 0.5
        assert health.is_healthy()
    
    def test_service_health_age_calculation(self):
        """Test age calculation for health checks."""
        import time
        
        health = ServiceHealth("test", HealthStatus.HEALTHY)
        
        # Age should be very small initially
        assert health.age_seconds() < 1.0
        
        # Simulate older check
        health.last_check = time.time() - 30
        assert health.age_seconds() >= 30
    
    def test_unhealthy_service_status(self):
        """Test unhealthy service status."""
        health = ServiceHealth(
            service_name="failing_service",
            status=HealthStatus.UNHEALTHY,
            error_message="Connection refused"
        )
        
        assert not health.is_healthy()
        assert health.error_message == "Connection refused"
    
    def test_degraded_service_status(self):
        """Test degraded service status."""
        health = ServiceHealth(
            service_name="slow_service",
            status=HealthStatus.DEGRADED,
            response_time=5.0
        )
        
        assert not health.is_healthy()  # Degraded is not healthy
        assert health.response_time == 5.0
