# ==== AI ORDER ANALYZER SERVICE ==== #

"""
AI-powered order problem detection service.

This module provides intelligent order analysis using AI to detect real problems
in order data, replacing hardcoded test pattern detection with genuine pattern
recognition and validation logic.
"""

import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from app.services.ai_client import get_ai_client
from app.services.prompt_loader import get_prompt_loader
from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger
from app.observability.metrics import (
    ai_requests_total,
    ai_fallback_rate,
    ai_failures_total
)
from app.resilience.decorators import ai_resilient
from app.storage.redis import get_redis_client


# ==== MODULE INITIALIZATION ==== #

tracer = get_tracer(__name__)
logger = ContextualLogger(__name__)

# Cache configuration
CACHE_KEY_PREFIX = "ai_order_analysis:"
CACHE_TTL_SECONDS = 3600  # 1 hour


# ==== AI ORDER ANALYZER CLASS ==== #


class AIOrderAnalyzer:
    """
    AI-powered order problem detection service.
    
    Analyzes raw order data using AI to detect potential problems that could
    cause fulfillment issues, replacing hardcoded pattern matching with
    intelligent analysis of addresses, payments, inventory, and order structure.
    """
    
    def __init__(self):
        """Initialize the AI order analyzer."""
        self.ai_client = get_ai_client()
        self.prompt_loader = get_prompt_loader()
    
    @ai_resilient("analyze_order_problems")
    async def analyze_order_problems(
        self, 
        raw_order_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        AI analyzes RAW order data to detect problems.
        
        Performs genuine AI analysis of complete order data without preprocessing
        hints, following the principle of letting AI discover patterns rather
        than matching pre-calculated values.
        
        Args:
            raw_order_data (Dict[str, Any]): Complete raw order JSON without preprocessing
            
        Returns:
            Dict[str, Any]: Analysis result with problems, confidence, and reasoning
            
        Raises:
            RuntimeError: If AI analysis fails and fallback is unavailable
        """
        with tracer.start_as_current_span("ai_analyze_order_problems") as span:
            span.set_attribute("order_id", raw_order_data.get("id", "unknown"))
            
            # Check cache first
            cache_key = await self._get_cache_key(raw_order_data)
            cached_result = await self._get_cached_analysis(cache_key)
            if cached_result:
                span.set_attribute("cache_hit", True)
                return cached_result
            
            span.set_attribute("cache_hit", False)
            start_time = time.time()
            
            try:
                # Prepare context for AI analysis (RAW data only!)
                context = {
                    "order_data": raw_order_data,  # Complete raw order
                    "analysis_timestamp": datetime.utcnow().isoformat()
                }
                
                # AI analysis using dedicated prompt
                ai_response = await self.ai_client.analyze_order_problems(context)
                
                # Parse and validate response
                result = self._parse_ai_response(ai_response)
                
                # Cache successful result
                await self._cache_analysis(cache_key, result)
                
                processing_time = time.time() - start_time
                span.set_attribute("processing_time_ms", int(processing_time * 1000))
                span.set_attribute("has_problems", result.get("has_problems", False))
                span.set_attribute("confidence", result.get("confidence", 0.0))
                span.set_attribute("problems_count", len(result.get("problems", [])))
                
                ai_requests_total.labels(
                    provider="openrouter",
                    model="mistral-nemo",
                    operation="order_analysis"
                ).inc()
                
                logger.info(
                    f"AI order analysis completed",
                    extra={
                        "order_id": raw_order_data.get("id"),
                        "has_problems": result.get("has_problems"),
                        "confidence": result.get("confidence"),
                        "problems_count": len(result.get("problems", [])),
                        "processing_time_ms": int(processing_time * 1000)
                    }
                )
                
                return result
                
            except Exception as e:
                ai_failures_total.labels(
                    provider="openrouter",
                    error_type=type(e).__name__.replace(".", "_").replace(" ", "_")
                ).inc()
                
                logger.warning(f"AI order analysis failed: {e}")
                
                # Set AI fallback rate for monitoring
                ai_fallback_rate.labels(operation="order_analysis").set(1.0)
                
                # Return NULL result for reprocessing (follows established pattern)
                # This allows the system to identify failed AI analysis for retry
                return {
                    "has_problems": None,  # NULL indicates AI failure
                    "confidence": None,    # NULL for reprocessing (established pattern)
                    "problems": None,      # NULL indicates no AI analysis available
                    "reasoning": f"AI analysis failed: {str(e)}",
                    "recommendations": ["Retry AI analysis", "Manual review required"],
                    "risk_assessment": None,  # NULL indicates unknown risk
                    "ai_used": False,
                    "analysis_method": "ai_failed",
                    "error": str(e)
                }
    
    def _parse_ai_response(self, response: str) -> Dict[str, Any]:
        """
        Parse AI response with comprehensive validation.
        
        Args:
            response (str): Raw AI response string
            
        Returns:
            Dict[str, Any]: Parsed and validated analysis result
            
        Raises:
            ValueError: If response format is invalid
        """
        try:
            # Handle both dict and string responses
            if isinstance(response, dict):
                result = response
            else:
                result = json.loads(response)
            
            # Validate required fields
            required_fields = ["has_problems", "confidence", "problems", "reasoning"]
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate confidence score
            confidence = float(result["confidence"])
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(f"Invalid confidence score: {confidence}")
            
            # Validate problems structure
            problems = result["problems"]
            if not isinstance(problems, list):
                raise ValueError("Problems must be a list")
            
            for problem in problems:
                if not isinstance(problem, dict):
                    raise ValueError("Each problem must be a dictionary")
                
                required_problem_fields = ["type", "field", "reason", "severity"]
                for field in required_problem_fields:
                    if field not in problem:
                        raise ValueError(f"Problem missing required field: {field}")
            
            # Add metadata
            result["ai_used"] = True
            result["analysis_method"] = "ai_powered"
            
            return result
            
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as e:
            logger.error(f"Invalid AI response format: {e}")
            raise ValueError(f"Invalid AI response format: {e}")
    
    async def _fallback_analysis(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rule-based fallback when AI fails.
        
        Maintains existing hardcoded checks as fallback only, ensuring
        system reliability when AI service is unavailable.
        
        Args:
            order_data (Dict[str, Any]): Raw order data
            
        Returns:
            Dict[str, Any]: Fallback analysis result
        """
        problems = []
        
        # Extract order details (handle both webhook and direct order formats)
        order = order_data.get("data", {}).get("order", order_data)
        shipping_address = order.get("shipping_address", {})
        
        # Keep existing hardcoded checks as fallback only
        zip_code = shipping_address.get("zip", "")
        if zip_code in ["00000", "99999", "INVALID"] or not zip_code:
            problems.append({
                "type": "ADDRESS_INVALID",
                "field": "zip_code", 
                "reason": "Invalid postal code format (fallback detection)",
                "severity": "MEDIUM"
            })
        
        address1 = shipping_address.get("address1", "")
        city = shipping_address.get("city", "")
        
        if "Nonexistent" in address1 or city == "Nowhere":
            problems.append({
                "type": "ADDRESS_INVALID",
                "field": "address",
                "reason": "Address appears to be test data (fallback detection)",
                "severity": "HIGH"
            })
        
        return {
            "has_problems": len(problems) > 0,
            "confidence": 0.6,  # Lower confidence for rule-based
            "problems": problems,
            "reasoning": "Rule-based fallback analysis - AI service unavailable",
            "recommendations": ["Review address data manually", "Verify customer information"],
            "ai_used": False,
            "analysis_method": "rule_based_fallback"
        }
    
    async def _get_cache_key(self, order_data: Dict[str, Any]) -> str:
        """
        Generate cache key for order analysis.
        
        Args:
            order_data (Dict[str, Any]): Order data
            
        Returns:
            str: Cache key for this analysis
        """
        order_id = order_data.get("id", "unknown")
        # Use order content hash for cache invalidation
        order_hash = hash(json.dumps(order_data, sort_keys=True))
        return f"{CACHE_KEY_PREFIX}{order_id}:{order_hash}"
    
    async def _get_cached_analysis(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached analysis result.
        
        Args:
            cache_key (str): Cache key
            
        Returns:
            Optional[Dict[str, Any]]: Cached result if available
        """
        try:
            redis_client = await get_redis_client()
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")
        return None
    
    async def _cache_analysis(
        self, 
        cache_key: str, 
        result: Dict[str, Any]
    ) -> None:
        """
        Cache analysis result.
        
        Args:
            cache_key (str): Cache key
            result (Dict[str, Any]): Analysis result to cache
        """
        try:
            redis_client = await get_redis_client()
            await redis_client.setex(
                cache_key, 
                CACHE_TTL_SECONDS, 
                json.dumps(result, default=str)
            )
        except Exception as e:
            logger.warning(f"Cache storage failed: {e}")


# ==== GLOBAL SERVICE INSTANCE ==== #

_ai_order_analyzer: Optional[AIOrderAnalyzer] = None


def get_ai_order_analyzer() -> AIOrderAnalyzer:
    """
    Get global AI order analyzer instance.
    
    Returns:
        AIOrderAnalyzer: Global AI order analyzer instance
    """
    global _ai_order_analyzer
    if _ai_order_analyzer is None:
        _ai_order_analyzer = AIOrderAnalyzer()
    return _ai_order_analyzer
