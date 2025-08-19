# ==== INGEST ENDPOINT SCHEMAS ==== #

"""
Pydantic schemas for ingest endpoints in Octup E²A.

This module provides comprehensive data validation schemas for event ingestion
with strict type checking, field validation, and format enforcement for
Shopify, WMS, and carrier event processing.
"""

from datetime import datetime
from typing import Literal, Optional, Dict, Any

from pydantic import BaseModel, Field, validator


# ==== SHOPIFY EVENT SCHEMA ==== #

class ShopifyOrderEvent(BaseModel):
    """
    Shopify order event schema with comprehensive validation.
    
    Provides strict validation for Shopify order events with type checking,
    field constraints, datetime validation, and optional payload support
    for flexible event processing and data integrity.
    """
    
    source: Literal["shopify"] = "shopify"
    event_type: Literal[
        "order_paid",
        "order_fulfilled", 
        "fulfillment_update",
        "order_cancelled"
    ]
    event_id: str = Field(..., min_length=1, max_length=128)
    order_id: str = Field(..., min_length=1, max_length=128)
    occurred_at: str = Field(..., description="ISO 8601 datetime string")
    
    # --► OPTIONAL SHOPIFY FIELDS
    carrier: Optional[str] = Field(None, max_length=64)
    tracking_number: Optional[str] = Field(None, max_length=128)
    address_hash: Optional[str] = Field(None, max_length=64)
    line_count: Optional[int] = Field(None, ge=0)
    total_amount_cents: Optional[int] = Field(None, ge=0)
    
    # --► FLEXIBLE PAYLOAD SUPPORT
    payload: Optional[Dict[str, Any]] = Field(
        None, 
        description="Additional event data and metadata"
    )
    
    # --► IDEMPOTENCY SUPPORT
    idempotency_key: Optional[str] = Field(None, max_length=128)
    
    @validator('occurred_at')
    def validate_occurred_at(cls, v: str) -> str:
        """
        Validate ISO 8601 datetime format.
        
        Args:
            v (str): Datetime string to validate
            
        Returns:
            str: Validated datetime string
            
        Raises:
            ValueError: If datetime format is invalid
        """
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError('occurred_at must be valid ISO 8601 datetime')
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "source": "shopify",
                "event_type": "order_paid",
                "event_id": "evt-1001",
                "order_id": "o-12345",
                "occurred_at": "2025-08-16T10:00:00Z",
                "carrier": "UPS",
                "line_count": 2,
                "total_amount_cents": 2999
            }
        }


class WMSEvent(BaseModel):
    """Warehouse Management System event schema."""
    
    source: Literal["wms"] = "wms"
    event_type: Literal[
        "pick_started",
        "pick_completed",
        "pack_started", 
        "pack_completed",
        "ship_label_printed",
        "label_created",  # Added for test compatibility
        "manifested",
        "exception_reported"
    ]
    event_id: str = Field(..., min_length=1, max_length=128)
    order_id: str = Field(..., min_length=1, max_length=128)
    occurred_at: str = Field(..., description="ISO 8601 datetime string")
    
    # Optional fields
    station: Optional[str] = Field(None, max_length=32)
    worker_id: Optional[str] = Field(None, max_length=32)
    zone: Optional[str] = Field(None, max_length=32)
    items_count: Optional[int] = Field(None, ge=0)
    exception_reason: Optional[str] = Field(None, max_length=128)
    
    # Payload field for additional data
    payload: Optional[Dict[str, Any]] = Field(None, description="Additional event data")
    
    # Idempotency
    idempotency_key: Optional[str] = Field(None, max_length=128)
    
    @validator('occurred_at')
    def validate_occurred_at(cls, v: str) -> str:
        """Validate ISO 8601 datetime format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError('occurred_at must be valid ISO 8601 datetime')
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "source": "wms",
                "event_type": "pick_completed",
                "event_id": "evt-2001",
                "order_id": "o-12345",
                "occurred_at": "2025-08-16T12:30:00Z",
                "station": "PICK-01",
                "worker_id": "W123",
                "items_count": 2
            }
        }


class CarrierEvent(BaseModel):
    """Carrier tracking event schema."""
    
    source: Literal["carrier"] = "carrier"
    event_type: Literal[
        "pickup_scheduled",
        "picked_up",
        "shipment_dispatched",  # Added for test compatibility
        "in_transit",
        "out_for_delivery",
        "delivered",
        "delivery_failed",
        "returned"
    ]
    event_id: str = Field(..., min_length=1, max_length=128)
    order_id: str = Field(..., min_length=1, max_length=128)
    occurred_at: str = Field(..., description="ISO 8601 datetime string")
    
    # Optional fields (can be in payload instead)
    tracking_number: Optional[str] = Field(None, max_length=128)
    carrier_name: Optional[str] = Field(None, max_length=64)
    location: Optional[str] = Field(None, max_length=128)
    delivery_notes: Optional[str] = Field(None, max_length=256)
    signature_required: Optional[bool] = None
    
    # Payload field for additional data
    payload: Optional[Dict[str, Any]] = Field(None, description="Additional event data")
    
    # Idempotency
    idempotency_key: Optional[str] = Field(None, max_length=128)
    
    @validator('occurred_at')
    def validate_occurred_at(cls, v: str) -> str:
        """Validate ISO 8601 datetime format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError('occurred_at must be valid ISO 8601 datetime')
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "source": "carrier",
                "event_type": "delivered",
                "event_id": "evt-3001",
                "order_id": "o-12345",
                "occurred_at": "2025-08-16T16:45:00Z",
                "tracking_number": "1Z999AA1234567890",
                "carrier_name": "UPS",
                "location": "Front door"
            }
        }


class IngestResponse(BaseModel):
    """Response schema for ingest endpoints."""
    
    ok: bool = True
    status: str = "processed"
    message: str = "Event processed successfully"
    event_id: Optional[str] = None
    order_id: Optional[str] = None
    processed_at: Optional[str] = None
    exception_created: bool = False
    reason_code: Optional[str] = None
    exception_id: Optional[int] = None
    correlation_id: Optional[str] = None
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "ok": True,
                "status": "processed",
                "message": "Event processed successfully",
                "event_id": "evt-1001",
                "order_id": "o-12345",
                "processed_at": "2025-08-16T10:00:00Z",
                "exception_created": False,
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }

# Import batch processing schemas
try:
    from .ingest_batch import (
        EventData,
        BatchIngestRequest,
        BatchIngestResponse,
        StreamIngestResponse,
        PerformanceStats
    )
except ImportError:
    # Fallback if batch schemas not available
    pass
