# ==== SLA ENGINE TEST SUITE ==== #

"""
Tests for SLA engine functionality.

This module provides comprehensive testing for the SLA engine
including timeline building, breach detection, SLA validation,
and integration testing with realistic data scenarios.
"""

import pytest
import datetime as dt
from unittest.mock import AsyncMock

from app.services.sla_engine import SLAEngine
from app.storage.models import OrderEvent, ExceptionRecord


# ==== SLA ENGINE UNIT TESTS ==== #


class TestSLAEngine:
    """
    Test cases for SLA engine.
    
    Provides comprehensive unit testing for all SLA engine
    functionality including timeline building, breach detection,
    and SLA validation across various scenarios.
    """
    
    @pytest.fixture
    def sla_engine(self):
        """
        Create SLA engine instance.
        
        Returns:
            SLAEngine: Fresh SLA engine instance for testing
        """
        return SLAEngine()
    
    @pytest.fixture
    def mock_db(self):
        """
        Create mock database session.
        
        Returns:
            AsyncMock: Mocked database session for testing
        """
        return AsyncMock()
    
    # ==== TIMELINE BUILDING TESTS ==== #
    
    def test_build_event_timeline(self, sla_engine):
        """
        Test event timeline building.
        
        Verifies that event timeline construction correctly
        maps event types to timestamps with proper ordering.
        """
        base_time = dt.datetime.utcnow()
        
        events = [
            OrderEvent(
                event_type="order_paid",
                occurred_at=base_time,
                payload={}
            ),
            OrderEvent(
                event_type="pick_completed", 
                occurred_at=base_time + dt.timedelta(minutes=90),
                payload={}
            ),
            OrderEvent(
                event_type="pack_completed",
                occurred_at=base_time + dt.timedelta(minutes=150),
                payload={}
            )
        ]
        
        timeline = sla_engine._build_event_timeline(events)
        
        assert "order_paid" in timeline
        assert "pick_completed" in timeline
        assert "pack_completed" in timeline
        assert timeline["order_paid"] == base_time
        assert timeline["pick_completed"] == base_time + dt.timedelta(minutes=90)
    
    # ==== PICK SLA VALIDATION TESTS ==== #
    
    def test_check_pick_sla_within_threshold(self, sla_engine):
        """
        Test pick SLA check when within threshold.
        
        Verifies that pick operations within SLA limits
        do not generate breach notifications.
        """
        base_time = dt.datetime.utcnow()
        timeline = {
            "order_paid": base_time,
            "pick_completed": base_time + dt.timedelta(minutes=90)  # Within 120min SLA
        }
        sla_config = {"pick_minutes": 120}
        
        breach = sla_engine._check_pick_sla(timeline, sla_config)
        
        assert breach is None
    
    def test_check_pick_sla_exceeds_threshold(self, sla_engine):
        """
        Test pick SLA check when exceeding threshold.
        
        Verifies that pick operations exceeding SLA limits
        correctly generate breach notifications with accurate
        timing and delay calculations.
        """
        base_time = dt.datetime.utcnow()
        timeline = {
            "order_paid": base_time,
            "pick_completed": base_time + dt.timedelta(minutes=180)  # Exceeds 120min SLA
        }
        sla_config = {"pick_minutes": 120}
        
        breach = sla_engine._check_pick_sla(timeline, sla_config)
        
        assert breach is not None
        assert breach["reason_code"] == "PICK_DELAY"
        assert breach["actual_minutes"] == 180
        assert breach["sla_minutes"] == 120
        assert breach["delay_minutes"] == 60
    
    # ==== PACK SLA VALIDATION TESTS ==== #
    
    def test_check_pack_sla_within_threshold(self, sla_engine):
        """
        Test pack SLA check when within threshold.
        
        Verifies that pack operations within SLA limits
        do not generate breach notifications.
        """
        base_time = dt.datetime.utcnow()
        timeline = {
            "pick_completed": base_time,
            "pack_completed": base_time + dt.timedelta(minutes=120)  # Within 180min SLA
        }
        sla_config = {"pack_minutes": 180}
        
        breach = sla_engine._check_pack_sla(timeline, sla_config)
        
        assert breach is None
    
    def test_check_pack_sla_exceeds_threshold(self, sla_engine):
        """
        Test pack SLA check when exceeding threshold.
        
        Verifies that pack operations exceeding SLA limits
        correctly generate breach notifications with accurate
        timing and delay calculations.
        """
        base_time = dt.datetime.utcnow()
        timeline = {
            "pick_completed": base_time,
            "pack_completed": base_time + dt.timedelta(minutes=240)  # Exceeds 180min SLA
        }
        sla_config = {"pack_minutes": 180}
        
        breach = sla_engine._check_pack_sla(timeline, sla_config)
        
        assert breach is not None
        assert breach["reason_code"] == "PACK_DELAY"
        assert breach["actual_minutes"] == 240
        assert breach["sla_minutes"] == 180
        assert breach["delay_minutes"] == 60
    
    # ==== MULTIPLE BREACH DETECTION TESTS ==== #
    
    def test_detect_breaches_multiple(self, sla_engine):
        """
        Test detection of multiple SLA breaches.
        
        Verifies that multiple SLA violations are correctly
        detected and prioritized according to business rules.
        """
        base_time = dt.datetime.utcnow()
        timeline = {
            "order_paid": base_time,
            "pick_completed": base_time + dt.timedelta(minutes=180),  # Exceeds 120min
            "pack_completed": base_time + dt.timedelta(minutes=420)   # Exceeds 180min from pick
        }
        sla_config = {
            "pick_minutes": 120,
            "pack_minutes": 180,
            "ship_minutes": 1440
        }
        
        breaches = sla_engine._detect_breaches(timeline, sla_config)
        
        # Should detect both pick and pack delays
        assert len(breaches) == 2
        
        # Should be sorted by priority (most critical first)
        reason_codes = [breach["reason_code"] for breach in breaches]
        assert "PICK_DELAY" in reason_codes
        assert "PACK_DELAY" in reason_codes
    
    # ==== UTILITY FUNCTION TESTS ==== #
    
    def test_calculate_duration_minutes(self, sla_engine):
        """
        Test duration calculation between timestamps.
        
        Verifies accurate duration calculation in minutes
        for SLA compliance evaluation.
        """
        start_time = dt.datetime(2025, 8, 16, 10, 0, 0)
        end_time = dt.datetime(2025, 8, 16, 12, 30, 0)
        
        duration = sla_engine._calculate_duration_minutes(start_time, end_time)
        
        assert duration == 150.0  # 2.5 hours = 150 minutes
    
    def test_get_breach_priority(self, sla_engine):
        """
        Test breach priority ordering.
        
        Verifies that breach priorities are correctly
        assigned according to business impact and urgency.
        """
        # System errors should have highest priority (lowest number)
        assert sla_engine._get_breach_priority("SYSTEM_ERROR") < sla_engine._get_breach_priority("PICK_DELAY")
        assert sla_engine._get_breach_priority("STOCK_MISMATCH") < sla_engine._get_breach_priority("PACK_DELAY")
        assert sla_engine._get_breach_priority("CARRIER_ISSUE") < sla_engine._get_breach_priority("MISSING_SCAN")
    
    # ==== EDGE CASE TESTS ==== #
    
    def test_missing_events_no_breach(self, sla_engine):
        """
        Test that missing events don't cause false breaches.
        
        Verifies that incomplete event timelines do not
        generate false positive breach notifications.
        """
        timeline = {
            "order_paid": dt.datetime.utcnow()
            # No pick_completed event
        }
        sla_config = {"pick_minutes": 120}
        
        breach = sla_engine._check_pick_sla(timeline, sla_config)
        
        assert breach is None
    
    @pytest.mark.asyncio
    async def test_evaluate_sla_no_events(self, sla_engine, mock_db):
        """
        Test SLA evaluation with no events.
        
        Verifies that SLA evaluation gracefully handles
        scenarios with no order events.
        """
        # Create a proper mock result that has scalars() method
        from unittest.mock import MagicMock
        mock_result = MagicMock()
        mock_result.scalars.return_value = []
        
        # Make execute return the mock result (not a coroutine)
        mock_db.execute.return_value = mock_result
        
        result = await sla_engine.evaluate_sla(mock_db, "test-tenant", "test-order")
        
        assert result is None
    
    def test_detect_breaches_empty_timeline(self, sla_engine):
        """
        Test breach detection with empty timeline.
        
        Verifies that empty event timelines are handled
        gracefully without generating errors.
        """
        timeline = {}
        sla_config = {"pick_minutes": 120, "pack_minutes": 180}
        
        breaches = sla_engine._detect_breaches(timeline, sla_config)
        
        assert breaches == []


