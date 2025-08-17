"""Pydantic schemas for exception handling."""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field


class ExceptionStatus(str, Enum):
    """Exception status enumeration."""
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class ExceptionSeverity(str, Enum):
    """Exception severity enumeration."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReasonCode(str, Enum):
    """SLA breach reason codes."""
    PICK_DELAY = "PICK_DELAY"
    PACK_DELAY = "PACK_DELAY"
    CARRIER_ISSUE = "CARRIER_ISSUE"
    MISSING_SCAN = "MISSING_SCAN"
    STOCK_MISMATCH = "STOCK_MISMATCH"
    ADDRESS_ERROR = "ADDRESS_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    DELIVERY_DELAY = "DELIVERY_DELAY"
    ADDRESS_INVALID = "ADDRESS_INVALID"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    INVENTORY_SHORTAGE = "INVENTORY_SHORTAGE"
    DAMAGED_PACKAGE = "DAMAGED_PACKAGE"
    CUSTOMER_UNAVAILABLE = "CUSTOMER_UNAVAILABLE"
    OTHER = "OTHER"


class ExceptionResponse(BaseModel):
    """Response schema for exception details."""
    
    id: int
    tenant: str
    order_id: str
    reason_code: ReasonCode
    status: ExceptionStatus
    severity: ExceptionSeverity
    
    # AI analysis
    ai_label: Optional[str] = None
    ai_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    ops_note: Optional[str] = None
    client_note: Optional[str] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    
    # Context
    correlation_id: Optional[str] = None
    context_data: Optional[Dict[str, Any]] = None
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "id": 123,
                "tenant": "demo-3pl",
                "order_id": "o-12345",
                "reason_code": "PICK_DELAY",
                "status": "OPEN",
                "severity": "MEDIUM",
                "ai_label": "PICK_DELAY",
                "ai_confidence": 0.85,
                "ops_note": "Pick operation exceeded 120-minute SLA by 45 minutes. Station PICK-01 reported high volume.",
                "client_note": "Your order is taking longer than expected to pick. We're working to get it out soon.",
                "created_at": "2025-08-16T10:00:00Z",
                "updated_at": "2025-08-16T10:05:00Z",
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


class ExceptionListResponse(BaseModel):
    """Response schema for exception list."""
    
    items: list[ExceptionResponse]
    total: int
    total_items: int  # Alias for total
    page: int = 1
    page_size: int = 20
    has_next: bool = False
    
    def __init__(self, **data):
        # Set total_items to match total if not provided
        if 'total_items' not in data and 'total' in data:
            data['total_items'] = data['total']
        super().__init__(**data)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "items": [],
                "total": 0,
                "total_items": 0,
                "page": 1,
                "page_size": 20,
                "has_next": False
            }
        }


class ExceptionUpdateRequest(BaseModel):
    """Request schema for updating exceptions."""
    
    status: Optional[ExceptionStatus] = None
    severity: Optional[ExceptionSeverity] = None
    ops_note: Optional[str] = Field(None, max_length=2000)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "status": "ACKNOWLEDGED",
                "ops_note": "Investigating with warehouse team"
            }
        }


class ExceptionStatsResponse(BaseModel):
    """Response schema for exception statistics."""
    
    total_exceptions: int
    open_exceptions: int
    resolved_exceptions: int
    by_reason_code: Dict[str, int]
    by_severity: Dict[str, int]
    by_status: Dict[str, int]
    avg_resolution_time_hours: Optional[float] = None
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "total_exceptions": 150,
                "open_exceptions": 25,
                "resolved_exceptions": 125,
                "by_reason_code": {
                    "PICK_DELAY": 45,
                    "PACK_DELAY": 30,
                    "CARRIER_ISSUE": 75
                },
                "by_severity": {
                    "LOW": 50,
                    "MEDIUM": 80,
                    "HIGH": 20
                },
                "by_status": {
                    "OPEN": 25,
                    "RESOLVED": 100,
                    "CLOSED": 25
                },
                "avg_resolution_time_hours": 4.5
            }
        }
