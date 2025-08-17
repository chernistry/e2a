# ==== AI EXCEPTION ANALYST SERVICE ==== #

"""
AI Exception Analyst service for generating exception narratives.

This module provides comprehensive AI-powered exception analysis
with intelligent fallback mechanisms, caching, and PII redaction
for secure and reliable exception handling across all tenants.
"""

import hashlib
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import ExceptionRecord
from app.services.ai_client import get_ai_client
from app.schemas.ai import ExceptionLabel
from app.settings import settings
from app.observability.tracing import get_tracer
from app.observability.metrics import ai_fallback_rate, ai_confidence_score
from app.security.pii import redact_context


tracer = get_tracer(__name__)

# In-memory cache for AI responses (keyed by content hash)
_analysis_cache: Dict[str, Dict[str, Any]] = {}


# ==== MAIN ANALYSIS FUNCTION ==== #


async def analyze_exception_or_fallback(
    db: AsyncSession,
    exception: ExceptionRecord
) -> None:
    """
    Analyze exception with AI or use fallback logic.
    
    Implements intelligent exception analysis with AI integration
    and comprehensive fallback mechanisms for operational reliability.
    
    Args:
        db (AsyncSession): Database session for persistence
        exception (ExceptionRecord): Exception record to analyze
    """
    with tracer.start_as_current_span("analyze_exception") as span:
        span.set_attribute("exception_id", exception.id)
        span.set_attribute("reason_code", exception.reason_code)
        span.set_attribute("ai_mode", settings.AI_MODE)
        
        print(f"🤖 AI Analysis for exception {exception.id}, mode: {settings.AI_MODE}")
        
        try:
            # Ensure the exception object is properly loaded in async context
            await db.refresh(exception)
            
        except Exception as e:
            # Log error but don't propagate to avoid breaking the main flow
            print(f"Warning: Exception analysis failed for {exception.id}: {e}")
            span.set_attribute("analysis_failed", True)
            span.set_attribute("error", str(e))
        
        span.set_attribute("tenant", exception.tenant)
        
        # Check if already analyzed
        if exception.ops_note and exception.client_note:
            span.set_attribute("already_analyzed", True)
            print(f"⚡ Exception {exception.id} already analyzed, skipping")
            return
        
        # Handle different AI modes
        if settings.AI_MODE == "fallback":
            print(f"⚡ Using fallback for {exception.id} (AI_MODE=fallback)")
            await _apply_fallback_analysis(db, exception)
            ai_fallback_rate.labels(operation="exception_analysis").set(1.0)
            span.set_attribute("analysis_source", "fallback")
            span.set_attribute("fallback_reason", "mode_forced_fallback")
            return
        
        if settings.AI_MODE == "full":
            print(f"🎯 Forcing AI for {exception.id} (AI_MODE=full)")
            ai_result = await _try_ai_analysis(exception)
            if not ai_result:
                print(f"❌ AI required but failed for {exception.id}")
                raise Exception(f"AI required but failed for {exception.id}")
            
            print(f"✅ AI analysis successful for {exception.id}, confidence: {ai_result.get('confidence', 0.0)}")
            await _apply_ai_analysis(db, exception, ai_result)
            ai_fallback_rate.labels(operation="exception_analysis").set(0.0)
            ai_confidence_score.labels(operation="exception_analysis").observe(
                ai_result.get("confidence", 0.0)
            )
            span.set_attribute("analysis_source", "ai")
            span.set_attribute("confidence", ai_result.get("confidence", 0.0))
            return
        
        # Smart mode - existing logic
        print(f"🧠 Using smart mode for {exception.id}")
        ai_result = await _try_ai_analysis(exception)
        
        if ai_result and _is_high_confidence(ai_result):
            # Use AI analysis
            print(f"✅ High confidence AI result for {exception.id}: {ai_result.get('confidence', 0.0)}")
            await _apply_ai_analysis(db, exception, ai_result)
            ai_fallback_rate.labels(operation="exception_analysis").set(0.0)
            
            # Record confidence score
            ai_confidence_score.labels(operation="exception_analysis").observe(
                ai_result.get("confidence", 0.0)
            )
            
            span.set_attribute("analysis_source", "ai")
            span.set_attribute("confidence", ai_result.get("confidence", 0.0))
            
        else:
            # Use fallback logic
            print(f"⚡ Using fallback for {exception.id} (low confidence or AI unavailable)")
            await _apply_fallback_analysis(db, exception)
            ai_fallback_rate.labels(operation="exception_analysis").set(1.0)
            
            span.set_attribute("analysis_source", "fallback")
            span.set_attribute("fallback_reason", 
                             "low_confidence" if ai_result else "ai_unavailable")


# ==== AI ANALYSIS INTEGRATION ==== #


