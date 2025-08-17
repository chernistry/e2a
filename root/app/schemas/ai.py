"""Pydantic schemas for AI operations."""

from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class ExceptionLabel(str, Enum):
    """AI-generated exception labels."""
    PICK_DELAY = "PICK_DELAY"
    PACK_DELAY = "PACK_DELAY"
    CARRIER_ISSUE = "CARRIER_ISSUE"
    STOCK_MISMATCH = "STOCK_MISMATCH"
    ADDRESS_ERROR = "ADDRESS_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    OTHER = "OTHER"


class AIExceptionAnalysis(BaseModel):
    """AI analysis result for exceptions."""
    
    label: ExceptionLabel
    confidence: float = Field(..., ge=0.0, le=1.0)
    ops_note: str = Field(..., max_length=2000)
    client_note: str = Field(..., max_length=1000)
    reasoning: Optional[str] = Field(None, max_length=1000)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "label": "PICK_DELAY",
                "confidence": 0.85,
                "ops_note": "Pick operation exceeded 120-minute SLA by 45 minutes. Station PICK-01 reported high volume during peak hours.",
                "client_note": "Your order is taking longer than expected to pick. We're working to get it out soon.",
                "reasoning": "Based on timing analysis and station capacity data"
            }
        }


class AIRuleLintRequest(BaseModel):
    """Request schema for AI rule linting."""
    
    policy_type: str = Field(..., description="Type of policy (sla, billing, etc.)")
    policy_content: str = Field(..., description="YAML/JSON policy content")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "policy_type": "sla",
                "policy_content": "pick_minutes: 120\npack_minutes: 180\nship_minutes: 1440",
                "context": {"tenant": "demo-3pl"}
            }
        }


class AIRuleLintSuggestion(BaseModel):
    """AI suggestion for policy improvement."""
    
    type: str = Field(..., description="Type of suggestion")
    severity: str = Field(..., description="Severity level")
    message: str = Field(..., description="Suggestion message")
    suggested_fix: Optional[str] = Field(None, description="Suggested fix")
    line_number: Optional[int] = Field(None, description="Line number if applicable")
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "type": "missing_edge_case",
                "severity": "medium",
                "message": "Consider adding handling for weekend/holiday delays",
                "suggested_fix": "Add weekend_multiplier: 1.5 to account for reduced staffing",
                "line_number": 3
            }
        }


class AIRuleLintTest(BaseModel):
    """AI-generated test case for policies."""
    
    name: str = Field(..., description="Test case name")
    given: str = Field(..., description="Given conditions")
    when: str = Field(..., description="When action occurs")
    then: str = Field(..., description="Then expected result")
    test_data: Optional[Dict[str, Any]] = Field(None, description="Test data")
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "name": "pick_delay_detection",
                "given": "Order paid at 10:00 AM",
                "when": "Pick completed at 1:00 PM (180 minutes later)",
                "then": "Should create PICK_DELAY exception (SLA: 120 minutes)",
                "test_data": {
                    "order_paid": "2025-08-16T10:00:00Z",
                    "pick_completed": "2025-08-16T13:00:00Z"
                }
            }
        }


class AIRuleLintResponse(BaseModel):
    """Response schema for AI rule linting."""
    
    suggestions: List[AIRuleLintSuggestion]
    test_cases: List[AIRuleLintTest]
    confidence: float = Field(..., ge=0.0, le=1.0)
    processing_time_ms: int
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "suggestions": [],
                "test_cases": [],
                "confidence": 0.75,
                "processing_time_ms": 1250
            }
        }


class AIProviderConfig(BaseModel):
    """AI provider configuration."""
    
    provider: str = Field(..., description="AI provider name")
    model: str = Field(..., description="Model name")
    base_url: Optional[str] = Field(None, description="Custom base URL")
    api_key: Optional[str] = Field(None, description="API key")
    timeout_seconds: int = Field(3, ge=1, le=30)
    max_retries: int = Field(2, ge=0, le=5)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "timeout_seconds": 3,
                "max_retries": 2
            }
        }


class AIUsageStats(BaseModel):
    """AI usage statistics."""
    
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_tokens: int
    total_cost_cents: int
    avg_confidence: float = Field(..., ge=0.0, le=1.0)
    fallback_rate: float = Field(..., ge=0.0, le=1.0)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "total_requests": 1000,
                "successful_requests": 850,
                "failed_requests": 150,
                "total_tokens": 50000,
                "total_cost_cents": 250,
                "avg_confidence": 0.78,
                "fallback_rate": 0.15
            }
        }
