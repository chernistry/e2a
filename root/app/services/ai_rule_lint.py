# ==== AI RULE LINT SERVICE ==== #

"""
AI Rule Lint service for policy validation and improvement suggestions.

This module provides comprehensive policy linting capabilities using
AI-powered analysis with intelligent fallback mechanisms for SLA,
billing, and operational policy validation and improvement.
"""

import time
from typing import Dict, Any

from app.services.ai_client import get_ai_client
from app.schemas.ai import (
    AIRuleLintResponse, AIRuleLintSuggestion, AIRuleLintTest
)
from app.observability.tracing import get_tracer


tracer = get_tracer(__name__)


# ==== MAIN LINTING FUNCTION ==== #


async def lint_policy_rules(
    policy_content: str,
    policy_type: str = "sla",
    context: Dict[str, Any] | None = None
) -> AIRuleLintResponse:
    """
    Lint policy rules using AI for suggestions and test generation.
    
    Implements AI-powered policy analysis with comprehensive
    suggestion generation and test case creation for operational
    policy improvement and validation.
    
    Args:
        policy_content (str): YAML/JSON policy content to lint
        policy_type (str): Type of policy (sla, billing, etc.)
        context (Dict[str, Any] | None): Additional context for linting
        
    Returns:
        AIRuleLintResponse: AI linting response with suggestions and test cases
    """
    with tracer.start_as_current_span("lint_policy_rules") as span:
        span.set_attribute("policy_type", policy_type)
        span.set_attribute("content_length", len(policy_content))
        
        start_time = time.time()
        
        try:
            # Get AI client
            ai_client = get_ai_client()
            
            # Perform AI linting
            result = await ai_client.lint_policy(policy_content, policy_type)
            
            # Parse and validate the response
            suggestions = _parse_suggestions(result.get("suggestions", []))
            test_cases = _parse_test_cases(result.get("test_cases", []))
            confidence = result.get("confidence", 0.5)
            
            processing_time = int((time.time() - start_time) * 1000)
            
            span.set_attribute("suggestions_count", len(suggestions))
            span.set_attribute("test_cases_count", len(test_cases))
            span.set_attribute("confidence", confidence)
            span.set_attribute("processing_time_ms", processing_time)
            
            return AIRuleLintResponse(
                suggestions=suggestions,
                test_cases=test_cases,
                confidence=confidence,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            # Fallback to rule-based linting
            span.set_attribute("ai_failed", True)
            span.set_attribute("fallback_used", True)
            
            return await _fallback_lint(policy_content, policy_type, start_time)


# ==== AI RESPONSE PARSING ==== #


def _parse_suggestions(raw_suggestions: list) -> list[AIRuleLintSuggestion]:
    """
    Parse and validate AI suggestions.
    
    Processes raw AI suggestions with comprehensive validation
    and formatting to ensure data quality and consistency.
    
    Args:
        raw_suggestions (list): Raw suggestions from AI
        
    Returns:
        list[AIRuleLintSuggestion]: List of validated suggestion objects
    """
    suggestions = []
    
    for raw_suggestion in raw_suggestions[:10]:  # Limit to 10 suggestions
        try:
            suggestion = AIRuleLintSuggestion(
                type=raw_suggestion.get("type", "best_practice"),
                severity=raw_suggestion.get("severity", "medium"),
                message=raw_suggestion.get("message", "")[:500],  # Truncate long messages
                suggested_fix=raw_suggestion.get("suggested_fix", "")[:1000],
                line_number=raw_suggestion.get("line_number")
            )
            suggestions.append(suggestion)
        except Exception:
            # Skip invalid suggestions
            continue
    
    return suggestions


def _parse_test_cases(raw_test_cases: list) -> list[AIRuleLintTest]:
    """
    Parse and validate AI test cases.
    
    Processes raw AI test cases with comprehensive validation
    and formatting to ensure test case quality and consistency.
    
    Args:
        raw_test_cases (list): Raw test cases from AI
        
    Returns:
        list[AIRuleLintTest]: List of validated test case objects
    """
    test_cases = []
    
    for raw_test in raw_test_cases[:5]:  # Limit to 5 test cases
        try:
            test_case = AIRuleLintTest(
                name=raw_test.get("name", "")[:100],
                given=raw_test.get("given", "")[:200],
                when=raw_test.get("when", "")[:200],
                then=raw_test.get("then", "")[:200],
                test_data=raw_test.get("test_data", {})
            )
            test_cases.append(test_case)
        except Exception:
            # Skip invalid test cases
            continue
    
    return test_cases


# ==== FALLBACK LINTING ==== #


async def _fallback_lint(
    policy_content: str,
    policy_type: str,
    start_time: float
) -> AIRuleLintResponse:
    """
    Fallback rule-based linting when AI is unavailable.
    
    Implements comprehensive rule-based policy analysis
    when AI services are unavailable or fail, ensuring
    continuous policy validation capabilities.
    
    Args:
        policy_content (str): Policy content to lint
        policy_type (str): Type of policy for targeted analysis
        start_time (float): Processing start time for timing calculation
        
    Returns:
        AIRuleLintResponse: Fallback linting response with suggestions and tests
    """
    with tracer.start_as_current_span("fallback_lint") as span:
        span.set_attribute("policy_type", policy_type)
        
        suggestions = []
        test_cases = []
        
        # Basic rule-based checks
        if policy_type == "sla":
            suggestions.extend(_check_sla_policy(policy_content))
            test_cases.extend(_generate_sla_tests(policy_content))
        elif policy_type == "billing":
            suggestions.extend(_check_billing_policy(policy_content))
            test_cases.extend(_generate_billing_tests(policy_content))
        
        processing_time = int((time.time() - start_time) * 1000)
        
        span.set_attribute("suggestions_count", len(suggestions))
        span.set_attribute("test_cases_count", len(test_cases))
        
        return AIRuleLintResponse(
            suggestions=suggestions,
            test_cases=test_cases,
            confidence=0.6,  # Medium confidence for rule-based
            processing_time_ms=processing_time
        )


# ==== SLA POLICY VALIDATION ==== #


def _check_sla_policy(policy_content: str) -> list[AIRuleLintSuggestion]:
    """
    Check SLA policy for common issues.
    
    Performs comprehensive SLA policy validation including
    missing field detection, edge case identification, and
    best practice recommendations for operational reliability.
    
    Args:
        policy_content (str): SLA policy content to validate
        
    Returns:
        list[AIRuleLintSuggestion]: List of validation suggestions
    """
    suggestions = []
    
    # Check for missing common fields
    if "pick_minutes" not in policy_content:
        suggestions.append(AIRuleLintSuggestion(
            type="missing_field",
            severity="high",
            message="Missing 'pick_minutes' threshold",
            suggested_fix="Add pick_minutes: 120 for 2-hour pick SLA"
        ))
    
    if "pack_minutes" not in policy_content:
        suggestions.append(AIRuleLintSuggestion(
            type="missing_field",
            severity="high",
            message="Missing 'pack_minutes' threshold",
            suggested_fix="Add pack_minutes: 180 for 3-hour pack SLA"
        ))
    
    if "ship_minutes" not in policy_content:
        suggestions.append(AIRuleLintSuggestion(
            type="missing_field",
            severity="high",
            message="Missing 'ship_minutes' threshold",
            suggested_fix="Add ship_minutes: 1440 for 24-hour ship SLA"
        ))
    
    # Check for weekend/holiday considerations
    if "weekend_multiplier" not in policy_content:
        suggestions.append(AIRuleLintSuggestion(
            type="missing_edge_case",
            severity="medium",
            message="No weekend handling specified",
            suggested_fix="Add weekend_multiplier: 1.5 to account for reduced weekend staffing"
        ))
    
    if "holiday_multiplier" not in policy_content:
        suggestions.append(AIRuleLintSuggestion(
            type="missing_edge_case",
            severity="medium",
            message="No holiday handling specified",
            suggested_fix="Add holiday_multiplier: 2.0 for holiday delays"
        ))
    
    return suggestions


# ==== BILLING POLICY VALIDATION ==== #


def _check_billing_policy(policy_content: str) -> list[AIRuleLintSuggestion]:
    """
    Check billing policy for common issues.
    
    Performs comprehensive billing policy validation including
    missing fee structure detection, best practice identification,
    and operational cost optimization recommendations.
    
    Args:
        policy_content (str): Billing policy content to validate
        
    Returns:
        list[AIRuleLintSuggestion]: List of validation suggestions
    """
    suggestions = []
    
    # Check for missing fee structures
    if "pick_fee_cents" not in policy_content:
        suggestions.append(AIRuleLintSuggestion(
            type="missing_field",
            severity="high",
            message="Missing 'pick_fee_cents' rate",
            suggested_fix="Add pick_fee_cents: 30 for $0.30 per pick"
        ))
    
    if "pack_fee_cents" not in policy_content:
        suggestions.append(AIRuleLintSuggestion(
            type="missing_field",
            severity="high",
            message="Missing 'pack_fee_cents' rate",
            suggested_fix="Add pack_fee_cents: 20 for $0.20 per pack"
        ))
    
    # Check for minimum fees
    if "min_order_fee_cents" not in policy_content:
        suggestions.append(AIRuleLintSuggestion(
            type="best_practice",
            severity="medium",
            message="Consider adding minimum order fee",
            suggested_fix="Add min_order_fee_cents: 50 for $0.50 minimum"
        ))
    
    return suggestions


# ==== TEST CASE GENERATION ==== #


def _generate_sla_tests(policy_content: str) -> list[AIRuleLintTest]:
    """
    Generate test cases for SLA policy.
    
    Creates comprehensive test cases covering SLA breach detection,
    normal operation scenarios, and edge case validation for
    robust policy testing and validation.
    
    Args:
        policy_content (str): SLA policy content for test generation
        
    Returns:
        list[AIRuleLintTest]: List of generated test cases
    """
    test_cases = []
    
    # Basic pick delay test
    test_cases.append(AIRuleLintTest(
        name="pick_delay_detection",
        given="Order paid at 10:00 AM with 120-minute pick SLA",
        when="Pick completed at 1:00 PM (180 minutes later)",
        then="Should create PICK_DELAY exception",
        test_data={
            "order_paid": "2025-08-16T10:00:00Z",
            "pick_completed": "2025-08-16T13:00:00Z",
            "expected_exception": "PICK_DELAY"
        }
    ))
    
    # Pack delay test
    test_cases.append(AIRuleLintTest(
        name="pack_delay_detection",
        given="Pick completed at 12:00 PM with 180-minute pack SLA",
        when="Pack completed at 4:00 PM (240 minutes later)",
        then="Should create PACK_DELAY exception",
        test_data={
            "pick_completed": "2025-08-16T12:00:00Z",
            "pack_completed": "2025-08-16T16:00:00Z",
            "expected_exception": "PACK_DELAY"
        }
    ))
    
    # No breach test
    test_cases.append(AIRuleLintTest(
        name="no_breach_within_sla",
        given="Order paid at 10:00 AM with normal SLA thresholds",
        when="All operations complete within SLA windows",
        then="Should not create any exceptions",
        test_data={
            "order_paid": "2025-08-16T10:00:00Z",
            "pick_completed": "2025-08-16T11:30:00Z",
            "pack_completed": "2025-08-16T13:00:00Z",
            "expected_exception": None
        }
    ))
    
    return test_cases


def _generate_billing_tests(policy_content: str) -> list[AIRuleLintTest]:
    """
    Generate test cases for billing policy.
    
    Creates comprehensive test cases covering billing calculations,
    minimum fee application, and rate structure validation for
    accurate financial operations and customer billing.
    
    Args:
        policy_content (str): Billing policy content for test generation
        
    Returns:
        list[AIRuleLintTest]: List of generated test cases
    """
    test_cases = []
    
    # Basic billing calculation
    test_cases.append(AIRuleLintTest(
        name="basic_billing_calculation",
        given="Order with 1 pick, 1 pack, 1 label operation",
        when="Calculating total billing amount",
        then="Should sum all operation fees correctly",
        test_data={
            "operations": {"pick": 1, "pack": 1, "label": 1},
            "rates": {"pick_fee_cents": 30, "pack_fee_cents": 20, "label_fee_cents": 15},
            "expected_total_cents": 65
        }
    ))
    
    # Minimum fee test
    test_cases.append(AIRuleLintTest(
        name="minimum_fee_application",
        given="Small order below minimum fee threshold",
        when="Calculating billing with minimum fee rule",
        then="Should apply minimum fee instead of calculated amount",
        test_data={
            "operations": {"pick": 1},
            "calculated_cents": 30,
            "min_order_fee_cents": 50,
            "expected_total_cents": 50
        }
    ))
    
    return test_cases
