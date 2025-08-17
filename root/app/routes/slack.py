# ==== SLACK INTEGRATION ROUTES ==== #

"""
Slack integration routes for Oktup E²A.

This module provides comprehensive Slack integration endpoints including
event webhooks, notification sending, and health monitoring with
full signature verification and tenant isolation support.
"""

import hashlib
import hmac
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from app.integrations.slack.models import SlackEventPayload, SlackNotificationRequest
from app.integrations.slack.processor import SlackEventProcessor
from app.integrations.slack.rag_service import SlackRAGService
from app.middleware.tenancy import get_tenant_id
from app.observability.metrics import SLACK_EVENTS_TOTAL
from app.observability.tracing import get_tracer
from app.services.ai_client import get_ai_client
from app.settings import get_settings


logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
router = APIRouter(prefix="/slack", tags=["slack"])

# Global processor instance (will be initialized on startup)
_slack_processor: Optional[SlackEventProcessor] = None


# ==== SLACK PROCESSOR MANAGEMENT ==== #


def get_slack_processor() -> SlackEventProcessor:
    """
    Get Slack processor instance.
    
    Initializes and returns a singleton SlackEventProcessor instance
    with RAG service integration if AI capabilities are available.
    
    Returns:
        SlackEventProcessor: Configured Slack processor instance
    """
    global _slack_processor
    if _slack_processor is None:
        settings = get_settings()
        
        # Initialize RAG service if AI is available
        rag_service = None
        try:
            ai_client = get_ai_client()
            rag_service = SlackRAGService(ai_client)
        except Exception as e:
            logger.warning(f"RAG service not available: {e}")
        
        _slack_processor = SlackEventProcessor(
            slack_bot_token=settings.slack_bot_token,
            slack_bot_user_id=settings.slack_bot_user_id,
            rag_service=rag_service
        )
    
    return _slack_processor


# ==== SECURITY AND VALIDATION ==== #


def verify_slack_signature(
    request_body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str
) -> bool:
    """
    Verify Slack request signature.
    
    Implements Slack's signature verification algorithm to ensure
    request authenticity and prevent replay attacks with timestamp
    validation and HMAC-SHA256 signature comparison.
    
    Args:
        request_body (bytes): Raw request body bytes
        timestamp (str): Request timestamp from Slack headers
        signature (str): Slack signature from headers
        signing_secret (str): Slack app signing secret
        
    Returns:
        bool: True if signature is valid and timestamp is recent
    """
    # Check timestamp (prevent replay attacks)
    current_time = int(time.time())
    if abs(current_time - int(timestamp)) > 300:  # 5 minutes
        return False
    
    # Create signature
    sig_basestring = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    expected_signature = 'v0=' + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


def get_tenant(request: Request) -> str:
    """
    Get tenant ID from request.
    
    Extracts tenant identifier from the request context for
    multi-tenant Slack integration support.
    
    Args:
        request (Request): FastAPI request object
        
    Returns:
        str: Tenant identifier
    """
    return get_tenant_id(request)


# ==== SLACK EVENT HANDLING ==== #


@router.post("/events")
async def handle_slack_events(
    request: Request,
    tenant: str = Depends(get_tenant)
) -> Any:
    """
    Handle Slack events webhook.
    
    Processes incoming Slack events including message events, app mentions,
    and URL verification challenges with comprehensive signature validation,
    event processing, and response generation.
    
    Args:
        request (Request): FastAPI request with Slack event payload
        tenant (str): Tenant identifier for multi-tenant support
        
    Returns:
        Any: Response for Slack (challenge response or status confirmation)
        
    Raises:
        HTTPException: If signature verification fails or processing errors occur
    """
    with tracer.start_as_current_span("slack_events_webhook") as span:
        span.set_attribute("tenant", tenant)
        
        settings = get_settings()
        
        # Get request data
        body = await request.body()
        headers = request.headers
        
        # Verify signature if signing secret is configured
        if settings.slack_signing_secret:
            timestamp = headers.get("x-slack-request-timestamp", "")
            signature = headers.get("x-slack-signature", "")
            
            if not verify_slack_signature(
                body, timestamp, signature, settings.slack_signing_secret
            ):
                logger.warning("Invalid Slack signature")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid signature"
                )
        
        try:
            # Parse JSON payload
            import json
            payload_data = json.loads(body.decode('utf-8'))
            
            # Handle URL verification
            if payload_data.get("type") == "url_verification":
                challenge = payload_data.get("challenge", "")
                return PlainTextResponse(challenge)
            
            # Parse event payload
            payload = SlackEventPayload(**payload_data)
            span.set_attribute("event_type", payload.type)
            
            # Process event
            processor = get_slack_processor()
            response = await processor.process_event(payload, tenant)
            
            # Send response if generated
            if response:
                success = await processor.send_notification(
                    channel=response.channel,
                    message=response.text,
                    thread_ts=response.thread_ts
                )
                
                if not success:
                    logger.warning("Failed to send Slack response")
            
            # Always return 200 OK to Slack
            return JSONResponse({"status": "ok"})
            
        except Exception as e:
            logger.error(f"Error handling Slack event: {e}")
            span.set_attribute("error", str(e))
            
            SLACK_EVENTS_TOTAL.labels(
                event_type="unknown",
                status="error",
                tenant=tenant
            ).inc()
            
            # Return 200 to prevent Slack retries for application errors
            return JSONResponse({"status": "error", "message": str(e)})


# ==== NOTIFICATION ENDPOINTS ==== #


@router.post("/notify")
async def send_slack_notification(
    notification: SlackNotificationRequest,
    tenant: str = Depends(get_tenant)
) -> Dict[str, Any]:
    """
    Send notification to Slack channel.
    
    Provides programmatic notification sending capability for external
    systems to send messages to Slack channels with tenant validation
    and comprehensive error handling.
    
    Args:
        notification (SlackNotificationRequest): Notification request data
        tenant (str): Tenant identifier for validation
        
    Returns:
        Dict[str, Any]: Success status and channel information
        
    Raises:
        HTTPException: If tenant mismatch or notification sending fails
    """
    with tracer.start_as_current_span("slack_notification") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("channel", notification.channel)
        
        # Verify tenant matches
        if notification.tenant != tenant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant mismatch"
            )
        
        try:
            processor = get_slack_processor()
            success = await processor.send_notification(
                channel=notification.channel,
                message=notification.message,
                thread_ts=notification.thread_ts
            )
            
            if success:
                span.set_attribute("success", True)
                return {"status": "sent", "channel": notification.channel}
            else:
                span.set_attribute("success", False)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to send notification"
                )
                
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            span.set_attribute("error", str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )


# ==== HEALTH MONITORING ==== #


@router.get("/health")
async def slack_health() -> Dict[str, Any]:
    """
    Check Slack integration health.
    
    Verifies Slack API connectivity and bot authentication status
    to ensure the integration is functioning correctly for
    operational monitoring and alerting.
    
    Returns:
        Dict[str, Any]: Health status with bot and team information
    """
    try:
        processor = get_slack_processor()
        
        # Test Slack API connection
        response = await processor.slack_client.get("/auth.test")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                return {
                    "status": "healthy",
                    "bot_user_id": data.get("user_id"),
                    "team": data.get("team")
                }
        
        return {"status": "unhealthy", "error": "Slack API test failed"}
        
    except Exception as e:
        logger.error(f"Slack health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
