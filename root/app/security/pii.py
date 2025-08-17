# ==== PII REDACTION UTILITIES ==== #

"""
PII (Personally Identifiable Information) redaction utilities for Octup E²A.

This module provides comprehensive PII detection and redaction capabilities
with pattern-based recognition, field-based filtering, and secure data
sanitization for AI processing and logging compliance.
"""

import re
from typing import Dict, Any, Union


# ==== PII DETECTION PATTERNS ==== #

# Regex patterns for detecting common PII formats
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
PHONE_PATTERN = re.compile(r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b')
SSN_PATTERN = re.compile(r'\b\d{3}-?\d{2}-?\d{4}\b')
CREDIT_CARD_PATTERN = re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b')


# ==== PII FIELD IDENTIFICATION ==== #

# Common field names that typically contain PII
PII_FIELDS = {
    'email', 'email_address', 'user_email', 'customer_email',
    'phone', 'phone_number', 'mobile', 'telephone',
    'name', 'first_name', 'last_name', 'full_name', 'customer_name',
    'address', 'street_address', 'home_address', 'billing_address', 'shipping_address',
    'ssn', 'social_security_number', 'tax_id',
    'credit_card', 'card_number', 'cc_number',
    'ip_address', 'ip_addr',
    'date_of_birth', 'dob', 'birth_date'
}


# ==== REDACTION FUNCTIONS ==== #

def redact_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redact PII from context dictionary.
    
    Implements comprehensive PII redaction using both field-name matching
    and pattern-based detection to ensure sensitive data is properly
    sanitized before AI processing or logging operations.
    
    Args:
        context (Dict[str, Any]): Context dictionary that may contain PII
        
    Returns:
        Dict[str, Any]: Context dictionary with PII redacted
    """
    if not isinstance(context, dict):
        return context
    
    redacted_context = {}
    
    for key, value in context.items():
        redacted_key = key.lower()
        
        # Check if field name suggests PII
        if any(pii_field in redacted_key for pii_field in PII_FIELDS):
            redacted_context[key] = _redact_value(value)
        else:
            # Recursively redact nested dictionaries
            if isinstance(value, dict):
                redacted_context[key] = redact_context(value)
            elif isinstance(value, list):
                redacted_context[key] = [
                    redact_context(item) if isinstance(item, dict) else _redact_if_pii(item)
                    for item in value
                ]
            else:
                # Check if value contains PII patterns
                redacted_context[key] = _redact_if_pii(value)
    
    return redacted_context


def _redact_value(value: Any) -> str:
    """Redact a value completely.
    
    Args:
        value: Value to redact
        
    Returns:
        Redacted placeholder
    """
    if isinstance(value, str):
        if len(value) <= 4:
            return "***"
        else:
            # Keep first and last character, redact middle
            return f"{value[0]}***{value[-1]}"
    else:
        return "[REDACTED]"


def _redact_if_pii(value: Any) -> Any:
    """Redact value if it contains PII patterns.
    
    Args:
        value: Value to check and potentially redact
        
    Returns:
        Original value or redacted version if PII detected
    """
    if not isinstance(value, str):
        return value
    
    # Check for email addresses
    if EMAIL_PATTERN.search(value):
        return EMAIL_PATTERN.sub('[EMAIL_REDACTED]', value)
    
    # Check for phone numbers
    if PHONE_PATTERN.search(value):
        return PHONE_PATTERN.sub('[PHONE_REDACTED]', value)
    
    # Check for SSN
    if SSN_PATTERN.search(value):
        return SSN_PATTERN.sub('[SSN_REDACTED]', value)
    
    # Check for credit card numbers
    if CREDIT_CARD_PATTERN.search(value):
        return CREDIT_CARD_PATTERN.sub('[CARD_REDACTED]', value)
    
    return value


def redact_order_id(order_id: str) -> str:
    """Redact order ID to show only last 4 characters.
    
    Args:
        order_id: Full order ID
        
    Returns:
        Redacted order ID showing only last 4 characters
    """
    if len(order_id) <= 4:
        return order_id
    
    return f"***{order_id[-4:]}"


def redact_tracking_number(tracking_number: str) -> str:
    """Redact tracking number to show only last 4 characters.
    
    Args:
        tracking_number: Full tracking number
        
    Returns:
        Redacted tracking number
    """
    if len(tracking_number) <= 4:
        return tracking_number
    
    return f"***{tracking_number[-4:]}"


def is_safe_for_logging(value: Any) -> bool:
    """Check if a value is safe to include in logs without redaction.
    
    Args:
        value: Value to check
        
    Returns:
        True if safe for logging, False if should be redacted
    """
    if not isinstance(value, str):
        return True
    
    # Check for PII patterns
    if EMAIL_PATTERN.search(value):
        return False
    
    if PHONE_PATTERN.search(value):
        return False
    
    if SSN_PATTERN.search(value):
        return False
    
    if CREDIT_CARD_PATTERN.search(value):
        return False
    
    return True


def sanitize_for_ai(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize data before sending to AI services.
    
    Args:
        data: Data dictionary to sanitize
        
    Returns:
        Sanitized data safe for AI processing
    """
    # Apply aggressive redaction for AI processing
    sanitized = redact_context(data)
    
    # Additional sanitization for AI
    for key, value in sanitized.items():
        if isinstance(value, str):
            # Redact any remaining potentially sensitive patterns
            if len(value) > 50:  # Long strings might contain sensitive info
                sanitized[key] = f"{value[:20]}...[TRUNCATED]"
    
    return sanitized


def create_audit_safe_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create an audit-safe version of a payload for logging.
    
    Args:
        payload: Original payload
        
    Returns:
        Audit-safe payload with PII redacted
    """
    audit_payload = redact_context(payload.copy())
    
    # Add metadata about redaction
    audit_payload["_redacted"] = True
    audit_payload["_redaction_timestamp"] = "2025-08-16T07:48:00Z"
    
    return audit_payload
