"""Unit tests for Event Processor Flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from flows.event_processor_flow import (
    analyze_order_events,
    process_sla_evaluations,
    process_ai_analysis_queue,
    event_processor_flow
)


@pytest.mark.unit
class TestEventProcessorFlow:
    """Test cases for Event Processor Flow components."""
    
    @pytest.mark.asyncio
    async def test_analyze_order_events_success(self):
        """Test successful order event analysis."""
        with patch('flows.event_processor_flow.get_session') as mock_session, \
             patch('flows.event_processor_flow.get_order_analyzer') as mock_analyzer:
            
            # Mock database session
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock query result
            mock_db.execute.return_value.scalars.return_value.all.return_value = []
            
            # Mock order analyzer
            mock_analyzer_instance = AsyncMock()
            mock_analyzer.return_value = mock_analyzer_instance
            
            result = await analyze_order_events(tenant="test-tenant", lookback_hours=1)
            
            assert "processed_count" in result or "events_found" in result
            mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_process_sla_evaluations_success(self):
        """Test successful SLA evaluation processing."""
        with patch('flows.event_processor_flow.get_session') as mock_session, \
             patch('flows.event_processor_flow.evaluate_sla') as mock_sla:
            
            # Mock database session
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock SLA evaluation
            mock_sla.return_value = {
                "sla_met": True,
                "processing_time_minutes": 45,
                "sla_threshold_minutes": 60
            }
            
            result = await process_sla_evaluations(tenant="test-tenant")
            
            assert "evaluations_processed" in result or "sla_violations" in result

    @pytest.mark.asyncio
    async def test_process_ai_analysis_queue_success(self):
        """Test successful AI analysis queue processing."""
        with patch('flows.event_processor_flow.get_session') as mock_session, \
             patch('flows.event_processor_flow.analyze_exception_or_fallback') as mock_ai:
            
            # Mock database session
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock exception records
            mock_exception = MagicMock()
            mock_exception.id = 1
            mock_exception.order_id = "order-123"
            mock_exception.exception_type = "PICK_DELAY"
            mock_exception.context = {"delay_minutes": 45}
            
            mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_exception]
            
            # Mock AI analysis
            mock_ai.return_value = {
                "analysis": "High volume causing delays",
                "recommendations": ["Increase picker capacity"],
                "confidence": 0.85
            }
            
            result = await process_ai_analysis_queue(tenant="test-tenant")
            
            assert "analyses_completed" in result or "exceptions_processed" in result

    @pytest.mark.asyncio
    async def test_event_processor_flow_complete(self):
        """Test complete event processor flow execution."""
        with patch('flows.event_processor_flow.analyze_order_events') as mock_analyze, \
             patch('flows.event_processor_flow.process_sla_evaluations') as mock_sla, \
             patch('flows.event_processor_flow.process_ai_analysis_queue') as mock_ai:
            
            # Mock task results
            mock_analyze.return_value = {
                "processed_count": 10,
                "events_found": 15,
                "processing_time_ms": 200
            }
            
            mock_sla.return_value = {
                "evaluations_processed": 10,
                "sla_violations": 2
            }
            
            mock_ai.return_value = {
                "analyses_completed": 3,
                "exceptions_processed": 3
            }
            
            # Execute flow
            result = await event_processor_flow(tenant="test-tenant")
            
            # Verify flow completion
            assert "status" in result
            assert result.get("status") in ["completed", "success"] or "processed_count" in result

    @pytest.mark.asyncio
    async def test_analyze_order_events_with_retry(self):
        """Test order analysis with retry mechanism."""
        with patch('flows.event_processor_flow.get_session') as mock_session:
            
            # Mock session that fails first time, succeeds second time
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.execute.side_effect = [Exception("Database error"), MagicMock()]
            
            # Should handle retry gracefully
            with pytest.raises(Exception):
                await analyze_order_events(tenant="test-tenant")

    @pytest.mark.asyncio
    async def test_process_sla_evaluations_empty_result(self):
        """Test SLA evaluation with no violations found."""
        with patch('flows.event_processor_flow.get_session') as mock_session:
            
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.execute.return_value.scalars.return_value.all.return_value = []
            
            result = await process_sla_evaluations(tenant="test-tenant")
            
            assert "evaluations_processed" in result or "sla_violations" in result

    @pytest.mark.asyncio
    async def test_process_ai_analysis_queue_empty_exceptions(self):
        """Test AI analysis with empty exception queue."""
        with patch('flows.event_processor_flow.get_session') as mock_session:
            
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.execute.return_value.scalars.return_value.all.return_value = []
            
            result = await process_ai_analysis_queue(tenant="test-tenant")
            
            assert "analyses_completed" in result or "exceptions_processed" in result

    @pytest.mark.asyncio
    async def test_event_processor_flow_with_correlation_id(self):
        """Test flow execution with correlation ID tracking."""
        with patch('flows.event_processor_flow.analyze_order_events') as mock_analyze, \
             patch('flows.event_processor_flow.process_sla_evaluations') as mock_sla, \
             patch('flows.event_processor_flow.process_ai_analysis_queue') as mock_ai:
            
            mock_analyze.return_value = {"processed_count": 5}
            mock_sla.return_value = {"evaluations_processed": 5}
            mock_ai.return_value = {"analyses_completed": 0}
            
            result = await event_processor_flow(
                tenant="test-tenant",
                correlation_id="test-correlation-123"
            )
            
            # Should complete successfully
            assert "status" in result or "processed_count" in result


@pytest.mark.unit
class TestEventProcessorFlowIntegration:
    """Integration-style unit tests for Event Processor Flow."""
    
    @pytest.mark.asyncio
    async def test_flow_handles_high_exception_volume(self):
        """Test flow handling high volume of exceptions."""
        with patch('flows.event_processor_flow.get_session') as mock_session, \
             patch('flows.event_processor_flow.analyze_exception_or_fallback') as mock_ai:
            
            # Mock database session with many exceptions
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Create large number of mock exceptions
            mock_exceptions = [
                MagicMock(
                    id=i,
                    order_id=f"order-{i}",
                    exception_type="PICK_DELAY",
                    context={"delay_minutes": 30}
                )
                for i in range(100)
            ]
            
            mock_db.execute.return_value.scalars.return_value.all.return_value = mock_exceptions
            
            mock_ai.return_value = {"analysis": "Standard delay", "confidence": 0.7}
            
            result = await process_ai_analysis_queue(tenant="test-tenant")
            
            assert "analyses_completed" in result or "exceptions_processed" in result

    @pytest.mark.asyncio
    async def test_flow_performance_metrics(self):
        """Test flow performance tracking and metrics."""
        with patch('flows.event_processor_flow.analyze_order_events') as mock_analyze:
            
            # Mock performance data
            mock_analyze.return_value = {
                "processed_count": 1000,
                "events_found": 1200,
                "processing_time_ms": 2500,
                "performance_metrics": {
                    "avg_event_processing_ms": 2.5,
                    "throughput_events_per_second": 400
                }
            }
            
            result = await analyze_order_events(tenant="test-tenant", lookback_hours=2)
            
            assert "processed_count" in result
            if "performance_metrics" in result:
                assert result["performance_metrics"]["throughput_events_per_second"] == 400

    @pytest.mark.asyncio
    async def test_flow_error_handling_and_recovery(self):
        """Test flow error handling and recovery mechanisms."""
        with patch('flows.event_processor_flow.get_session') as mock_session, \
             patch('flows.event_processor_flow.get_run_logger') as mock_logger:
            
            # Mock database connection failure
            mock_session.side_effect = Exception("Connection timeout")
            mock_logger_instance = MagicMock()
            mock_logger.return_value = mock_logger_instance
            
            with pytest.raises(Exception):
                await analyze_order_events(tenant="test-tenant")
            
            # Verify error was logged
            mock_logger.assert_called()

    @pytest.mark.asyncio
    async def test_flow_sla_evaluation_integration(self):
        """Test SLA evaluation integration within the flow."""
        with patch('flows.event_processor_flow.get_session') as mock_session, \
             patch('flows.event_processor_flow.evaluate_sla') as mock_sla:
            
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock orders needing SLA evaluation
            mock_orders = [
                MagicMock(order_id=f"order-{i}", created_at=datetime.now(timezone.utc))
                for i in range(5)
            ]
            
            mock_db.execute.return_value.scalars.return_value.all.return_value = mock_orders
            
            # Mock SLA evaluation results
            mock_sla.return_value = {
                "sla_met": False,
                "processing_time_minutes": 75,
                "sla_threshold_minutes": 60,
                "violation_severity": "MEDIUM"
            }
            
            result = await process_sla_evaluations(tenant="test-tenant")
            
            assert "evaluations_processed" in result or "sla_violations" in result

    @pytest.mark.asyncio
    async def test_flow_ai_analysis_with_fallback(self):
        """Test AI analysis with fallback mechanisms."""
        with patch('flows.event_processor_flow.get_session') as mock_session, \
             patch('flows.event_processor_flow.analyze_exception_or_fallback') as mock_ai:
            
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock exception requiring analysis
            mock_exception = MagicMock()
            mock_exception.id = 1
            mock_exception.order_id = "order-123"
            mock_exception.exception_type = "PICK_DELAY"
            mock_exception.context = {"delay_minutes": 90}
            
            mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_exception]
            
            # Mock AI analysis with fallback
            mock_ai.return_value = {
                "analysis": "Fallback analysis: Significant delay detected",
                "recommendations": ["Review picker allocation"],
                "confidence": 0.60,
                "fallback_used": True
            }
            
            result = await process_ai_analysis_queue(tenant="test-tenant")
            
            assert "analyses_completed" in result or "exceptions_processed" in result
