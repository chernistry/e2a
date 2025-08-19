# ==== AI AUTOMATED RESOLUTION SERVICE TESTS ==== #

"""
Unit tests for AI automated resolution service.

Tests the AI-powered analysis of exception resolution possibilities,
ensuring genuine analysis of raw data rather than pattern matching.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.services.ai_automated_resolution import (
    analyze_automated_resolution_possibility,
    execute_automated_actions,
    AutomatedResolutionActions
)
from app.storage.models import ExceptionRecord


# ==== TEST FIXTURES ==== #


@pytest.fixture
def sample_exception():
    """Create a sample exception record for testing."""
    return ExceptionRecord(
        id="test-exc-001",
        order_id="ORD-12345",
        reason_code="ADDRESS_INVALID",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        context_data={"test": "data"}
    )


@pytest.fixture
def raw_order_data():
    """Sample raw order data without preprocessing."""
    return {
        "order_id": "ORD-12345",
        "warehouse_events": [
            {
                "event_type": "order_created",
                "occurred_at": "2024-08-19T10:00:00Z",
                "event_data": {"status": "pending"},
                "source": "order_system"
            }
        ],
        "shipping_address": {
            "address1": "123 Main St",
            "city": "Anytown",
            "zip_code": "1234",  # Invalid zip (too short)
            "country": "US"
        },
        "financial_status": "paid",
        "line_items": [
            {"sku": "ITEM-001", "quantity": 2}
        ]
    }


@pytest.fixture
def ai_resolution_response():
    """Sample AI resolution analysis response."""
    return {
        "can_auto_resolve": True,
        "confidence": 0.85,
        "automated_actions": [AutomatedResolutionActions.ADDRESS_VALIDATION],
        "resolution_strategy": "Validate and correct zip code format",
        "success_probability": 0.75,
        "reasoning": "Zip code format issue detected, can be corrected automatically",
        "risk_assessment": "Low",
        "estimated_resolution_time": "2 minutes"
    }


# ==== CORE FUNCTIONALITY TESTS ==== #


@pytest.mark.asyncio
async def test_analyze_automated_resolution_possibility_success(
    sample_exception, 
    raw_order_data, 
    ai_resolution_response
):
    """Test successful AI analysis of automated resolution possibility."""
    
    # Mock database session and raw data retrieval
    mock_db = AsyncMock()
    
    with patch('app.services.ai_automated_resolution._get_raw_order_data') as mock_get_data, \
         patch('app.services.ai_automated_resolution._perform_ai_resolution_analysis') as mock_ai_analysis, \
         patch('app.services.ai_automated_resolution._get_cached_analysis') as mock_cache_get, \
         patch('app.services.ai_automated_resolution._cache_analysis_result') as mock_cache_set:
        
        # Setup mocks
        mock_cache_get.return_value = None  # No cached result
        mock_get_data.return_value = raw_order_data
        mock_ai_analysis.return_value = ai_resolution_response
        
        # Execute analysis
        result = await analyze_automated_resolution_possibility(mock_db, sample_exception)
        
        # Verify AI analysis was called with raw data
        mock_get_data.assert_called_once_with(mock_db, sample_exception.order_id)
        mock_ai_analysis.assert_called_once()
        
        # Verify result structure
        assert result["can_auto_resolve"] is True
        assert result["confidence"] == 0.85
        assert AutomatedResolutionActions.ADDRESS_VALIDATION in result["automated_actions"]
        assert result["success_probability"] == 0.75
        
        # Verify caching was attempted
        mock_cache_set.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_automated_resolution_with_cache_hit(
    sample_exception, 
    ai_resolution_response
):
    """Test that cached results are returned when available."""
    
    mock_db = AsyncMock()
    
    with patch('app.services.ai_automated_resolution._get_cached_analysis') as mock_cache_get, \
         patch('app.services.ai_automated_resolution._get_raw_order_data') as mock_get_data:
        
        # Setup cache hit
        mock_cache_get.return_value = ai_resolution_response
        
        # Execute analysis
        result = await analyze_automated_resolution_possibility(mock_db, sample_exception)
        
        # Verify cache was used and raw data retrieval was skipped
        mock_cache_get.assert_called_once()
        mock_get_data.assert_not_called()
        
        # Verify cached result was returned
        assert result == ai_resolution_response


@pytest.mark.asyncio
async def test_analyze_automated_resolution_ai_failure_fallback(
    sample_exception, 
    raw_order_data
):
    """Test fallback to rule-based analysis when AI fails."""
    
    mock_db = AsyncMock()
    
    with patch('app.services.ai_automated_resolution._get_raw_order_data') as mock_get_data, \
         patch('app.services.ai_automated_resolution._perform_ai_resolution_analysis') as mock_ai_analysis, \
         patch('app.services.ai_automated_resolution._get_cached_analysis') as mock_cache_get, \
         patch('app.services.ai_automated_resolution._fallback_resolution_analysis') as mock_fallback:
        
        # Setup mocks
        mock_cache_get.return_value = None
        mock_get_data.return_value = raw_order_data
        mock_ai_analysis.side_effect = Exception("AI service unavailable")
        
        fallback_result = {
            "can_auto_resolve": True,
            "confidence": 0.6,
            "automated_actions": [AutomatedResolutionActions.ADDRESS_VALIDATION],
            "fallback_used": True
        }
        mock_fallback.return_value = fallback_result
        
        # Execute analysis
        result = await analyze_automated_resolution_possibility(mock_db, sample_exception)
        
        # Verify fallback was used
        mock_fallback.assert_called_once_with(sample_exception, raw_order_data)
        assert result["fallback_used"] is True
        assert result["confidence"] == 0.6


# ==== RAW DATA ANALYSIS TESTS ==== #


@pytest.mark.asyncio
async def test_raw_data_contains_no_preprocessing_hints():
    """Test that raw order data contains no preprocessing hints."""
    
    from app.services.ai_automated_resolution import _get_raw_order_data
    
    mock_db = AsyncMock()
    
    # Mock order events with various data
    mock_events = [
        MagicMock(
            event_type="order_created",
            occurred_at=datetime.now(timezone.utc),
            event_data={
                "financial_status": "paid",
                "shipping_address": {"zip_code": "12345"},
                "line_items": [{"sku": "ITEM-001", "quantity": 1}]
            },
            source="order_system"
        )
    ]
    
    with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_events
        mock_execute.return_value = mock_result
        
        raw_data = await _get_raw_order_data(mock_db, "ORD-12345")
        
        # Verify no preprocessing hints are present
        assert "fulfillment_delay_hours" not in raw_data
        assert "can_auto_resolve" not in raw_data
        assert "pre_calculated_flags" not in raw_data
        
        # Verify raw data is present
        assert "warehouse_events" in raw_data
        assert "financial_status" in raw_data
        assert "shipping_address" in raw_data
        assert raw_data["order_id"] == "ORD-12345"


# ==== ACTION EXECUTION TESTS ==== #


@pytest.mark.asyncio
async def test_execute_automated_actions_success(sample_exception):
    """Test successful execution of automated actions."""
    
    mock_db = AsyncMock()
    actions = [
        AutomatedResolutionActions.ADDRESS_VALIDATION,
        AutomatedResolutionActions.SYSTEM_RECOVERY
    ]
    
    with patch('app.services.ai_automated_resolution._execute_address_validation') as mock_addr, \
         patch('app.services.ai_automated_resolution._execute_system_recovery') as mock_system:
        
        # Setup successful execution
        mock_addr.return_value = True
        mock_system.return_value = True
        
        result = await execute_automated_actions(mock_db, sample_exception, actions)
        
        # Verify actions were executed
        mock_addr.assert_called_once_with(mock_db, sample_exception)
        mock_system.assert_called_once_with(mock_db, sample_exception)
        
        # Verify success
        assert result is True


@pytest.mark.asyncio
async def test_execute_automated_actions_partial_failure(sample_exception):
    """Test execution with some actions failing."""
    
    mock_db = AsyncMock()
    actions = [
        AutomatedResolutionActions.ADDRESS_VALIDATION,
        AutomatedResolutionActions.PAYMENT_RETRY
    ]
    
    with patch('app.services.ai_automated_resolution._execute_address_validation') as mock_addr, \
         patch('app.services.ai_automated_resolution._execute_payment_retry') as mock_payment:
        
        # Setup mixed results
        mock_addr.return_value = True
        mock_payment.return_value = False
        
        result = await execute_automated_actions(mock_db, sample_exception, actions)
        
        # Should return True if at least one action succeeded
        assert result is True


@pytest.mark.asyncio
async def test_execute_automated_actions_all_fail(sample_exception):
    """Test execution when all actions fail."""
    
    mock_db = AsyncMock()
    actions = [AutomatedResolutionActions.PAYMENT_RETRY]
    
    with patch('app.services.ai_automated_resolution._execute_payment_retry') as mock_payment:
        
        # Setup failure
        mock_payment.return_value = False
        
        result = await execute_automated_actions(mock_db, sample_exception, actions)
        
        # Should return False when all actions fail
        assert result is False


# ==== INTEGRATION TESTS ==== #


@pytest.mark.asyncio
async def test_ai_analysis_validates_required_fields():
    """Test that AI analysis validates required response fields."""
    
    from app.services.ai_automated_resolution import _perform_ai_resolution_analysis
    
    context = {
        "exception_id": "test-001",
        "order_id": "ORD-12345",
        "reason_code": "ADDRESS_INVALID"
    }
    
    with patch('app.services.ai_client.get_ai_client') as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        
        # Test missing required field
        mock_client.analyze_automated_resolution.return_value = {
            "can_auto_resolve": True,
            "confidence": 0.8
            # Missing automated_actions and success_probability
        }
        
        with pytest.raises(ValueError, match="Missing required field"):
            await _perform_ai_resolution_analysis(context)


@pytest.mark.asyncio
async def test_confidence_score_monitoring():
    """Test that confidence scores are properly monitored."""
    
    from app.services.ai_automated_resolution import _perform_ai_resolution_analysis
    
    context = {"exception_id": "test-001"}
    
    with patch('app.services.ai_client.get_ai_client') as mock_get_client, \
         patch('app.observability.metrics.ai_confidence_score') as mock_metric:
        
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        
        mock_client.analyze_automated_resolution.return_value = {
            "can_auto_resolve": True,
            "confidence": 0.85,
            "automated_actions": ["test_action"],
            "success_probability": 0.75
        }
        
        await _perform_ai_resolution_analysis(context)
        
        # Verify confidence score was recorded
        mock_metric.labels.assert_called_with(analysis_type="automated_resolution")
        mock_metric.labels.return_value.observe.assert_called_with(0.85)