async def _try_ai_analysis(exception: ExceptionRecord) -> Optional[Dict[str, Any]]:
    """
    Try to analyze exception using AI.
    
    Attempts AI-powered exception analysis with comprehensive
    caching and error handling for optimal performance and reliability.
    
    Args:
        exception (ExceptionRecord): Exception record to analyze
        
    Returns:
        Optional[Dict[str, Any]]: AI analysis result or None if failed
    """
    print(f"🔍 Attempting AI analysis for exception {exception.id}")
    
    try:
        # Check cache first
        cache_key = _get_cache_key(exception)
        print(f"🔑 Cache key: {cache_key}")
        
        if cache_key in _analysis_cache:
            print(f"💾 Cache hit for exception {exception.id}")
            return _analysis_cache[cache_key]
        
        print(f"🆕 Cache miss, making AI request for exception {exception.id}")
        
        # Prepare context for AI
        context = _prepare_ai_context(exception)
        print(f"📋 AI context: {context}")
        
        # Get AI client and analyze
        ai_client = get_ai_client()
        print(f"🤖 Calling AI client for exception {exception.id}")
        
        result = await ai_client.classify_exception(context)
        print(f"✅ AI analysis result for {exception.id}: {result}")
        
        # Cache the result
        _analysis_cache[cache_key] = result
        print(f"💾 Cached result for exception {exception.id}")
        
        return result
        
    except Exception as e:
        # Log error but don't fail - fallback will handle
        print(f"❌ AI analysis failed for exception {exception.id}: {type(e).__name__}: {e}")
        
        with tracer.start_as_current_span("ai_analysis_error") as span:
            span.set_attribute("error", str(e))
            span.set_attribute("error_type", type(e).__name__)
            span.set_attribute("exception_id", exception.id)
        
        return None


# ==== CACHE MANAGEMENT ==== #


def _get_cache_key(exception: ExceptionRecord) -> str:
    """
    Generate cache key for exception analysis.
    
    Creates deterministic cache keys based on exception attributes
    to enable efficient caching and prevent duplicate AI calls.
    
    Args:
        exception (ExceptionRecord): Exception record for key generation
        
    Returns:
        str: Cache key string for lookup and storage
    """
    # Create signature from key exception attributes
    signature_data = f"{exception.tenant}:{exception.reason_code}:{exception.order_id[-4:]}"
    
    # Add context data if available
    if exception.context_data:
        context_str = str(sorted(exception.context_data.items()))
        signature_data += f":{context_str}"
    
    return hashlib.md5(signature_data.encode()).hexdigest()


# ==== CONTEXT PREPARATION ==== #


def _prepare_ai_context(exception: ExceptionRecord) -> Dict[str, Any]:
    """
    Prepare context for AI analysis.
    
    Builds comprehensive context dictionary for AI analysis
    with PII redaction and structured data extraction.
    
    Args:
        exception (ExceptionRecord): Exception record for context building
        
    Returns:
        Dict[str, Any]: Context dictionary ready for AI analysis
    """
    context = {
        "reason_code": exception.reason_code,
        "order_id_suffix": exception.order_id[-4:] if len(exception.order_id) >= 4 else exception.order_id,
        "tenant": exception.tenant,
        "severity": exception.severity,
        "status": exception.status
    }
    
    # Add context data if available
    if exception.context_data:
        # Safely extract timing information
        context.update({
            "duration_minutes": exception.context_data.get("actual_minutes", 0),
            "sla_minutes": exception.context_data.get("sla_minutes", 0),
            "delay_minutes": exception.context_data.get("delay_minutes", 0)
        })
    
    # Redact PII
    return redact_context(context)


# ==== CONFIDENCE VALIDATION ==== #


def _is_high_confidence(ai_result: Dict[str, Any]) -> bool:
    """
    Check if AI result meets confidence threshold.
    
    Validates AI analysis confidence against configurable
    thresholds to ensure quality and reliability.
    
    Args:
        ai_result (Dict[str, Any]): AI analysis result to validate
        
    Returns:
        bool: True if confidence is above threshold
    """
    confidence = ai_result.get("confidence", 0.0)
    min_confidence = settings.AI_MIN_CONFIDENCE
    
    return isinstance(confidence, (int, float)) and confidence >= min_confidence


# ==== ANALYSIS APPLICATION ==== #


async def _apply_ai_analysis(
    db: AsyncSession,
    exception: ExceptionRecord,
    ai_result: Dict[str, Any]
) -> None:
    """
    Apply AI analysis to exception record.
    
    Updates exception record with AI-generated analysis
    including labels, confidence scores, and narrative notes.
    
    Args:
        db (AsyncSession): Database session for persistence
        exception (ExceptionRecord): Exception record to update
        ai_result (Dict[str, Any]): AI analysis result to apply
    """
    # Validate and set AI label
    label = ai_result.get("label", "OTHER")
    if label in ExceptionLabel.__members__:
        exception.ai_label = label
    else:
        exception.ai_label = "OTHER"
    
    # Set confidence score
    exception.ai_confidence = ai_result.get("confidence", 0.0)
    
    # Set notes
    exception.ops_note = ai_result.get("ops_note", "")[:2000]  # Truncate if too long
    exception.client_note = ai_result.get("client_note", "")[:1000]
    
    # Update timestamp
    exception.updated_at = exception.updated_at  # Trigger update
    
    await db.flush()


