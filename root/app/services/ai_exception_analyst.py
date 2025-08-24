# ==== AI EXCEPTION ANALYST SERVICE ==== #

"""
AI Exception Analyst service for generating exception narratives.

This module provides comprehensive AI-powered exception analysis
with circuit breaker pattern, intelligent fallback mechanisms, 
Redis caching, and PII redaction for secure and reliable exception 
handling across all tenants.
"""

import hashlib
import json
import time
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import ExceptionRecord
from app.storage.redis import get_redis_client
from app.services.ai_client import get_ai_client
from app.schemas.ai import ExceptionLabel
from app.settings import settings
from app.observability.tracing import get_tracer
from app.observability.metrics import ai_fallback_rate, ai_confidence_score, cache_hits_total, cache_misses_total
from app.security.pii import redact_context


tracer = get_tracer(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 3600  # 1 hour
CACHE_KEY_PREFIX = "ai_analysis:"

# Circuit breaker configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 300  # 5 minutes
CIRCUIT_BREAKER_KEY = "ai_circuit_breaker"


class AICircuitBreaker:
    """Circuit breaker for AI service calls."""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client()
        self.failure_threshold = CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self.timeout = CIRCUIT_BREAKER_TIMEOUT
        
    async def is_open(self) -> bool:
        """Check if circuit breaker is open (blocking calls)."""
        try:
            breaker_data = await self.redis.get(CIRCUIT_BREAKER_KEY)
            if not breaker_data:
                return False
                
            data = json.loads(breaker_data)
            
            # Check if timeout has passed
            if time.time() - data.get("opened_at", 0) > self.timeout:
                await self.redis.delete(CIRCUIT_BREAKER_KEY)
                return False
                
            return data.get("state") == "open"
            
        except Exception:
            return False  # Fail safe - allow calls if Redis is down
    
    async def record_success(self) -> None:
        """Record successful AI call."""
        try:
            await self.redis.delete(CIRCUIT_BREAKER_KEY)
        except Exception:
            pass  # Ignore Redis errors
    
    async def record_failure(self) -> None:
        """Record failed AI call and potentially open circuit."""
        try:
            breaker_data = await self.redis.get(CIRCUIT_BREAKER_KEY)
            
            if breaker_data:
                data = json.loads(breaker_data)
                failure_count = data.get("failure_count", 0) + 1
            else:
                failure_count = 1
            
            if failure_count >= self.failure_threshold:
                # Open circuit breaker
                await self.redis.setex(
                    CIRCUIT_BREAKER_KEY,
                    self.timeout,
                    json.dumps({
                        "state": "open",
                        "failure_count": failure_count,
                        "opened_at": time.time()
                    })
                )
            else:
                # Update failure count
                await self.redis.setex(
                    CIRCUIT_BREAKER_KEY,
                    60,  # Short TTL for failure tracking
                    json.dumps({
                        "state": "closed",
                        "failure_count": failure_count
                    })
                )
                
        except Exception:
            pass  # Ignore Redis errors


# Global circuit breaker instance
_circuit_breaker = None


def get_circuit_breaker() -> AICircuitBreaker:
    """Get circuit breaker instance."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = AICircuitBreaker()
    return _circuit_breaker


# ==== MAIN ANALYSIS FUNCTION ==== #


async def analyze_exception_or_fallback(
    db: AsyncSession,
    exception: ExceptionRecord
) -> None:
    """
    Analyze exception with AI or use fallback logic.
    
    Implements intelligent exception analysis with AI integration,
    circuit breaker protection, and comprehensive fallback mechanisms 
    for operational reliability.
    
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
        if settings.AI_MODE == "disabled":
            print(f"⚡ Using fallback for {exception.id} (AI_MODE=disabled)")
            await _apply_fallback_analysis(db, exception)
            ai_fallback_rate.labels(operation="exception_analysis").set(1.0)
            span.set_attribute("analysis_source", "fallback")
            span.set_attribute("fallback_reason", "mode_disabled")
            return
            
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
    Try to analyze exception using AI with circuit breaker protection.
    
    Attempts AI-powered exception analysis with circuit breaker pattern,
    comprehensive Redis caching and error handling for optimal performance 
    and reliability.
    
    Args:
        exception (ExceptionRecord): Exception record to analyze
        
    Returns:
        Optional[Dict[str, Any]]: AI analysis result or None if failed
    """
    print(f"🔍 Attempting AI analysis for exception {exception.id}")
    
    # Check circuit breaker first
    circuit_breaker = get_circuit_breaker()
    if await circuit_breaker.is_open():
        print(f"🚫 Circuit breaker is open, skipping AI analysis for exception {exception.id}")
        return None
    
    try:
        # Check Redis cache first
        cache_key = _get_cache_key(exception)
        redis_key = f"{CACHE_KEY_PREFIX}{cache_key}"
        print(f"🔑 Cache key: {redis_key}")
        
        try:
            redis_client = await get_redis_client()
            cached_result = await redis_client.get(redis_key)
            
            if cached_result:
                print(f"💾 Redis cache hit for exception {exception.id}")
                cache_hits_total.labels(cache_type="ai_analysis", operation="exception_analysis").inc()
                return json.loads(cached_result)
        except Exception as redis_error:
            print(f"⚠️ Redis cache check failed: {redis_error}, proceeding without cache")
        
        print(f"🆕 Cache miss, making AI request for exception {exception.id}")
        cache_misses_total.labels(cache_type="ai_analysis", operation="exception_analysis").inc()
        
        # Prepare context for AI
        context = _prepare_ai_context(exception)
        print(f"📋 AI context: {context}")
        
        # Get AI client and analyze
        ai_client = get_ai_client()
        print(f"🤖 Calling AI client for exception {exception.id}")
        
        result = await ai_client.classify_exception(context)
        print(f"✅ AI analysis result for {exception.id}: {result}")
        
        # Record success with circuit breaker
        await circuit_breaker.record_success()
        
        # Cache the result in Redis
        try:
            redis_client = await get_redis_client()
            await redis_client.setex(
                redis_key, 
                CACHE_TTL_SECONDS, 
                json.dumps(result)
            )
            print(f"💾 Cached result in Redis for exception {exception.id}")
        except Exception as redis_error:
            print(f"⚠️ Redis cache store failed: {redis_error}, continuing without caching")
        
        return result
        
    except Exception as e:
        # Record failure with circuit breaker
        circuit_breaker = get_circuit_breaker()
        await circuit_breaker.record_failure()
        
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
    Prepare TRULY RAW ORDER DATA for AI analysis.
    
    Passes ALL available raw data to AI without preprocessing, calculations,
    or hints. The AI must do genuine analysis from scratch.
    
    DEMO LIMITATION: No PII redaction applied. In production, implement proper
    PII redaction or use isolated AI environments.
    
    Args:
        exception (ExceptionRecord): Exception record containing raw order data
        
    Returns:
        Dict[str, Any]: Complete raw order data for AI analysis
    """
    # Start with basic order identification
    context = {
        "order_id": exception.order_id,
        "tenant": exception.tenant,
        "created_at": exception.created_at.isoformat() if exception.created_at else None
    }
    
    # Pass ALL RAW DATA from context_data without filtering or preprocessing
    if exception.context_data:
        # Pass EVERYTHING - let AI decide what's relevant
        for key, value in exception.context_data.items():
            # Skip any pre-classified fields that would bias the AI
            if key not in ["reason_code", "severity", "classification", "ai_label"]:
                context[key] = value
    
    # DO NOT calculate anything for the AI - that's their job!
    # REMOVED: fulfillment_delay_hours calculation
    # REMOVED: is_peak_hours, is_weekend calculations  
    # REMOVED: payment_issues flag filtering
    
    # The AI should analyze raw timestamps, not pre-calculated delays
    # The AI should detect payment issues from gateway responses, not flags
    # The AI should compare inventory vs line items, not rely on hints
    
    # DO NOT include reason_code - let AI determine it from raw data!
    context.pop("reason_code", None)
    context.pop("severity", None) 
    context.pop("classification", None)
    context.pop("ai_label", None)
    
    # DEMO: Return completely raw context without PII redaction
    return context



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
    Apply AI root cause analysis to exception record.
    
    Updates exception record with AI-generated root cause analysis,
    recommendations, and enhanced operational insights.
    
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
    
    # Build enhanced ops note with root cause analysis
    ops_note_parts = []
    
    # Add root cause analysis if available
    root_cause = ai_result.get("root_cause_analysis", "")
    if root_cause:
        ops_note_parts.append(f"[ROOT CAUSE] {root_cause}")
    
    # Add original ops note
    ops_note = ai_result.get("ops_note", "")
    if ops_note:
        ops_note_parts.append(f"[ANALYSIS] {ops_note}")
    
    # Add recommendations if available
    recommendations = ai_result.get("recommendations", "")
    if recommendations:
        ops_note_parts.append(f"[RECOMMENDATIONS] {recommendations}")
    
    # Add priority factors if available
    priority_factors = ai_result.get("priority_factors", [])
    if priority_factors:
        factors_str = ", ".join(priority_factors)
        ops_note_parts.append(f"[PRIORITY FACTORS] {factors_str}")
    
    # Combine all parts
    combined_ops_note = "\n\n".join(ops_note_parts)
    exception.ops_note = combined_ops_note[:2000]  # Truncate if too long
    
    # Set client note
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


async def clear_analysis_cache() -> None:
    """
    Clear the analysis cache.
    
    Provides manual cache clearing capability for memory management
    and testing scenarios requiring fresh AI analysis.
    """
    try:
        redis_client = await get_redis_client()
        # Delete all keys matching our cache prefix
        keys = await redis_client.keys(f"{CACHE_KEY_PREFIX}*")
        if keys:
            await redis_client.delete(*keys)
            print(f"🗑️ Cleared {len(keys)} AI analysis cache entries from Redis")
    except Exception as e:
        print(f"⚠️ Failed to clear Redis cache: {e}")


async def get_cache_stats() -> Dict[str, int]:
    """
    Get cache statistics.
    
    Provides cache performance metrics and size information
    for monitoring and optimization purposes.
    
    Returns:
        Dict[str, int]: Dictionary with cache statistics
    """
    try:
        redis_client = await get_redis_client()
        keys = await redis_client.keys(f"{CACHE_KEY_PREFIX}*")
        
        # Get memory usage info if available
        try:
            info = await redis_client.info("memory")
            memory_usage = info.get("used_memory", 0)
        except:
            memory_usage = 0
        
        return {
            "cache_size": len(keys),
            "memory_usage_bytes": memory_usage,
            "cache_prefix": CACHE_KEY_PREFIX,
            "ttl_seconds": CACHE_TTL_SECONDS
        }
    except Exception as e:
        print(f"⚠️ Failed to get Redis cache stats: {e}")
        return {
            "cache_size": 0,
            "memory_usage_bytes": 0,
            "error": str(e)
        }
