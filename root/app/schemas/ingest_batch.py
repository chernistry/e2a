"""
Schemas for optimized batch ingestion.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EventData(BaseModel):
    """Single event data for batch processing."""
    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Type of event")
    order_id: str = Field(..., description="Order identifier")
    occurred_at: str = Field(..., description="ISO timestamp when event occurred")
    source: str = Field(default="shopify", description="Event source system")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event payload data")


class BatchIngestRequest(BaseModel):
    """Request for batch event ingestion."""
    events: List[EventData] = Field(..., description="List of events to process")
    batch_id: Optional[str] = Field(None, description="Optional batch identifier")
    priority: str = Field(default="normal", description="Processing priority")
    
    class Config:
        schema_extra = {
            "example": {
                "events": [
                    {
                        "event_id": "evt_001",
                        "event_type": "order_created",
                        "order_id": "#12345",
                        "occurred_at": "2025-08-19T12:00:00Z",
                        "source": "shopify",
                        "data": {
                            "order": {
                                "id": "12345",
                                "total_price": "99.99",
                                "financial_status": "paid"
                            }
                        }
                    }
                ],
                "batch_id": "batch_001",
                "priority": "high"
            }
        }


class BatchIngestResponse(BaseModel):
    """Response for batch event ingestion."""
    processed_count: int = Field(..., description="Number of events processed")
    event_ids: List[str] = Field(..., description="List of processed event IDs")
    status: str = Field(..., description="Overall processing status")
    message: str = Field(..., description="Processing message")
    batch_id: Optional[str] = Field(None, description="Batch identifier")
    processing_time_ms: Optional[float] = Field(None, description="Processing time in milliseconds")
    
    class Config:
        schema_extra = {
            "example": {
                "processed_count": 1500,
                "event_ids": ["evt_001", "evt_002"],
                "status": "success",
                "message": "Processed 1500 events successfully",
                "batch_id": "batch_001",
                "processing_time_ms": 250.5
            }
        }


class StreamIngestResponse(BaseModel):
    """Response for streaming event ingestion."""
    event_id: str = Field(..., description="Event identifier")
    status: str = Field(..., description="Processing status")
    message: str = Field(..., description="Processing message")
    queued_at: str = Field(..., description="When event was queued")
    batch_position: Optional[int] = Field(None, description="Position in current batch")


class PerformanceStats(BaseModel):
    """Performance statistics for the ingestion system."""
    batch_processor: Dict[str, Any] = Field(..., description="Batch processor stats")
    background_queue: Dict[str, Any] = Field(..., description="Background queue stats")
    circuit_breaker: Dict[str, Any] = Field(..., description="Circuit breaker stats")
    rate_limiter: Dict[str, Any] = Field(..., description="Rate limiter stats")
    throughput: Dict[str, float] = Field(default_factory=dict, description="Throughput metrics")