async def _apply_fallback_analysis(
    db: AsyncSession,
    exception: ExceptionRecord
) -> None:
    """
    Apply fallback analysis to exception record.
    
    Implements rule-based fallback analysis when AI is unavailable
    or produces low-confidence results for operational reliability.
    
    Args:
        db (AsyncSession): Database session for persistence
        exception (ExceptionRecord): Exception record to update
    """
    # Use reason code as label if valid
    if exception.reason_code in ExceptionLabel.__members__:
        exception.ai_label = exception.reason_code
    else:
        exception.ai_label = "OTHER"
    
    # No confidence score for fallback
    exception.ai_confidence = None
    
    # Generate fallback notes based on reason code
    fallback_notes = _generate_fallback_notes(exception)
    exception.ops_note = fallback_notes["ops_note"]
    exception.client_note = fallback_notes["client_note"]
    
    await db.flush()


# ==== FALLBACK NOTE GENERATION ==== #


def _generate_fallback_notes(exception: ExceptionRecord) -> Dict[str, str]:
    """
    Generate fallback notes for exception.
    
    Creates comprehensive operational and client-facing notes
    based on reason codes and context data for consistent
    communication across all exception types.
    
    Args:
        exception (ExceptionRecord): Exception record for note generation
        
    Returns:
        Dict[str, str]: Dictionary with ops_note and client_note
    """
    reason_code = exception.reason_code
    order_suffix = exception.order_id[-4:] if len(exception.order_id) >= 4 else exception.order_id
    
    # Get delay information from context if available
    delay_info = ""
    if exception.context_data:
        delay_minutes = exception.context_data.get("delay_minutes", 0)
        if delay_minutes > 0:
            delay_info = f" (delayed by {delay_minutes} minutes)"
    
    # Generate notes based on reason code
    notes_map = {
        "PICK_DELAY": {
            "ops_note": f"[Rules] Pick operation exceeded SLA threshold{delay_info}. Check station capacity and worker allocation. Review order complexity and inventory location.",
            "client_note": f"Your order is taking longer than expected to pick from our warehouse. We're working to get it processed soon."
        },
        "PACK_DELAY": {
            "ops_note": f"[Rules] Pack operation exceeded SLA threshold{delay_info}. Check packing station efficiency and material availability. Review order size and packaging requirements.",
            "client_note": f"Your order is taking longer than expected to pack. We're working to get it ready for shipment soon."
        },
        "CARRIER_ISSUE": {
            "ops_note": f"[Rules] Carrier pickup/delivery exceeded SLA threshold{delay_info}. Contact carrier for status update. Check manifest and tracking information.",
            "client_note": f"There may be a delay with your shipment. We're working with our carrier partner to resolve this quickly."
        },
        "MISSING_SCAN": {
            "ops_note": f"[Rules] Expected scan event not received{delay_info}. Check scanner connectivity and worker training. Verify process compliance.",
            "client_note": f"We're tracking your order through our fulfillment process. Updates will be provided as they become available."
        },
        "STOCK_MISMATCH": {
            "ops_note": f"[Rules] Inventory count mismatch detected for order {order_suffix}. Perform cycle count and investigate discrepancy. Check for damaged or misplaced items.",
            "client_note": f"We're verifying inventory for your order. This may cause a brief delay, but we'll update you with any changes."
        },
        "ADDRESS_ERROR": {
            "ops_note": f"[Rules] Shipping address validation failed for order {order_suffix}. Contact customer for address verification. Check address format and postal codes.",
            "client_note": f"We need to verify your shipping address to ensure successful delivery. Please check your contact information."
        },
        "SYSTEM_ERROR": {
            "ops_note": f"[Rules] System or integration error detected for order {order_suffix}. Check system logs and API connectivity. Escalate to technical team immediately.",
            "client_note": f"We're experiencing a technical issue with your order. Our team is working to resolve this quickly."
        }
    }
    
    # Default fallback
    default_notes = {
        "ops_note": f"[Rules] Operational exception detected for order {order_suffix}{delay_info}. Investigate root cause and take corrective action.",
        "client_note": f"We're working on your order and will provide updates as they become available."
    }
    
    return notes_map.get(reason_code, default_notes)


# ==== CACHE MANAGEMENT UTILITIES ==== #


def clear_analysis_cache() -> None:
    """
    Clear the analysis cache.
    
    Provides manual cache clearing capability for memory management
    and testing scenarios requiring fresh AI analysis.
    """
    global _analysis_cache
    _analysis_cache.clear()


def get_cache_stats() -> Dict[str, int]:
    """
    Get cache statistics.
    
    Provides cache performance metrics and size information
    for monitoring and optimization purposes.
    
    Returns:
        Dict[str, int]: Dictionary with cache statistics
    """
    return {
        "cache_size": len(_analysis_cache),
        "max_cache_size": 1000  # Could be configurable
    }
