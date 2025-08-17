"""Slack integration models for Oktup E²A."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SlackUser(BaseModel):
    """Slack user information."""
    
    id: str
    name: Optional[str] = None
    real_name: Optional[str] = None
    email: Optional[str] = None


class SlackChannel(BaseModel):
    """Slack channel information."""
    
    id: str
    name: Optional[str] = None
    is_private: bool = False


class SlackMessage(BaseModel):
    """Slack message model."""
    
    text: str
    user: str
    channel: str
    ts: str
    thread_ts: Optional[str] = None
    bot_id: Optional[str] = None
    subtype: Optional[str] = None


class SlackEvent(BaseModel):
    """Slack event model."""
    
    type: str
    event: Optional[SlackMessage] = None
    user: Optional[str] = None
    channel: Optional[str] = None
    text: Optional[str] = None
    ts: Optional[str] = None
    thread_ts: Optional[str] = None
    bot_id: Optional[str] = None


class SlackEventPayload(BaseModel):
    """Complete Slack event payload."""
    
    token: str
    team_id: str
    api_app_id: str
    event: SlackEvent
    type: str
    event_id: str
    event_time: int
    authed_users: List[str] = Field(default_factory=list)


class SlackResponse(BaseModel):
    """Slack response model."""
    
    text: str
    channel: str
    thread_ts: Optional[str] = None
    blocks: Optional[List[Dict[str, Any]]] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class ExceptionSummary(BaseModel):
    """Exception summary for Slack notifications."""
    
    id: int
    tenant: str
    order_id: str
    reason_code: str
    severity: str
    status: str
    created_at: datetime
    ops_note: Optional[str] = None
    client_note: Optional[str] = None
    ai_confidence: Optional[float] = None


class SlackNotificationRequest(BaseModel):
    """Request to send Slack notification."""
    
    channel: str
    message: str
    thread_ts: Optional[str] = None
    tenant: str
    exception_id: Optional[int] = None


class SlackQueryRequest(BaseModel):
    """Request for querying exception data via Slack."""
    
    query: str
    user_id: str
    channel_id: str
    tenant: str
    thread_ts: Optional[str] = None


class SlackQueryResponse(BaseModel):
    """Response to Slack query."""
    
    answer: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: Optional[float] = None
    processing_time: Optional[float] = None
    exception_count: Optional[int] = None
    related_exceptions: List[ExceptionSummary] = Field(default_factory=list)
