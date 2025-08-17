"""Tests for Slack integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.integrations.slack.models import (
    SlackEvent,
    SlackEventPayload,
    SlackQueryRequest,
    SlackQueryResponse,
    ExceptionSummary
)
from app.integrations.slack.processor import SlackEventProcessor
from app.integrations.slack.rag_service import SlackRAGService


class TestSlackEventProcessor:
    """Test Slack event processor."""
    
    @pytest.fixture
    def processor(self):
        """Create processor instance."""
        return SlackEventProcessor(
            slack_bot_token="xoxb-test-token",
            slack_bot_user_id="U123456789",
            rag_service=None
        )
    
    @pytest.fixture
    def sample_event(self):
        """Create sample Slack event."""
        return SlackEvent(
            type="app_mention",
            user="U987654321",
            channel="C123456789",
            text="<@U123456789> show me recent exceptions",
            ts="1642781234.123456"
        )
    
    @pytest.fixture
    def sample_payload(self, sample_event):
        """Create sample event payload."""
        return SlackEventPayload(
            token="test-token",
            team_id="T123456789",
            api_app_id="A123456789",
            event=sample_event,
            type="event_callback",
            event_id="Ev123456789",
            event_time=1642781234,
            authed_users=["U123456789"]
        )
    
    def test_extract_question_from_mention(self, processor):
        """Test question extraction from mention."""
        text = "<@U123456789> show me recent PICK_DELAY exceptions"
        question = processor._extract_question_from_mention(text)
        assert question == "show me recent PICK_DELAY exceptions"
    
    def test_extract_keywords(self, processor):
        """Test keyword extraction."""
        query = "show me recent PICK_DELAY exceptions for order ORD-123"
        keywords = processor._extract_keywords(query)
        
        # Check that we get expected keywords (case insensitive, underscores preserved)
        assert "pick_delay" in keywords
        assert "exceptions" in keywords
        assert "order" in keywords
        assert "recent" in keywords
        # "show" is not in stop words, so it will be included
        assert "show" in keywords
        # Short words (len <= 2) should be filtered out
        # "me" has length 2, so it should be filtered out
        assert len([k for k in keywords if len(k) <= 2]) == 0
    
    @pytest.mark.asyncio
    async def test_process_app_mention(self, processor, sample_event):
        """Test app mention processing."""
        with patch.object(processor, '_query_database') as mock_query:
            mock_query.return_value = SlackQueryResponse(
                answer="Found 5 recent exceptions",
                confidence=0.8,
                exception_count=5
            )
            
            response = await processor._handle_app_mention(
                sample_event, "test-tenant", MagicMock()
            )
            
            assert response is not None
            assert "Found 5 recent exceptions" in response.text
            assert response.channel == "C123456789"
    
    @pytest.mark.asyncio
    async def test_ignore_bot_messages(self, processor):
        """Test that bot messages are ignored."""
        bot_event = SlackEvent(
            type="app_mention",
            user="U123456789",  # Same as bot user ID
            channel="C123456789",
            text="<@U123456789> test",
            ts="1642781234.123456"
        )
        
        response = await processor._handle_app_mention(
            bot_event, "test-tenant", MagicMock()
        )
        
        assert response is None
    
    @pytest.mark.asyncio
    async def test_help_response(self, processor):
        """Test help response."""
        help_event = SlackEvent(
            type="app_mention",
            user="U987654321",
            channel="C123456789",
            text="<@U123456789> help",
            ts="1642781234.123456"
        )
        
        response = await processor._handle_app_mention(
            help_event, "test-tenant", MagicMock()
        )
        
        assert response is not None
        assert "Oktup E²A Assistant" in response.text
        assert "Query exceptions" in response.text
    
    def test_generate_database_answer(self, processor):
        """Test database answer generation."""
        exceptions = [
            ExceptionSummary(
                id=1,
                tenant="test-tenant",
                order_id="ORD-123",
                reason_code="PICK_DELAY",
                severity="MEDIUM",
                status="OPEN",
                created_at=datetime.now(timezone.utc),
                ops_note="Pick operation delayed"
            ),
            ExceptionSummary(
                id=2,
                tenant="test-tenant",
                order_id="ORD-124",
                reason_code="PICK_DELAY",
                severity="HIGH",
                status="RESOLVED",
                created_at=datetime.now(timezone.utc),
                ops_note="Pick station issue"
            )
        ]
        
        answer = processor._generate_database_answer(exceptions, "pick delays")
        
        assert "Found 2 recent exceptions" in answer
        assert "PICK_DELAY: 2 (100.0%)" in answer
        assert "ORD-123" in answer


class TestSlackRAGService:
    """Test Slack RAG service."""
    
    @pytest.fixture
    def mock_ai_client(self):
        """Create mock AI client."""
        client = AsyncMock()
        client.generate_text.return_value = MagicMock(
            content="Based on the exception data, there are 2 PICK_DELAY cases..."
        )
        return client
    
    @pytest.fixture
    def rag_service(self, mock_ai_client):
        """Create RAG service instance."""
        return SlackRAGService(mock_ai_client)
    
    @pytest.mark.asyncio
    async def test_query_with_results(self, rag_service):
        """Test RAG query with results."""
        with patch.object(rag_service, '_retrieve_exceptions') as mock_retrieve:
            mock_retrieve.return_value = [
                {
                    "id": 1,
                    "order_id": "ORD-123",
                    "reason_code": "PICK_DELAY",
                    "ops_note": "Pick operation delayed",
                    "severity": "MEDIUM",
                    "status": "OPEN",
                    "created_at": "2025-01-17T10:30:00Z",
                    "similar_cases": 5
                }
            ]
            
            response = await rag_service.query(
                query="show me pick delays",
                tenant="test-tenant",
                user_id="U123456789"
            )
            
            assert response is not None
            assert response.confidence > 0.8
            assert response.exception_count == 1
            assert len(response.sources) == 1
    
    @pytest.mark.asyncio
    async def test_query_no_results(self, rag_service):
        """Test RAG query with no results."""
        with patch.object(rag_service, '_retrieve_exceptions') as mock_retrieve:
            mock_retrieve.return_value = []
            
            response = await rag_service.query(
                query="show me unicorn delays",
                tenant="test-tenant",
                user_id="U123456789"
            )
            
            assert response is not None
            assert response.confidence < 0.5
            assert "No relevant exceptions found" in response.answer
    
    @pytest.mark.asyncio
    async def test_ai_fallback(self, rag_service):
        """Test fallback when AI fails."""
        with patch.object(rag_service, '_retrieve_exceptions') as mock_retrieve:
            mock_retrieve.return_value = [
                {
                    "id": 1,
                    "order_id": "ORD-123",
                    "reason_code": "PICK_DELAY",
                    "ops_note": "Pick operation delayed",
                    "severity": "MEDIUM",
                    "status": "OPEN",
                    "created_at": "2025-01-17T10:30:00Z",
                    "similar_cases": 5
                }
            ]
            
            # Make AI client fail
            rag_service.ai_client.generate_text.side_effect = Exception("AI failed")
            
            response = await rag_service.query(
                query="show me pick delays",
                tenant="test-tenant",
                user_id="U123456789"
            )
            
            assert response is not None
            assert response.confidence == 0.7  # Fallback confidence
            assert "Found 1 relevant exceptions" in response.answer
    
    def test_extract_keywords(self, rag_service):
        """Test keyword extraction."""
        keywords = rag_service._extract_keywords("show me recent PICK_DELAY exceptions")
        
        assert "pick_delay" in keywords  # Converted to lowercase
        assert "recent" in keywords
        assert "exceptions" in keywords
        assert "show" not in keywords  # stop word
        assert "me" not in keywords    # stop word


class TestSlackModels:
    """Test Slack models."""
    
    def test_slack_event_model(self):
        """Test SlackEvent model."""
        event = SlackEvent(
            type="app_mention",
            user="U123456789",
            channel="C123456789",
            text="Hello bot",
            ts="1642781234.123456"
        )
        
        assert event.type == "app_mention"
        assert event.user == "U123456789"
        assert event.channel == "C123456789"
    
    def test_slack_query_request(self):
        """Test SlackQueryRequest model."""
        request = SlackQueryRequest(
            query="show me exceptions",
            user_id="U123456789",
            channel_id="C123456789",
            tenant="test-tenant"
        )
        
        assert request.query == "show me exceptions"
        assert request.tenant == "test-tenant"
    
    def test_slack_query_response(self):
        """Test SlackQueryResponse model."""
        response = SlackQueryResponse(
            answer="Found 5 exceptions",
            confidence=0.85,
            exception_count=5
        )
        
        assert response.answer == "Found 5 exceptions"
        assert response.confidence == 0.85
        assert response.exception_count == 5
        assert response.sources == []  # Default empty list
    
    def test_exception_summary(self):
        """Test ExceptionSummary model."""
        summary = ExceptionSummary(
            id=1,
            tenant="test-tenant",
            order_id="ORD-123",
            reason_code="PICK_DELAY",
            severity="MEDIUM",
            status="OPEN",
            created_at=datetime.now(timezone.utc)
        )
        
        assert summary.id == 1
        assert summary.order_id == "ORD-123"
        assert summary.reason_code == "PICK_DELAY"


@pytest.mark.asyncio
async def test_slack_webhook_signature_verification():
    """Test Slack webhook signature verification."""
    from app.routes.slack import verify_slack_signature
    import time
    
    # Test data
    body = b'{"type":"url_verification","challenge":"test"}'
    timestamp = str(int(time.time()))
    signing_secret = "test-secret"
    
    # Create valid signature
    import hashlib
    import hmac
    
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    signature = 'v0=' + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Test valid signature
    assert verify_slack_signature(body, timestamp, signature, signing_secret)
    
    # Test invalid signature
    assert not verify_slack_signature(body, timestamp, "invalid", signing_secret)
    
    # Test old timestamp
    old_timestamp = str(int(time.time()) - 400)  # 400 seconds ago
    assert not verify_slack_signature(body, old_timestamp, signature, signing_secret)
