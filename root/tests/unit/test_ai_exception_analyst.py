"""Unit tests for AI exception analyst functionality."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.ai_exception_analyst import (
    analyze_exception_or_fallback,
    clear_analysis_cache,
    get_cache_stats
)


@pytest.mark.unit
@pytest.mark.ai
class TestAIExceptionAnalyst:
    """Test cases for AI exception analyst functions."""
    
    @pytest.fixture
    def mock_exception(self):
        """Create mock exception record."""
        from app.storage.models import ExceptionRecord
        exception = MagicMock(spec=ExceptionRecord)
        exception.id = 1
        exception.tenant = "test-tenant"
        exception.order_id = "order-12345"
        exception.reason_code = "PICK_DELAY"
        exception.severity = "MEDIUM"
        exception.status = "OPEN"
        exception.ops_note = None
        exception.client_note = None
        exception.context_data = {"delay_minutes": 45, "sla_minutes": 120}
        return exception

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_analyze_exception_already_analyzed(self, mock_db, mock_exception):
        """Test that already analyzed exceptions are skipped."""
        mock_exception.ops_note = "Already analyzed"
        mock_exception.client_note = "Already analyzed"
        
        await analyze_exception_or_fallback(mock_db, mock_exception)
        
        # Should not modify the exception
        assert mock_exception.ops_note == "Already analyzed"
        assert mock_exception.client_note == "Already analyzed"

    @pytest.mark.asyncio
    async def test_analyze_exception_ai_success(self, mock_db, mock_exception):
        """Test successful AI analysis."""
        with patch('app.services.ai_exception_analyst._try_ai_analysis') as mock_ai:
            mock_ai.return_value = {
                "label": "PICK_DELAY",
                "confidence": 0.85,
                "ops_note": "AI generated ops note",
                "client_note": "AI generated client note"
            }
            
            with patch('app.services.ai_exception_analyst._is_high_confidence') as mock_confidence:
                mock_confidence.return_value = True
                
                await analyze_exception_or_fallback(mock_db, mock_exception)
                
                # Should apply AI analysis
                mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_exception_ai_failure_fallback(self, mock_db, mock_exception):
        """Test fallback when AI analysis fails."""
        with patch('app.services.ai_exception_analyst._try_ai_analysis') as mock_ai:
            mock_ai.return_value = None  # AI failed
            
            await analyze_exception_or_fallback(mock_db, mock_exception)
            
            # Should apply fallback analysis
            mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_exception_low_confidence_fallback(self, mock_db, mock_exception):
        """Test fallback when AI confidence is too low."""
        with patch('app.services.ai_exception_analyst._try_ai_analysis') as mock_ai:
            mock_ai.return_value = {
                "label": "PICK_DELAY",
                "confidence": 0.3,  # Low confidence
                "ops_note": "AI generated ops note",
                "client_note": "AI generated client note"
            }
            
            with patch('app.services.ai_exception_analyst._is_high_confidence') as mock_confidence:
                mock_confidence.return_value = False  # Low confidence
                
                await analyze_exception_or_fallback(mock_db, mock_exception)
                
                # Should apply fallback analysis
                mock_db.flush.assert_called_once()

    def test_clear_analysis_cache(self):
        """Test clearing the analysis cache."""
        # Add something to cache first
        from app.services.ai_exception_analyst import _analysis_cache
        _analysis_cache["test_key"] = {"test": "data"}
        
        clear_analysis_cache()
        
        assert len(_analysis_cache) == 0

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        # Add something to cache first
        from app.services.ai_exception_analyst import _analysis_cache
        _analysis_cache["test_key"] = {"test": "data"}
        
        stats = get_cache_stats()
        
        assert "cache_size" in stats
        assert "max_cache_size" in stats
        assert stats["cache_size"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_exception_with_context_data(self, mock_db, mock_exception):
        """Test analysis with rich context data."""
        mock_exception.context_data = {
            "delay_minutes": 45,
            "sla_minutes": 120,
            "actual_minutes": 165
        }
        
        with patch('app.services.ai_exception_analyst._try_ai_analysis') as mock_ai:
            mock_ai.return_value = None  # Force fallback
            
            await analyze_exception_or_fallback(mock_db, mock_exception)
            
            # Should complete without error
            mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_exception_different_reason_codes(self, mock_db, mock_exception):
        """Test analysis with different reason codes."""
        reason_codes = ["PICK_DELAY", "PACK_DELAY", "CARRIER_ISSUE", "STOCK_MISMATCH"]
        
        for reason_code in reason_codes:
            mock_exception.reason_code = reason_code
            mock_exception.ops_note = None
            mock_exception.client_note = None
            
            with patch('app.services.ai_exception_analyst._try_ai_analysis') as mock_ai:
                mock_ai.return_value = None  # Force fallback
                
                await analyze_exception_or_fallback(mock_db, mock_exception)
                
                # Should complete without error for all reason codes
                assert mock_db.flush.called
