"""Performance smoke tests to detect regressions."""

import pytest
import asyncio
from datetime import datetime, timezone
from statistics import mean, median


@pytest.mark.perf
@pytest.mark.slow
class TestPerformance:
    """Performance smoke tests with latency targets."""
    
    @pytest.mark.asyncio
    async def test_event_ingestion_latency(self, client, tenant_headers, performance_timer):
        """Test event ingestion latency meets SLA."""
        event_data = {
            "source": "shopify",
            "event_type": "order_paid",
            "event_id": "evt-perf-001",
            "order_id": "order-perf-001",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"total_amount_cents": 2999}
        }
        
        performance_timer.start()
        response = await client.post("/ingest/shopify", headers=tenant_headers, json=event_data)
        performance_timer.stop()
        
        assert response.status_code == 200
        
        # Target: < 200ms p95
        latency_ms = performance_timer.elapsed_ms()
        assert latency_ms < 200, f"Event ingestion took {latency_ms}ms, target is <200ms"
    
    @pytest.mark.asyncio
    async def test_event_ingestion_throughput(self, client, tenant_headers):
        """Test event ingestion throughput under load."""
        num_events = 50
        events = []
        
        # Prepare events
        for i in range(num_events):
            event = {
                "source": "shopify",
                "event_type": "order_paid",
                "event_id": f"evt-throughput-{i:03d}",
                "order_id": f"order-throughput-{i:03d}",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"total_amount_cents": 2999}
            }
            events.append(event)
        
        # Send events concurrently
        start_time = asyncio.get_event_loop().time()
        
        async def send_event(event):
            response = await client.post("/ingest/shopify", headers=tenant_headers, json=event)
            return response.status_code == 200
        
        tasks = [send_event(event) for event in events]
        results = await asyncio.gather(*tasks)
        
        end_time = asyncio.get_event_loop().time()
        duration_seconds = end_time - start_time
        
        # All events should succeed
        assert all(results), "Some events failed during throughput test"
        
        # Calculate throughput
        throughput = num_events / duration_seconds
        
        # Target: > 20 events/second
        assert throughput > 20, f"Throughput was {throughput:.1f} events/sec, target is >20/sec"
    
    @pytest.mark.skip(reason="SLA evaluation requires real database and timing")
    @pytest.mark.asyncio
    async def test_sla_evaluation_latency(self, client, tenant_headers, performance_timer, base_time):
        """Test SLA evaluation latency when breach is detected."""
        order_id = "order-sla-perf-001"
        
        # First event: order paid
        order_paid = {
            "source": "shopify",
            "event_type": "order_paid",
            "event_id": "evt-sla-perf-001",
            "order_id": order_id,
            "occurred_at": base_time.isoformat(),
            "payload": {"total_amount_cents": 2999}
        }
        
        response = await client.post("/ingest/shopify", headers=tenant_headers, json=order_paid)
        assert response.status_code == 200
        
        # Second event: pick completed late (triggers SLA evaluation)
        from datetime import timedelta
        pick_completed = {
            "source": "wms",
            "event_type": "pick_completed",
            "event_id": "evt-sla-perf-002",
            "order_id": order_id,
            "occurred_at": (base_time + timedelta(hours=3)).isoformat(),
            "payload": {"station": "PICK-01"}
        }
        
        performance_timer.start()
        response = await client.post("/ingest/wms", headers=tenant_headers, json=pick_completed)
        performance_timer.stop()
        
        assert response.status_code == 200
        assert response.json().get("exception_created") is True
        
        # Target: < 100ms p95 for SLA evaluation
        latency_ms = performance_timer.elapsed_ms()
        assert latency_ms < 100, f"SLA evaluation took {latency_ms}ms, target is <100ms"
    
    @pytest.mark.asyncio
    async def test_exception_retrieval_latency(self, client, tenant_headers, performance_timer):
        """Test exception list retrieval latency."""
        performance_timer.start()
        response = await client.get("/exceptions", headers=tenant_headers)
        performance_timer.stop()
        
        assert response.status_code == 200
        
        # Target: < 100ms p95 (relaxed for test environment)
        latency_ms = performance_timer.elapsed_ms()
        assert latency_ms < 100, f"Exception retrieval took {latency_ms}ms, target is <100ms"
    
    @pytest.mark.asyncio
    async def test_exception_retrieval_with_pagination(self, client, tenant_headers, performance_timer):
        """Test exception retrieval with pagination parameters."""
        params = {
            "page": 1,
            "page_size": 20,
            "status": "OPEN",
            "severity": "HIGH"
        }
        
        performance_timer.start()
        response = await client.get("/exceptions", headers=tenant_headers, params=params)
        performance_timer.stop()
        
        assert response.status_code == 200
        
        # Target: < 150ms p95 with filters (relaxed for test environment)
        latency_ms = performance_timer.elapsed_ms()
        assert latency_ms < 150, f"Filtered exception retrieval took {latency_ms}ms, target is <150ms"
    
    @pytest.mark.asyncio
    async def test_health_check_latency(self, client, performance_timer):
        """Test health check endpoint latency."""
        performance_timer.start()
        response = await client.get("/healthz")
        performance_timer.stop()
        
        assert response.status_code == 200
        
        # Target: < 50ms p95 (relaxed for test environment)
        latency_ms = performance_timer.elapsed_ms()
        assert latency_ms < 50, f"Health check took {latency_ms}ms, target is <50ms"
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint_latency(self, client, performance_timer):
        """Test metrics endpoint latency."""
        performance_timer.start()
        response = await client.get("/metrics")
        performance_timer.stop()
        
        assert response.status_code == 200
        
        # Target: < 100ms p95 (relaxed for test environment)
        latency_ms = performance_timer.elapsed_ms()
        assert latency_ms < 100, f"Metrics endpoint took {latency_ms}ms, target is <100ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_different_tenants(self, client):
        """Test concurrent requests from different tenants."""
        num_tenants = 10
        events_per_tenant = 5
        
        async def send_tenant_events(tenant_id):
            headers = {"X-Tenant-Id": f"tenant-{tenant_id}", "Content-Type": "application/json"}
            latencies = []
            
            for i in range(events_per_tenant):
                event = {
                    "source": "shopify",
                    "event_type": "order_paid",
                    "event_id": f"evt-tenant-{tenant_id}-{i}",
                    "order_id": f"order-tenant-{tenant_id}-{i}",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"total_amount_cents": 1999}
                }
                
                start_time = asyncio.get_event_loop().time()
                response = await client.post("/ingest/shopify", headers=headers, json=event)
                end_time = asyncio.get_event_loop().time()
                
                assert response.status_code == 200
                latencies.append((end_time - start_time) * 1000)  # Convert to ms
            
            return latencies
        
        # Run concurrent tenant operations
        tasks = [send_tenant_events(i) for i in range(num_tenants)]
        all_latencies = await asyncio.gather(*tasks)
        
        # Flatten latencies
        flat_latencies = [latency for tenant_latencies in all_latencies for latency in tenant_latencies]
        
        # Calculate statistics
        avg_latency = mean(flat_latencies)
        p95_latency = sorted(flat_latencies)[int(0.95 * len(flat_latencies))]
        
        # Targets under concurrent load
        assert avg_latency < 300, f"Average latency under load: {avg_latency:.1f}ms, target <300ms"
        assert p95_latency < 500, f"P95 latency under load: {p95_latency:.1f}ms, target <500ms"
    
    @pytest.mark.asyncio
    async def test_database_query_performance(self, client, tenant_headers, db_session):
        """Test database query performance for complex operations."""
        from sqlalchemy import select, func
        from app.storage.models import OrderEvent, ExceptionRecord
        
        # Test complex query performance
        start_time = asyncio.get_event_loop().time()
        
        # Complex query: count events by type and tenant
        query = (
            select(OrderEvent.event_type, func.count(OrderEvent.id))
            .where(OrderEvent.tenant == "test-tenant")
            .group_by(OrderEvent.event_type)
        )
        
        result = await db_session.execute(query)
        event_counts = result.all()
        
        end_time = asyncio.get_event_loop().time()
        query_time_ms = (end_time - start_time) * 1000
        
        # Target: < 100ms for aggregation queries (relaxed for test environment)
        assert query_time_ms < 100, f"Database aggregation took {query_time_ms:.1f}ms, target <100ms"
    
    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, client, tenant_headers):
        """Test that memory usage remains stable under load."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Send many events to test memory stability
        for i in range(100):
            event = {
                "source": "shopify",
                "event_type": "order_paid",
                "event_id": f"evt-memory-{i:03d}",
                "order_id": f"order-memory-{i:03d}",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"total_amount_cents": 2999, "large_data": "x" * 1000}
            }
            
            response = await client.post("/ingest/shopify", headers=tenant_headers, json=event)
            assert response.status_code == 200
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Memory should not increase significantly (< 50MB increase)
        assert memory_increase < 50, f"Memory increased by {memory_increase:.1f}MB, target <50MB"
    
    @pytest.mark.asyncio
    async def test_error_handling_performance(self, client, tenant_headers, performance_timer):
        """Test that error handling doesn't significantly impact performance."""
        # Send invalid event that will trigger validation error
        invalid_event = {
            "source": "shopify",
            "event_type": "invalid_type",
            "event_id": "evt-error-001",
            # Missing required fields
        }
        
        performance_timer.start()
        response = await client.post("/ingest/shopify", headers=tenant_headers, json=invalid_event)
        performance_timer.stop()
        
        assert response.status_code == 422  # Validation error
        
        # Error handling should still be fast
        latency_ms = performance_timer.elapsed_ms()
        assert latency_ms < 100, f"Error handling took {latency_ms}ms, target <100ms"
    
    @pytest.mark.skip(reason="Duplicate detection requires real database")
    @pytest.mark.asyncio
    async def test_duplicate_detection_performance(self, client, tenant_headers, performance_timer):
        """Test duplicate detection performance."""
        event_data = {
            "source": "shopify",
            "event_type": "order_paid",
            "event_id": "evt-duplicate-perf-001",
            "order_id": "order-duplicate-perf-001",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"total_amount_cents": 2999}
        }
        
        # Send event first time
        response = await client.post("/ingest/shopify", headers=tenant_headers, json=event_data)
        assert response.status_code == 200
        
        # Send duplicate - measure duplicate detection time
        performance_timer.start()
        response = await client.post("/ingest/shopify", headers=tenant_headers, json=event_data)
        performance_timer.stop()
        
        assert response.status_code == 200
        assert response.json()["status"] == "duplicate"
        
        # Duplicate detection should be fast
        latency_ms = performance_timer.elapsed_ms()
        assert latency_ms < 50, f"Duplicate detection took {latency_ms}ms, target <50ms"
    
    @pytest.mark.skip(reason="AI timeout handling is environment-dependent")
    @pytest.mark.asyncio
    async def test_ai_analysis_timeout_handling(self, client, tenant_headers, base_time):
        """Test AI analysis timeout doesn't block request processing."""
        from unittest.mock import patch, AsyncMock
        import httpx
        
        order_id = "order-ai-timeout-001"
        
        # Mock AI client to return timeout response
        async def mock_classify_exception(*args, **kwargs):
            raise httpx.TimeoutException("AI service timeout")
        
        with patch('app.services.ai_client.get_ai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.classify_exception.side_effect = mock_classify_exception
            mock_get_client.return_value = mock_client
            
            # Order paid
            order_paid = {
                "source": "shopify",
                "event_type": "order_paid",
                "event_id": "evt-ai-timeout-001",
                "order_id": order_id,
                "occurred_at": base_time.isoformat(),
                "payload": {"total_amount_cents": 2999}
            }
            
            response = await client.post("/ingest/shopify", headers=tenant_headers, json=order_paid)
            assert response.status_code == 200
            
            # Pick completed late (should trigger AI analysis with timeout)
            from datetime import timedelta
            pick_completed = {
                "source": "wms",
                "event_type": "pick_completed",
                "event_id": "evt-ai-timeout-002",
                "order_id": order_id,
                "occurred_at": (base_time + timedelta(hours=3)).isoformat(),
                "payload": {"station": "PICK-01"}
            }
            
            start_time = asyncio.get_event_loop().time()
            response = await client.post("/ingest/wms", headers=tenant_headers, json=pick_completed)
            end_time = asyncio.get_event_loop().time()
            
            assert response.status_code == 200
            assert response.json().get("exception_created") is True
            
            # Should complete quickly despite AI timeout (fallback to rule-based)
            request_time_ms = (end_time - start_time) * 1000
            assert request_time_ms < 1000, f"Request with AI timeout took {request_time_ms:.1f}ms, target <1000ms"
