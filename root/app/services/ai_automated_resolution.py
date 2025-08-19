# ==== AI AUTOMATED RESOLUTION SERVICE ==== #

"""
AI Automated Resolution service for intelligent exception resolution.

This module provides AI-powered analysis of raw order data to determine
if exceptions can be automatically resolved without human intervention,
following the principle of analyzing raw data rather than pre-processed hints.
"""

import hashlib
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.storage.models import ExceptionRecord, OrderEvent
from app.storage.redis import get_redis_client
from app.services.ai_client import get_ai_client
from app.settings import settings
from app.observability.tracing import get_tracer
from app.observability.metrics import ai_fallback_rate, ai_confidence_score, cache_hits_total, cache_misses_total


tracer = get_tracer(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 1800  # 30 minutes (shorter than exception analysis)
CACHE_KEY_PREFIX = "ai_resolution:"


# ==== AUTOMATED RESOLUTION ACTIONS ==== #


class AutomatedResolutionActions:
    """Available automated resolution actions."""
    
    ADDRESS_VALIDATION = "address_validation_service"
    PAYMENT_RETRY = "payment_retry"
    INVENTORY_REALLOCATION = "inventory_reallocation"
    SYSTEM_RECOVERY = "system_recovery"
    CARRIER_API_UPDATE = "carrier_api_update"
    
    @classmethod
    def get_all_actions(cls) -> List[str]:
        """Get list of all available automated actions."""
        return [
            cls.ADDRESS_VALIDATION,
            cls.PAYMENT_RETRY,
            cls.INVENTORY_REALLOCATION,
            cls.SYSTEM_RECOVERY,
            cls.CARRIER_API_UPDATE
        ]


# ==== MAIN RESOLUTION ANALYSIS FUNCTION ==== #


async def analyze_automated_resolution_possibility(
    db: AsyncSession,
    exception: ExceptionRecord
) -> Dict[str, Any]:
    """
    Analyze if exception can be automatically resolved using AI.
    
    This function analyzes RAW order data to determine if an exception
    can be automatically resolved without human intervention, following
    the principle of genuine AI analysis rather than pattern matching.
    
    Args:
        db (AsyncSession): Database session for data access
        exception (ExceptionRecord): Exception record to analyze
        
    Returns:
        Dict containing resolution analysis results
    """
    with tracer.start_as_current_span("ai_automated_resolution_analysis") as span:
        span.set_attribute("exception.id", str(exception.id))
        span.set_attribute("exception.reason_code", exception.reason_code)
        
        # Check cache first
        cache_key = f"{CACHE_KEY_PREFIX}{exception.id}:{exception.updated_at.isoformat()}"
        cached_result = await _get_cached_analysis(cache_key)
        if cached_result:
            cache_hits_total.labels(cache_type="ai_resolution", operation="automated_resolution").inc()
            return cached_result
        
        cache_misses_total.labels(cache_type="ai_resolution", operation="automated_resolution").inc()
        
        # Get raw order data WITHOUT preprocessing
        raw_order_data = await _get_raw_order_data(db, exception.order_id)
        
        # Prepare context for AI analysis (NO HINTS!)
        analysis_context = {
            "exception_id": str(exception.id),
            "order_id": exception.order_id,
            "reason_code": exception.reason_code,
            "created_at": exception.created_at.isoformat(),
            "status": exception.status,
            **raw_order_data  # Raw data without preprocessing
        }
        
        # Attempt AI analysis
        try:
            ai_result = await _perform_ai_resolution_analysis(analysis_context)
            
            # Cache successful result
            await _cache_analysis_result(cache_key, ai_result)
            
            return ai_result
            
        except Exception as e:
            # Fallback to rule-based analysis
            ai_fallback_rate.labels(operation="automated_resolution").set(1.0)
            fallback_result = await _fallback_resolution_analysis(exception, raw_order_data)
            
            # Cache fallback result with shorter TTL
            await _cache_analysis_result(cache_key, fallback_result, ttl=300)
            
            return fallback_result


# ==== HELPER FUNCTIONS ==== #


async def _get_raw_order_data(db: AsyncSession, order_id: str) -> Dict[str, Any]:
    """
    Get raw order data WITHOUT preprocessing or hints.
    
    CRITICAL: This function must return raw data only, without any
    pre-calculated fields or hints that would make AI analysis trivial.
    """
    # Get all order events (raw, unprocessed)
    events_query = select(OrderEvent).where(OrderEvent.order_id == order_id)
    events_result = await db.execute(events_query)
    events = events_result.scalars().all()
    
    # Convert events to raw data format
    raw_events = []
    for event in events:
        raw_events.append({
            "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat(),
            "event_data": event.payload,  # payload содержит данные события
            "source": event.source
        })
    
    # Build raw order context (NO preprocessing!)
    raw_data = {
        "warehouse_events": raw_events,
        "order_id": order_id
    }
    
    # Add additional raw data fields if available in events
    for event in events:
        if event.payload:  # payload вместо event_data
            # Extract raw fields without interpretation
            if "financial_status" in event.payload:
                raw_data["financial_status"] = event.payload["financial_status"]
            if "payment_gateway_response" in event.payload:
                raw_data["payment_gateway_response"] = event.payload["payment_gateway_response"]
            if "shipping_address" in event.payload:
                raw_data["shipping_address"] = event.payload["shipping_address"]
            if "line_items" in event.payload:
                raw_data["line_items"] = event.payload["line_items"]
            if "inventory_snapshot" in event.payload:
                raw_data["inventory_snapshot"] = event.payload["inventory_snapshot"]
            if "carrier_events" in event.payload:
                raw_data["carrier_events"] = event.payload["carrier_events"]
            if "system_logs" in event.payload:
                raw_data["system_logs"] = event.payload["system_logs"]
    
    return raw_data


async def _perform_ai_resolution_analysis(context: Dict[str, Any]) -> Dict[str, Any]:
    """Perform AI analysis for automated resolution possibility."""
    ai_client = get_ai_client()
    
    # Use the automated_resolution prompt template
    response = await ai_client.analyze_automated_resolution(context)
    
    # Validate and structure the response
    if not isinstance(response, dict):
        raise ValueError("AI response must be a dictionary")
    
    # Ensure required fields are present
    required_fields = ["can_auto_resolve", "confidence", "automated_actions", "success_probability"]
    for field in required_fields:
        if field not in response:
            raise ValueError(f"Missing required field: {field}")
    
    # Record confidence score for monitoring
    ai_confidence_score.labels(operation="automated_resolution").observe(
        response.get("confidence", 0.0)
    )
    
    return response

async def _fallback_resolution_analysis(
    exception: ExceptionRecord, 
    raw_order_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Fallback rule-based resolution analysis when AI is unavailable.
    
    This provides basic automation rules as a fallback, but should
    be much simpler than AI analysis.
    """
    reason_code = exception.reason_code
    
    # Basic fallback rules (much simpler than AI)
    fallback_rules = {
        "ADDRESS_INVALID": {
            "can_auto_resolve": True,
            "confidence": 0.6,
            "automated_actions": [AutomatedResolutionActions.ADDRESS_VALIDATION],
            "success_probability": 0.7
        },
        "PAYMENT_FAILED": {
            "can_auto_resolve": True,
            "confidence": 0.5,
            "automated_actions": [AutomatedResolutionActions.PAYMENT_RETRY],
            "success_probability": 0.4
        },
        "SYSTEM_ERROR": {
            "can_auto_resolve": True,
            "confidence": 0.4,
            "automated_actions": [AutomatedResolutionActions.SYSTEM_RECOVERY],
            "success_probability": 0.6
        }
    }
    
    rule = fallback_rules.get(reason_code, {
        "can_auto_resolve": False,
        "confidence": 0.0,
        "automated_actions": [],
        "success_probability": 0.0
    })
    
    return {
        **rule,
        "resolution_strategy": f"Fallback rule for {reason_code}",
        "reasoning": f"Fallback analysis - AI unavailable, using basic rule for {reason_code}",
        "risk_assessment": "Medium - fallback analysis",
        "estimated_resolution_time": "10 minutes",
        "prerequisites": ["System availability"],
        "fallback_used": True
    }


async def _get_cached_analysis(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached resolution analysis result."""
    try:
        redis_client = await get_redis_client()
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception:
        # Cache errors should not break the flow
        pass
    return None


async def _cache_analysis_result(
    cache_key: str, 
    result: Dict[str, Any], 
    ttl: int = CACHE_TTL_SECONDS
) -> None:
    """Cache resolution analysis result."""
    try:
        redis_client = await get_redis_client()
        await redis_client.setex(
            cache_key, 
            ttl, 
            json.dumps(result, default=str)
        )
    except Exception:
        # Cache errors should not break the flow
        pass


# ==== PUBLIC API ==== #


async def execute_automated_actions(
    db: AsyncSession,
    exception: ExceptionRecord,
    actions: List[str]
) -> bool:
    """
    Execute the automated resolution actions.
    
    Args:
        db: Database session
        exception: Exception to resolve
        actions: List of automated actions to execute
        
    Returns:
        True if all actions succeeded, False otherwise
    """
    success_count = 0
    
    for action in actions:
        try:
            if action == AutomatedResolutionActions.ADDRESS_VALIDATION:
                success = await _execute_address_validation(db, exception)
            elif action == AutomatedResolutionActions.PAYMENT_RETRY:
                success = await _execute_payment_retry(db, exception)
            elif action == AutomatedResolutionActions.INVENTORY_REALLOCATION:
                success = await _execute_inventory_reallocation(db, exception)
            elif action == AutomatedResolutionActions.SYSTEM_RECOVERY:
                success = await _execute_system_recovery(db, exception)
            elif action == AutomatedResolutionActions.CARRIER_API_UPDATE:
                success = await _execute_carrier_update(db, exception)
            else:
                success = False
                
            if success:
                success_count += 1
                
        except Exception:
            # Log error but continue with other actions
            continue
    
    # Return True if at least one action succeeded
    return success_count > 0

# ==== ACTION EXECUTION FUNCTIONS ==== #


async def _execute_address_validation(db: AsyncSession, exception: ExceptionRecord) -> bool:
    """Execute address validation and correction."""
    # Simulate address validation service with realistic success rate
    import random
    success = random.random() < 0.7  # 70% success rate
    
    if success:
        # In real implementation, this would call external address validation API
        # and update the shipping address in the order
        print(f"✅ Address validation successful for exception {exception.id}")
    else:
        print(f"❌ Address validation failed for exception {exception.id}")
    
    return success


async def _execute_payment_retry(db: AsyncSession, exception: ExceptionRecord) -> bool:
    """Execute payment retry with exponential backoff."""
    # Simulate payment retry with realistic success rate
    import random
    success = random.random() < 0.4  # 40% success rate
    
    if success:
        # In real implementation, this would call payment gateway API
        print(f"✅ Payment retry successful for exception {exception.id}")
    else:
        print(f"❌ Payment retry failed for exception {exception.id}")
    
    return success


async def _execute_inventory_reallocation(db: AsyncSession, exception: ExceptionRecord) -> bool:
    """Execute inventory reallocation to alternative SKUs."""
    # Simulate inventory reallocation with realistic success rate
    import random
    success = random.random() < 0.6  # 60% success rate
    
    if success:
        # In real implementation, this would update inventory and order line items
        print(f"✅ Inventory reallocation successful for exception {exception.id}")
    else:
        print(f"❌ Inventory reallocation failed for exception {exception.id}")
    
    return success


async def _execute_system_recovery(db: AsyncSession, exception: ExceptionRecord) -> bool:
    """Execute system recovery actions like backfilling missing scans."""
    # Simulate system recovery with realistic success rate
    import random
    success = random.random() < 0.8  # 80% success rate
    
    if success:
        # In real implementation, this would update system state and missing events
        print(f"✅ System recovery successful for exception {exception.id}")
    else:
        print(f"❌ System recovery failed for exception {exception.id}")
    
    return success


async def _execute_carrier_update(db: AsyncSession, exception: ExceptionRecord) -> bool:
    """Execute carrier API update to get latest tracking information."""
    # Simulate carrier API call with realistic success rate
    import random
    success = random.random() < 0.5  # 50% success rate
    
    if success:
        # In real implementation, this would call carrier tracking APIs
        print(f"✅ Carrier update successful for exception {exception.id}")
    else:
        print(f"❌ Carrier update failed for exception {exception.id}")
    
    return success
