"""Slack event processor for Oktup E²A."""

import logging
import re
import time
from typing import List, Optional

import httpx
from sqlalchemy import desc, or_, select

from app.integrations.slack.models import (
    ExceptionSummary,
    SlackEvent,
    SlackEventPayload,
    SlackQueryRequest,
    SlackQueryResponse,
    SlackResponse,
)
from app.integrations.slack.rag_service import SlackRAGService
from app.observability.metrics import SLACK_EVENTS_TOTAL
from app.observability.tracing import get_tracer
from app.security.pii import sanitize_for_ai
from app.storage.db import SessionLocal
from app.storage.models import ExceptionRecord

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class SlackEventProcessor:
    """Processes Slack events and generates responses for Oktup E²A."""
    
    def __init__(
        self,
        slack_bot_token: str,
        slack_bot_user_id: str,
        rag_service: Optional[SlackRAGService] = None
    ):
        """Initialize Slack event processor.
        
        Args:
            slack_bot_token: Slack bot token
            slack_bot_user_id: Bot user ID
            rag_service: RAG service for intelligent responses
        """
        self.slack_bot_token = slack_bot_token
        self.slack_bot_user_id = slack_bot_user_id
        self.rag_service = rag_service
        
        # HTTP client for Slack API
        self.slack_client = httpx.AsyncClient(
            base_url="https://slack.com/api",
            headers={
                "Authorization": f"Bearer {slack_bot_token}",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )
    
    async def process_event(
        self,
        payload: SlackEventPayload,
        tenant: str
    ) -> Optional[SlackResponse]:
        """Process Slack event and generate response.
        
        Args:
            payload: Slack event payload
            tenant: Tenant identifier
            
        Returns:
            Slack response or None
        """
        with tracer.start_as_current_span("slack_event_process") as span:
            span.set_attribute("event_type", payload.type)
            span.set_attribute("tenant", tenant)
            
            try:
                if payload.type == "event_callback" and payload.event:
                    response = await self._process_event_callback(
                        payload.event, tenant, span
                    )
                    
                    if response:
                        SLACK_EVENTS_TOTAL.labels(
                            event_type=payload.event.type,
                            status="success",
                            tenant=tenant
                        ).inc()
                    
                    return response
                
                elif payload.type == "url_verification":
                    # Handle Slack URL verification
                    return None
                
                else:
                    logger.debug(f"Ignoring event type: {payload.type}")
                    return None
                    
            except Exception as e:
                logger.error(f"Error processing Slack event: {e}")
                span.set_attribute("error", str(e))
                
                SLACK_EVENTS_TOTAL.labels(
                    event_type=payload.event.type if payload.event else "unknown",
                    status="error",
                    tenant=tenant
                ).inc()
                
                return SlackResponse(
                    text="I encountered an error processing your request. Please try again.",
                    channel=payload.event.channel if payload.event else "",
                    thread_ts=payload.event.thread_ts if payload.event else None
                )
    
    async def _process_event_callback(
        self,
        event: SlackEvent,
        tenant: str,
        span
    ) -> Optional[SlackResponse]:
        """Process event callback.
        
        Args:
            event: Slack event
            tenant: Tenant identifier
            span: OpenTelemetry span
            
        Returns:
            Slack response or None
        """
        span.set_attribute("event_callback_type", event.type)
        
        # Handle app mentions
        if event.type == "app_mention":
            return await self._handle_app_mention(event, tenant, span)
        
        # Handle direct messages
        elif event.type == "message" and event.channel and event.channel.startswith("D"):
            return await self._handle_direct_message(event, tenant, span)
        
        else:
            logger.debug(f"Ignoring event type: {event.type}")
            return None
    
    async def _handle_app_mention(
        self,
        event: SlackEvent,
        tenant: str,
        span
    ) -> Optional[SlackResponse]:
        """Handle app mention events.
        
        Args:
            event: Slack event
            tenant: Tenant identifier
            span: OpenTelemetry span
            
        Returns:
            Slack response or None
        """
        if not event.text or not event.user:
            return None
        
        # Skip bot messages and messages from the bot itself
        if event.user == self.slack_bot_user_id or event.bot_id:
            logger.debug(f"Ignoring bot message from user {event.user}")
            return None
        
        # Skip message subtypes that shouldn't trigger responses
        if hasattr(event, 'subtype') and event.subtype:
            logger.debug(f"Ignoring message with subtype: {event.subtype}")
            return None
        
        span.set_attribute("user_id", event.user)
        span.set_attribute("channel_id", event.channel or "unknown")
        
        # Extract question from mention
        question = self._extract_question_from_mention(event.text)
        
        if not question:
            return self._format_help_response(event.channel, event.thread_ts or event.ts)
        
        # Handle help requests
        if question.lower().strip() in ["help", "?"]:
            return self._format_help_response(event.channel, event.thread_ts or event.ts)
        
        span.set_attribute("question_length", len(question))
        
        # Process the question
        try:
            start_time = time.time()
            
            # Create query request
            query_request = SlackQueryRequest(
                query=question,
                user_id=event.user,
                channel_id=event.channel or "",
                tenant=tenant,
                thread_ts=event.thread_ts
            )
            
            # Process query
            query_response = await self._process_query(query_request)
            
            processing_time = time.time() - start_time
            
            # Format response for Slack
            response = self._format_query_response(
                query_response,
                event.channel or "",
                event.thread_ts or event.ts,
                processing_time
            )
            
            logger.info(
                f"Processed app mention: {len(question)} chars, {processing_time:.2f}s",
                extra={
                    "user_id": event.user,
                    "channel_id": event.channel,
                    "question_length": len(question),
                    "processing_time": processing_time,
                    "tenant": tenant
                }
            )
            
            span.set_attribute("success", True)
            span.set_attribute("processing_time", processing_time)
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing app mention: {e}")
            span.set_attribute("error", str(e))
            
            return SlackResponse(
                text="I encountered an error processing your question. Please try again.",
                channel=event.channel or "",
                thread_ts=event.thread_ts or event.ts
            )
    
    async def _handle_direct_message(
        self,
        event: SlackEvent,
        tenant: str,
        span
    ) -> Optional[SlackResponse]:
        """Handle direct message events.
        
        Args:
            event: Slack event
            tenant: Tenant identifier
            span: OpenTelemetry span
            
        Returns:
            Slack response or None
        """
        if not event.text or not event.user:
            return None
        
        # Skip bot messages and messages from the bot itself
        if event.user == self.slack_bot_user_id or event.bot_id:
            return None
        
        # Skip message subtypes that shouldn't trigger responses
        if hasattr(event, 'subtype') and event.subtype:
            return None
        
        span.set_attribute("user_id", event.user)
        span.set_attribute("is_dm", True)
        
        # Process DM similar to app mention but without mention extraction
        question = event.text.strip()
        
        if question.lower() in ["help", "?"]:
            return self._format_help_response(event.channel, event.thread_ts)
        
        # Create query request
        query_request = SlackQueryRequest(
            query=question,
            user_id=event.user,
            channel_id=event.channel or "",
            tenant=tenant,
            thread_ts=event.thread_ts
        )
        
        # Process query
        query_response = await self._process_query(query_request)
        
        return self._format_query_response(
            query_response,
            event.channel or "",
            event.thread_ts,
            0.0
        )
    
    async def _process_query(self, request: SlackQueryRequest) -> SlackQueryResponse:
        """Process query using RAG service and database.
        
        Args:
            request: Query request
            
        Returns:
            Query response
        """
        # Redact PII from query
        safe_query_data = sanitize_for_ai({"query": request.query})
        safe_query = safe_query_data["query"]
        
        # Try RAG service first if available
        if self.rag_service:
            try:
                rag_response = await self.rag_service.query(
                    query=safe_query,
                    tenant=request.tenant,
                    user_id=request.user_id
                )
                
                if rag_response and rag_response.confidence and rag_response.confidence > 0.7:
                    return rag_response
                    
            except Exception as e:
                logger.warning(f"RAG service failed, falling back to database: {e}")
        
        # Fallback to database query
        return await self._query_database(request)
    
    async def _query_database(self, request: SlackQueryRequest) -> SlackQueryResponse:
        """Query database for exceptions.
        
        Args:
            request: Query request
            
        Returns:
            Query response
        """
        async with SessionLocal() as session:
            # Parse query for keywords
            keywords = self._extract_keywords(request.query)
            
            # Build query
            query = select(ExceptionRecord).filter(
                ExceptionRecord.tenant == request.tenant
            )
            
            # Add keyword filters
            if keywords:
                conditions = []
                for keyword in keywords:
                    conditions.extend([
                        ExceptionRecord.reason_code.ilike(f"%{keyword}%"),
                        ExceptionRecord.ops_note.ilike(f"%{keyword}%"),
                        ExceptionRecord.order_id.ilike(f"%{keyword}%")
                    ])
                
                if conditions:
                    query = query.filter(or_(*conditions))
            
            # Get recent exceptions
            result = await session.execute(
                query.order_by(desc(ExceptionRecord.created_at)).limit(10)
            )
            exceptions = result.scalars().all()
            
            # Convert to summaries
            exception_summaries = [
                ExceptionSummary(
                    id=exc.id,
                    tenant=exc.tenant,
                    order_id=exc.order_id,
                    reason_code=exc.reason_code,
                    severity=exc.severity,
                    status=exc.status,
                    created_at=exc.created_at,
                    ops_note=exc.ops_note,
                    client_note=exc.client_note,
                    ai_confidence=exc.ai_confidence
                )
                for exc in exceptions
            ]
            
            # Generate answer
            if exception_summaries:
                answer = self._generate_database_answer(exception_summaries, request.query)
            else:
                answer = "No matching exceptions found for your query."
            
            return SlackQueryResponse(
                answer=answer,
                sources=[],
                confidence=0.8 if exception_summaries else 0.3,
                exception_count=len(exception_summaries),
                related_exceptions=exception_summaries
            )
    
    def _extract_question_from_mention(self, text: str) -> str:
        """Extract question from app mention text.
        
        Args:
            text: Raw mention text
            
        Returns:
            Extracted question
        """
        # Remove bot mention
        mention_pattern = r'<@[A-Z0-9]+>'
        question = re.sub(mention_pattern, '', text).strip()
        
        return question
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract keywords from query.
        
        Args:
            query: User query
            
        Returns:
            List of keywords
        """
        # Simple keyword extraction
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        return keywords[:5]  # Limit to 5 keywords
    
    def _generate_database_answer(self, exceptions: List[ExceptionSummary], query: str) -> str:
        """Generate answer from database results.
        
        Args:
            exceptions: Exception summaries
            query: Original query
            
        Returns:
            Generated answer
        """
        if not exceptions:
            return "No exceptions found matching your query."
        
        # Group by reason code
        reason_counts = {}
        for exc in exceptions:
            reason_counts[exc.reason_code] = reason_counts.get(exc.reason_code, 0) + 1
        
        # Generate summary
        total = len(exceptions)
        top_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        answer_parts = [
            f"Found {total} recent exceptions matching your query:",
            ""
        ]
        
        for reason, count in top_reasons:
            percentage = (count / total) * 100
            answer_parts.append(f"• {reason}: {count} ({percentage:.1f}%)")
        
        if len(exceptions) > 0:
            latest = exceptions[0]
            answer_parts.extend([
                "",
                f"Latest exception: Order {latest.order_id} ({latest.reason_code})",
                f"Status: {latest.status} | Severity: {latest.severity}"
            ])
            
            if latest.ops_note:
                answer_parts.append(f"Note: {latest.ops_note[:100]}...")
        
        return "\n".join(answer_parts)
    
    def _format_help_response(self, channel: str, thread_ts: Optional[str]) -> SlackResponse:
        """Format help response.
        
        Args:
            channel: Slack channel
            thread_ts: Thread timestamp
            
        Returns:
            Slack response
        """
        help_text = """
🤖 **Oktup E²A Assistant**

I can help you with:
• Query exceptions: "Show me PICK_DELAY exceptions"
• Order status: "What happened to order ORD-123?"
• Trends: "Recent shipping delays"
• Statistics: "Exception summary for today"

Just mention me (@oktup) or send me a direct message!
        """.strip()
        
        return SlackResponse(
            text=help_text,
            channel=channel,
            thread_ts=thread_ts
        )
    
    def _format_query_response(
        self,
        response: SlackQueryResponse,
        channel: str,
        thread_ts: Optional[str],
        processing_time: float
    ) -> SlackResponse:
        """Format query response for Slack.
        
        Args:
            response: Query response
            channel: Slack channel
            thread_ts: Thread timestamp
            processing_time: Processing time in seconds
            
        Returns:
            Slack response
        """
        text_parts = [response.answer]
        
        if response.related_exceptions:
            text_parts.extend([
                "",
                f"📊 Found {len(response.related_exceptions)} related exceptions"
            ])
        
        if processing_time > 0:
            text_parts.append(f"⏱️ Processed in {processing_time:.2f}s")
        
        return SlackResponse(
            text="\n".join(text_parts),
            channel=channel,
            thread_ts=thread_ts
        )
    
    async def send_notification(
        self,
        channel: str,
        message: str,
        thread_ts: Optional[str] = None
    ) -> bool:
        """Send notification to Slack channel.
        
        Args:
            channel: Slack channel
            message: Message to send
            thread_ts: Thread timestamp
            
        Returns:
            Success status
        """
        try:
            payload = {
                "channel": channel,
                "text": message
            }
            
            if thread_ts:
                payload["thread_ts"] = thread_ts
            
            response = await self.slack_client.post("/chat.postMessage", json=payload)
            response.raise_for_status()
            
            result = response.json()
            return result.get("ok", False)
            
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
    
    async def close(self):
        """Close HTTP client."""
        await self.slack_client.aclose()
