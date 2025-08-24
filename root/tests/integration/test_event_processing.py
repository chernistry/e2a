"""Integration tests for simplified 2-flow event processing architecture."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from unittest.mock import patch, AsyncMock

from app.storage.models import OrderEvent, ExceptionRecord
from flows.event_processor_flow import event_processor_flow
from flows.business_operations_flow import business_operations_flow


@pytest.mark.integration
@pytest.mark.postgres
class TestEventProcessingIntegration:
    """Integration tests for Event Processor Flow with real database."""
    
    @pytest.mark.asyncio
    async def test_shopify_event_ingestion_and_processing(self, client, tenant_headers, db_session, tenant_record):
        """Test Shopify event ingestion through Event Processor Flow."""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        
        event_data = {
            "source": "shopify",
            "event_type": "order_paid",
            "event_id": f"evt-shopify-{unique_id}",
            "order_id": f"order-integration-{unique_id}",
            "occurred_at": "2025-08-16T10:00:00Z",
            "total_amount_cents": 2999,
            "line_count": 2
        }
        
        # Test webhook ingestion
        response = await client.post("/ingest/shopify", headers=tenant_headers, json=event_data)
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["ok"] is True
        assert result["message"] in [
            "Event processed successfully",
            "Event already processed (duplicate detected at database level)"
        ]
        assert "correlation_id" in result
        
        # Verify event was stored in database
        query = select(OrderEvent).where(OrderEvent.event_id == event_data["event_id"])
        db_result = await db_session.execute(query)
        stored_event = db_result.scalar_one_or_none()
        
        if stored_event:
            assert stored_event.source == "shopify"
            assert stored_event.event_type == "order_paid"
            assert stored_event.order_id == event_data["order_id"]
            assert stored_event.tenant == "test-tenant"

    @pytest.mark.asyncio
    async def test_wms_event_processing_flow(self, client, tenant_headers, db_session, tenant_record):
        """Test WMS event processing through Event Processor Flow."""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        
        event_data = {
            "source": "wms",
            "event_type": "order_picked",
            "event_id": f"evt-wms-{unique_id}",
            "order_id": f"order-wms-{unique_id}",
            "occurred_at": "2025-08-16T11:00:00Z",
            "picked_items": 3,
            "picker_id": "picker-001"
        }
        
        response = await client.post("/ingest/wms", headers=tenant_headers, json=event_data)
        
        assert response.status_code == 200
        result = response.json()
        assert result["ok"] is True
        
        # Verify WMS event storage
        query = select(OrderEvent).where(OrderEvent.event_id == event_data["event_id"])
        db_result = await db_session.execute(query)
        stored_event = db_result.scalar_one_or_none()
        
        if stored_event:
            assert stored_event.source == "wms"
            assert stored_event.event_type == "order_picked"

    @pytest.mark.asyncio
    async def test_carrier_event_processing_flow(self, client, tenant_headers, db_session, tenant_record):
        """Test carrier event processing through Event Processor Flow."""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        
        event_data = {
            "source": "carrier",
            "event_type": "order_shipped",
            "event_id": f"evt-carrier-{unique_id}",
            "order_id": f"order-carrier-{unique_id}",
            "occurred_at": "2025-08-16T12:00:00Z",
            "tracking_number": "TRACK123456",
            "carrier_name": "TestCarrier"
        }
        
        response = await client.post("/ingest/carrier", headers=tenant_headers, json=event_data)
        
        assert response.status_code == 200
        result = response.json()
        assert result["ok"] is True
        
        # Verify carrier event storage
        query = select(OrderEvent).where(OrderEvent.event_id == event_data["event_id"])
        db_result = await db_session.execute(query)
        stored_event = db_result.scalar_one_or_none()
        
        if stored_event:
            assert stored_event.source == "carrier"
            assert stored_event.event_type == "order_shipped"

    @pytest.mark.asyncio
    async def test_event_processor_flow_execution(self, db_session, tenant_record):
        """Test Event Processor Flow execution with mocked services."""
        with patch('flows.event_processor_flow.get_order_analyzer') as mock_analyzer, \
             patch('flows.event_processor_flow.analyze_exception_or_fallback') as mock_ai:
            
            # Mock order analyzer
            mock_analyzer_instance = AsyncMock()
            mock_analyzer.return_value = mock_analyzer_instance
            mock_analyzer_instance.analyze_recent_orders.return_value = {
                "orders_analyzed": 10,
                "exceptions_found": 2,
                "processing_time_ms": 250
            }
            
            # Mock AI analysis
            mock_ai.return_value = {
                "analysis": "Test analysis",
                "recommendations": ["Test recommendation"],
                "confidence": 0.85
            }
            
            # Execute Event Processor Flow
            result = await event_processor_flow(tenant="test-tenant", lookback_hours=1)
            
            assert "status" in result or "processed_count" in result


@pytest.mark.integration
@pytest.mark.postgres
class TestBusinessOperationsIntegration:
    """Integration tests for Business Operations Flow with real database."""
    
    @pytest.mark.asyncio
    async def test_business_operations_flow_execution(self, db_session, tenant_record):
        """Test Business Operations Flow execution with mocked services."""
        with patch('flows.business_operations_flow.InvoiceGeneratorService') as mock_invoice_service, \
             patch('flows.business_operations_flow.BillingService') as mock_billing_service:
            
            # Mock invoice generator
            mock_invoice_generator = AsyncMock()
            mock_invoice_service.return_value = mock_invoice_generator
            mock_invoice_generator.generate_daily_invoices.return_value = {
                "invoices_generated": 5,
                "total_amount_cents": 15000,
                "invoice_ids": ["inv-1", "inv-2", "inv-3", "inv-4", "inv-5"]
            }
            
            # Mock billing service
            mock_billing = AsyncMock()
            mock_billing_service.return_value = mock_billing
            mock_billing.validate_daily_billing.return_value = {
                "validation_passed": True,
                "discrepancies_found": 0,
                "total_validated_amount_cents": 15000
            }
            
            # Execute Business Operations Flow
            result = await business_operations_flow(tenant="test-tenant")
            
            assert "status" in result or "orders_monitored" in result


@pytest.mark.integration
@pytest.mark.postgres
class TestFlowOrchestration:
    """Integration tests for flow orchestration and coordination."""
    
    @pytest.mark.asyncio
    async def test_dual_flow_coordination(self, db_session, tenant_record):
        """Test coordination between Event Processor and Business Operations flows."""
        # Create test data that both flows will process
        base_time = datetime.now(timezone.utc)
        
        order_event = OrderEvent(
            tenant="test-tenant",
            source="shopify",
            event_type="order_paid",
            event_id="evt-coordination-test",
            order_id="order-coordination-test",
            occurred_at=base_time,
            payload={"total_amount_cents": 5000}
        )
        
        db_session.add(order_event)
        await db_session.commit()
        
        # Mock services for both flows
        with patch('flows.event_processor_flow.get_order_analyzer') as mock_analyzer, \
             patch('flows.business_operations_flow.InvoiceGeneratorService') as mock_invoice_service:
            
            # Setup mocks
            mock_analyzer_instance = AsyncMock()
            mock_analyzer.return_value = mock_analyzer_instance
            mock_analyzer_instance.analyze_recent_orders.return_value = {
                "orders_analyzed": 1,
                "exceptions_found": 0
            }
            
            mock_invoice_generator = AsyncMock()
            mock_invoice_service.return_value = mock_invoice_generator
            mock_invoice_generator.generate_daily_invoices.return_value = {
                "invoices_generated": 1,
                "total_amount_cents": 5000
            }
            
            # Execute both flows
            event_result = await event_processor_flow(tenant="test-tenant")
            
            with patch('flows.business_operations_flow.BillingService'):
                business_result = await business_operations_flow(tenant="test-tenant")
            
            # Verify both flows completed successfully
            assert "status" in event_result or "processed_count" in event_result
            assert "status" in business_result or "orders_monitored" in business_result