# ==== SLA ENGINE INTEGRATION TESTS ==== #


@pytest.mark.asyncio
async def test_sla_engine_integration():
    """
    Integration test for SLA engine with real-like data.
    
    Provides end-to-end testing of SLA engine functionality
    using realistic order event scenarios and configurations.
    """
    engine = SLAEngine()
    
    # Simulate a delayed pick scenario
    base_time = dt.datetime.utcnow() - dt.timedelta(hours=4)
    
    events = [
        OrderEvent(
            tenant="test-tenant",
            source="shopify",
            event_type="order_paid",
            event_id="evt-001",
            order_id="order-001",
            occurred_at=base_time,
            payload={"total_amount_cents": 2999}
        ),
        OrderEvent(
            tenant="test-tenant",
            source="wms", 
            event_type="pick_completed",
            event_id="evt-002",
            order_id="order-001",
            occurred_at=base_time + dt.timedelta(minutes=180),  # 3 hours - exceeds 2hr SLA
            payload={"station": "PICK-01", "worker_id": "W123"}
        )
    ]
    
    timeline = engine._build_event_timeline(events)
    sla_config = {"pick_minutes": 120, "pack_minutes": 180, "ship_minutes": 1440}
    
    breaches = engine._detect_breaches(timeline, sla_config)
    
    assert len(breaches) == 1
    assert breaches[0]["reason_code"] == "PICK_DELAY"
    assert breaches[0]["delay_minutes"] == 60  # 180 - 120 = 60 minutes delay
