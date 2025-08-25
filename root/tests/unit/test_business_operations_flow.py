"""Unit tests for Business Operations Flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any
import sys


def reload_flow_module():
    """Helper to reload flow module with mocked Prefect decorators."""
    if 'flows.business_operations_flow' in sys.modules:
        del sys.modules['flows.business_operations_flow']
    
    with patch('prefect.task', lambda *args, **kwargs: lambda f: f), \
         patch('prefect.flow', lambda *args, **kwargs: lambda f: f), \
         patch('prefect.get_run_logger', lambda: MagicMock()):
        import flows.business_operations_flow
        return flows.business_operations_flow


# Mock Prefect before importing the flow module
with patch('prefect.task'), patch('prefect.flow'), patch('prefect.get_run_logger'):
    from flows.business_operations_flow import (
        monitor_order_fulfillment,
        identify_billable_orders,
        generate_invoices,
        validate_invoices,
        process_billing_adjustments,
        generate_business_metrics,
        business_operations_flow
    )


@pytest.mark.unit
class TestBusinessOperationsFlow:
    """Test cases for Business Operations Flow components."""
    
    @pytest.mark.asyncio
    async def test_monitor_order_fulfillment_success(self):
        """Test successful order fulfillment monitoring."""
        with patch('flows.business_operations_flow.get_session') as mock_session, \
             patch('flows.business_operations_flow.get_run_logger') as mock_logger:
            
            # Mock logger
            mock_logger.return_value = MagicMock()
            
            # Mock database session
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock order fulfillment data
            mock_db.execute.return_value.fetchall.return_value = [
                ("order-1", "completed", 120),  # order_id, status, fulfillment_time_minutes
                ("order-2", "in_progress", 45),
                ("order-3", "stalled", 180)
            ]
            
            # Import and test the actual function logic
            flow_module = reload_flow_module()
            
            result = await flow_module.monitor_order_fulfillment(tenant="test-tenant", lookback_hours=24)
            
            assert "orders_monitored" in result or "fulfillment_status" in result

    @pytest.mark.asyncio
    async def test_identify_billable_orders_success(self):
        """Test successful billable order identification."""
        with patch('flows.business_operations_flow.get_session') as mock_session, \
             patch('flows.business_operations_flow.get_run_logger') as mock_logger:
            
            # Mock logger
            mock_logger.return_value = MagicMock()
            
            # Mock database session
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock billable orders
            mock_orders = [
                MagicMock(order_id=f"order-{i}", total_amount_cents=1000 + i * 100)
                for i in range(5)
            ]
            
            mock_db.execute.return_value.scalars.return_value.all.return_value = mock_orders
            
            # Import and test the actual function logic
            flow_module = reload_flow_module()
            
            result = await flow_module.identify_billable_orders(tenant="test-tenant")
            
            assert "billable_orders_found" in result or "orders_identified" in result

    @pytest.mark.asyncio
    async def test_generate_invoices_success(self):
        """Test successful invoice generation."""
    @pytest.mark.asyncio
    @patch('flows.business_operations_flow.InvoiceGeneratorService')
    @patch('flows.business_operations_flow.get_session')
    @patch('flows.business_operations_flow.get_run_logger')
    async def test_generate_invoices_success(self, mock_logger, mock_session, mock_service):
        """Test successful invoice generation."""
        # Mock logger
        mock_logger.return_value = MagicMock()
        
        # Mock database session
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_db
        
        # Mock invoice generator service
        mock_generator = AsyncMock()
        mock_service.return_value = mock_generator
        mock_generator.generate_daily_invoices.return_value = {
            "invoices_generated": 5,
            "total_amount_cents": 15000,
            "invoice_ids": ["inv-1", "inv-2", "inv-3", "inv-4", "inv-5"]
        }
        
        # Mock billable orders data
        billable_orders = [
            {"order_id": "order_1", "amount": 250.00},
            {"order_id": "order_2", "amount": 300.00}
        ]
        
        # Import and test the actual function logic
        flow_module = reload_flow_module()
        
        result = await flow_module.generate_invoices(billable_orders=billable_orders, tenant="test-tenant")
        
        assert "invoices_generated" in result or "generation_status" in result

    @pytest.mark.asyncio
    async def test_validate_invoices_success(self):
        """Test successful invoice validation."""
        with patch('flows.business_operations_flow.get_session') as mock_session:
            
            # Mock database session
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock invoice validation data
            mock_invoices = [
                MagicMock(id=i, amount_cents=1000 + i * 100, status="pending")
                for i in range(3)
            ]
            
            mock_db.execute.return_value.scalars.return_value.all.return_value = mock_invoices
            
            result = await validate_invoices(tenant="test-tenant")
            
            assert "invoices_validated" in result or "validation_status" in result

    @pytest.mark.asyncio
    async def test_process_billing_adjustments_success(self):
        """Test successful billing adjustment processing."""
        with patch('flows.business_operations_flow.get_session') as mock_session:
            
            # Mock database session
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock pending adjustments
            mock_adjustments = [
                MagicMock(id=1, order_id="order-1", amount_cents=-100, reason="credit"),
                MagicMock(id=2, order_id="order-2", amount_cents=50, reason="additional_charge")
            ]
            
            mock_db.execute.return_value.scalars.return_value.all.return_value = mock_adjustments
            
            result = await process_billing_adjustments(tenant="test-tenant")
            
            assert "adjustments_processed" in result or "processing_status" in result

    @pytest.mark.asyncio
    async def test_generate_business_metrics_success(self):
        """Test successful business metrics generation."""
        with patch('flows.business_operations_flow.get_session') as mock_session:
            
            # Mock database session
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock business metrics data
            mock_db.execute.return_value.fetchone.return_value = (
                Decimal('15000.00'),  # total_revenue
                Decimal('2500.00'),   # total_adjustments
                150,                  # total_operations
                95.5                  # avg_order_value
            )
            
            result = await generate_business_metrics(tenant="test-tenant")
            
            assert "metrics_generated" in result or "business_metrics" in result

    @pytest.mark.asyncio
    async def test_business_operations_flow_complete(self):
        """Test complete business operations flow execution."""
        with patch('flows.business_operations_flow.monitor_order_fulfillment') as mock_monitor, \
             patch('flows.business_operations_flow.identify_billable_orders') as mock_identify, \
             patch('flows.business_operations_flow.generate_invoices') as mock_invoices, \
             patch('flows.business_operations_flow.validate_invoices') as mock_validate, \
             patch('flows.business_operations_flow.process_billing_adjustments') as mock_adjustments, \
             patch('flows.business_operations_flow.generate_business_metrics') as mock_metrics:
            
            # Mock task results
            mock_monitor.return_value = {"orders_monitored": 50}
            mock_identify.return_value = {"billable_orders_found": 45}
            mock_invoices.return_value = {"invoices_generated": 8}
            mock_validate.return_value = {"invoices_validated": 8}
            mock_adjustments.return_value = {"adjustments_processed": 2}
            mock_metrics.return_value = {"metrics_generated": True}
            
            # Execute flow
            result = await business_operations_flow(tenant="test-tenant")
            
            # Verify flow completion
            assert "status" in result or "orders_monitored" in result


@pytest.mark.unit
class TestBusinessOperationsFlowIntegration:
    """Integration-style unit tests for Business Operations Flow."""
    
    @pytest.mark.asyncio
    async def test_flow_handles_large_volume_processing(self):
        """Test flow handling large volume of daily operations."""
        with patch('flows.business_operations_flow.monitor_order_fulfillment') as mock_monitor, \
             patch('flows.business_operations_flow.generate_invoices') as mock_invoices:
            
            # Mock high-volume processing
            mock_monitor.return_value = {
                "orders_monitored": 10000,
                "completed_orders": 9800,
                "stalled_orders": 50,
                "processing_time_ms": 5000
            }
            
            mock_invoices.return_value = {
                "invoices_generated": 500,
                "total_amount_cents": 2500000,
                "processing_time_ms": 8000
            }
            
            result_monitor = await monitor_order_fulfillment(tenant="test-tenant")
            result_invoices = await generate_invoices(tenant="test-tenant")
            
            assert "orders_monitored" in result_monitor or "fulfillment_status" in result_monitor
            assert "invoices_generated" in result_invoices or "generation_status" in result_invoices

    @pytest.mark.asyncio
    async def test_flow_error_handling_and_recovery(self):
        """Test flow error handling and recovery mechanisms."""
        with patch('flows.business_operations_flow.get_session') as mock_session, \
             patch('flows.business_operations_flow.get_run_logger') as mock_logger:
            
            # Mock database connection failure
            mock_session.side_effect = Exception("Connection timeout")
            mock_logger_instance = MagicMock()
            mock_logger.return_value = mock_logger_instance
            
            with pytest.raises(Exception):
                await monitor_order_fulfillment(tenant="test-tenant")
            
            # Verify error was logged
            mock_logger.assert_called()
