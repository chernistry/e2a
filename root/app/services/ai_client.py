# ==== AI CLIENT SERVICE ==== #

"""
AI client for LLM interactions with multiple provider support in Octup E²A.

This module provides comprehensive AI integration with circuit breaker protection,
token tracking, cost monitoring, and fallback mechanisms for reliable
AI-powered exception analysis and policy validation.
"""

import json
import time
import os
from typing import Dict, Any, Optional

import httpx

from app.settings import settings
from app.observability.tracing import get_tracer
from app.observability.metrics import (
    ai_requests_total, 
    ai_tokens_total, 
    ai_cost_cents_total, 
    ai_failures_total
)
from app.resilience.decorators import ai_resilient
from app.resilience.circuit_breaker import CircuitBreakerError
from app.services.prompt_loader import get_prompt_loader
from app.services.json_extractor import (
    extract_exception_classification, 
    extract_policy_linting
)


# ==== MODULE INITIALIZATION ==== #


tracer = get_tracer(__name__)


# ==== AI CLIENT CLASS ==== #


class AIClient:
    """
    Client for AI/LLM interactions with fallback and monitoring.
    
    Provides comprehensive AI integration with circuit breaker protection,
    token usage tracking, cost monitoring, and automatic fallback mechanisms
    for reliable AI-powered analysis in production environments.
    """
    
    def __init__(self):
        """
        Initialize AI client with configuration and monitoring.
        
        Sets up provider configuration, token tracking, circuit breaker
        integration, and prompt loading for AI operations.
        """
        self.provider = "openai"  # Default to OpenAI-compatible API
        self.model = settings.AI_MODEL
        self.api_key = settings.AI_API_KEY
        
        # ⚠️ Use mock-ai-service for testing, fallback to settings for production
        self.base_url = (
            "http://mock-ai-service" 
            if os.environ.get("APP_ENV") == "test" 
            else settings.AI_PROVIDER_BASE_URL
        )
        
        self.timeout = settings.AI_TIMEOUT_SECONDS
        self.max_retries = settings.AI_RETRY_MAX_ATTEMPTS
        
        # --► TOKEN TRACKING AND BUDGET CONTROL
        self.daily_tokens_used = 0
        self.max_daily_tokens = settings.AI_MAX_DAILY_TOKENS
        
        # --► PROMPT LOADER INITIALIZATION
        self.prompt_loader = get_prompt_loader()


    @ai_resilient("classify_exception")
    async def classify_exception(
        self,
        context: Dict[str, Any],
        prompt_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Classify exception using AI with comprehensive error handling.
        
        Performs AI-powered exception classification with automatic fallback,
        token budget enforcement, and comprehensive monitoring integration.
        
        Args:
            context (Dict[str, Any]): Exception context data for analysis
            prompt_template (Optional[str]): Custom prompt template override
            
        Returns:
            Dict[str, Any]: Classification results with confidence scores
            
        Raises:
            RuntimeError: If AI is disabled or quota exceeded
            CircuitBreakerError: When AI service circuit breaker is open
        """
        if not self.api_key or settings.AI_PROVIDER_BASE_URL == "disabled":
            raise RuntimeError("AI provider disabled")
        
        if self.daily_tokens_used >= self.max_daily_tokens:
            raise RuntimeError("Daily token quota exceeded")
        
        with tracer.start_as_current_span("ai_classify_exception") as span:
            span.set_attribute("provider", self.provider)
            span.set_attribute("model", self.model)
            
            start_time = time.time()
            
            try:
                prompt = self._build_exception_prompt(context, prompt_template)
                raw_result = await self._make_request(prompt, "exception_classification")
                
                # Use robust JSON extraction
                extract_result = await extract_exception_classification(raw_result)
                if not extract_result.success:
                    raise ValueError(f"JSON extraction failed: {extract_result.error}")
                
                parsed_result = extract_result.data
                
                # Update metrics
                processing_time = time.time() - start_time
                span.set_attribute("processing_time_ms", int(processing_time * 1000))
                span.set_attribute("confidence", parsed_result.get("confidence", 0))
                
                ai_requests_total.labels(
                    provider=self.provider,
                    model=self.model,
                    operation="exception_classification"
                ).inc()
                
                return parsed_result
                
            except Exception as e:
                ai_failures_total.labels(
                    provider=self.provider,
                    error_type=type(e).__name__
                ).inc()
                
                span.set_attribute("error", str(e))
                raise


    @ai_resilient("lint_policy")
    async def lint_policy(
        self,
        policy_content: str,
        policy_type: str = "sla"
    ) -> Dict[str, Any]:
        """
        Lint policy configuration using AI.
        
        Analyzes policy configurations for potential issues, missing edge cases,
        and optimization opportunities with comprehensive error handling
        and fallback mechanisms.
        
        Args:
            policy_content (str): YAML/JSON policy content to analyze
            policy_type (str): Type of policy (sla, billing, etc.)
            
        Returns:
            Dict[str, Any]: AI linting result with suggestions and test cases
            
        Raises:
            RuntimeError: If AI is disabled or quota exceeded
        """
        if not self.api_key or settings.AI_PROVIDER_BASE_URL == "disabled":
            raise RuntimeError("AI provider disabled")
        
        if self.daily_tokens_used >= self.max_daily_tokens:
            raise RuntimeError("Daily token quota exceeded")
        
        with tracer.start_as_current_span("ai_lint_policy") as span:
            span.set_attribute("provider", self.provider)
            span.set_attribute("model", self.model)
            span.set_attribute("policy_type", policy_type)
            
            start_time = time.time()
            
            try:
                prompt = self._build_lint_prompt(policy_content, policy_type)
                raw_result = await self._make_request(prompt, "policy_linting")
                
                # Use robust JSON extraction
                extract_result = await extract_policy_linting(raw_result)
                if not extract_result.success:
                    raise ValueError(f"JSON extraction failed: {extract_result.error}")
                
                parsed_result = extract_result.data
                
                # Update metrics
                processing_time = time.time() - start_time
                span.set_attribute("processing_time_ms", int(processing_time * 1000))
                span.set_attribute("suggestions_count", len(parsed_result.get("suggestions", [])))
                span.set_attribute("test_cases_count", len(parsed_result.get("test_cases", [])))
                
                ai_requests_total.labels(
                    provider=self.provider,
                    model=self.model,
                    operation="policy_linting"
                ).inc()
                
                return parsed_result
                
            except Exception as e:
                ai_failures_total.labels(
                    provider=self.provider,
                    error_type=type(e).__name__
                ).inc()
                
                span.set_attribute("error", str(e))
                raise


    # ==== INTERNAL HELPER METHODS ==== #


    async def _make_request(
        self,
        prompt: str,
        operation: str
    ) -> str:
        """
        Make HTTP request to AI provider.
        
        Handles HTTP communication with AI providers including error handling,
        token tracking, cost estimation, and comprehensive fallback mechanisms
        for production reliability.
        
        Args:
            prompt (str): Prompt text to send to AI provider
            operation (str): Operation type for metrics and monitoring
            
        Returns:
            str: Raw API response content or fallback response
        """
        print(f"🌐 Sending request to OpenRouter: {self.base_url}")
        print(f"📝 Model: {self.model}")
        print(f"🔑 API Key: {self.api_key[:20]}..." if self.api_key else "❌ No API Key")
        print(f"📊 Operation: {operation}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 8000
        }
        
        print(f"📤 Request body: {json.dumps(body, indent=2)[:500]}...")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                print(f"⏱️ Making request with timeout: {self.timeout}s")
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers=headers
                )
                
                print(f"✅ OpenRouter response: {response.status_code}")
                print(f"📋 Response headers: {dict(response.headers)}")
                
                response.raise_for_status()
                
                data = response.json()
                print(f"📥 Response data keys: {list(data.keys())}")
                
                # Extract content and usage
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                
                print(f"📊 Usage: {usage}")
                print(f"📝 Content preview: {content[:200]}...")
                
                # Update token tracking
                total_tokens = usage.get("total_tokens", 100)  # Estimate if not provided
                self.daily_tokens_used += total_tokens
                
                print(f"🔢 Tokens used: {total_tokens}, Daily total: {self.daily_tokens_used}/{self.max_daily_tokens}")
                
                # Update metrics
                ai_tokens_total.labels(
                    provider=self.provider,
                    model=self.model,
                    type="prompt"
                ).inc(usage.get("prompt_tokens", 50))
                
                ai_tokens_total.labels(
                    provider=self.provider,
                    model=self.model,
                    type="completion"
                ).inc(usage.get("completion_tokens", 50))
                
                # Estimate cost (rough approximation)
                estimated_cost_cents = max(1, total_tokens // 100)
                ai_cost_cents_total.labels(
                    provider=self.provider,
                    model=self.model
                ).inc(estimated_cost_cents)
                
                print(f"💰 Estimated cost: {estimated_cost_cents} cents")
                
                # Return raw content for robust parsing
                return content
                
            except CircuitBreakerError:
                print(f"🔴 Circuit breaker is open for AI service")
                # Circuit breaker is open - return fallback immediately
                return '{"ai_status": "circuit_open", "ok": false, "label": "OTHER", "confidence": 0.0, "ops_note": "AI service temporarily unavailable - manual review required", "client_note": "Processing your request - updates coming soon", "reasoning": "AI service circuit breaker open"}'
            except httpx.TimeoutException as e:
                print(f"⏰ AI request timeout: {e}")
                # Return controlled fallback for timeout
                return '{"ai_status": "timeout", "ok": false, "label": "OTHER", "confidence": 0.0, "ops_note": "AI analysis timed out - manual review required", "client_note": "Processing your request - updates coming soon", "reasoning": "AI service timeout"}'
            except (httpx.HTTPStatusError, json.JSONDecodeError) as e:
                print(f"🔴 AI request error: {type(e).__name__}: {e}")
                # Return fallback for HTTP errors and JSON decode errors
                return f'{{"ai_status": "error", "ok": false, "label": "OTHER", "confidence": 0.0, "ops_note": "AI analysis failed: {type(e).__name__} - manual review required", "client_note": "Processing your request - updates coming soon", "reasoning": "AI service error: {str(e)}"}}'
            except Exception as e:
                print(f"❌ Unexpected AI error: {type(e).__name__}: {e}")
                # Handle other errors with fallback
                if "timeout" in str(e).lower():
                    return '{"ai_status": "timeout", "ok": false, "label": "OTHER", "confidence": 0.0, "ops_note": "AI analysis timed out - manual review required", "client_note": "Processing your request - updates coming soon", "reasoning": "AI service timeout"}'
                # For unexpected errors, still raise to maintain error visibility
                raise


    def _build_exception_prompt(
        self,
        context: Dict[str, Any],
        template: Optional[str] = None
    ) -> str:
        """
        Build prompt for exception classification.
        
        Constructs AI prompts for exception analysis using either custom
        templates or the default prompt loader with comprehensive fallback
        to inline prompts for reliability.
        
        Args:
            context (Dict[str, Any]): Exception context data
            template (Optional[str]): Optional custom template override
            
        Returns:
            str: Formatted prompt string for AI analysis
        """
        if template:
            return template.format(**context)
        
        try:
            # Use prompt loader with Jinja2 templating
            return self.prompt_loader.get_exception_classification_prompt(**context)
            
        except (FileNotFoundError, KeyError):
            # Fallback to inline prompt if external file fails
            return f"""
Analyze this logistics exception and provide a JSON response with the following structure:
{{
    "label": "PICK_DELAY|PACK_DELAY|CARRIER_ISSUE|STOCK_MISMATCH|ADDRESS_ERROR|SYSTEM_ERROR|OTHER",
    "confidence": 0.0-1.0,
    "ops_note": "Technical note for operations team (max 200 words)",
    "client_note": "Customer-friendly explanation (max 100 words)",
    "reasoning": "Brief explanation of classification logic"
}}

Exception Context:
- Reason Code: {context.get('reason_code', 'UNKNOWN')}
- Order ID: {context.get('order_id_suffix', 'XXX')}
- Tenant: {context.get('tenant', 'unknown')}
- Duration: {context.get('duration_minutes', 0)} minutes
- Expected: {context.get('sla_minutes', 0)} minutes
- Delay: {context.get('delay_minutes', 0)} minutes

Provide actionable insights while maintaining customer confidence.
"""


    def _build_lint_prompt(
        self,
        policy_content: str,
        policy_type: str
    ) -> str:
        """
        Build prompt for policy linting.
        
        Constructs AI prompts for policy analysis and validation using
        the prompt loader with comprehensive fallback to inline prompts
        for operational reliability.
        
        Args:
            policy_content (str): Policy configuration content to analyze
            policy_type (str): Type of policy for context-specific analysis
            
        Returns:
            str: Formatted prompt string for AI policy linting
        """
        try:
            # Use prompt loader with Jinja2 templating
            return self.prompt_loader.get_policy_linting_prompt(
                policy_type=policy_type,
                policy_content=policy_content
            )
            
        except (FileNotFoundError, KeyError):
            # Fallback to inline prompt if external file fails
            return f"""
Act as a senior QA engineer reviewing this {policy_type} policy configuration.
Analyze for missing edge cases, potential issues, and suggest improvements.

Return JSON with this structure:
{{
    "suggestions": [
        {{
            "type": "missing_edge_case|validation_issue|performance_concern|best_practice",
            "severity": "low|medium|high|critical",
            "message": "Description of the issue",
            "suggested_fix": "Specific recommendation",
            "line_number": null
        }}
    ],
    "test_cases": [
        {{
            "name": "descriptive_test_name",
            "given": "Initial conditions",
            "when": "Action or event",
            "then": "Expected outcome",
            "test_data": {{}}
        }}
    ],
    "confidence": 0.0-1.0
}}

Policy Configuration:
```
{policy_content}
```

Focus on real-world logistics scenarios, edge cases, and operational reliability.
"""

    def _parse_classification_response(self, response) -> Dict[str, Any]:
        """Parse classification response from AI service."""
        import json
        
        try:
            # If it's already a dict, use it directly
            if isinstance(response, dict):
                parsed = response
            else:
                # If it's a string, try to parse as JSON
                parsed = json.loads(response)
            
            # Validate required fields
            if "label" not in parsed:
                raise ValueError("Missing required field: label")
            
            return parsed
            
        except (json.JSONDecodeError, TypeError):
            # Return a default response if parsing fails
            return {
                "label": "UNKNOWN",
                "confidence": 0.0,
                "reasoning": "Failed to parse AI response"
            }


# ==== GLOBAL CLIENT INSTANCE ==== #


# Global instance
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """
    Get global AI client instance.
    
    Provides singleton access to the AI client for consistent
    configuration and resource management across the application.
    
    Returns:
        AIClient: Global AI client instance
    """
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
