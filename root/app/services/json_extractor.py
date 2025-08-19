# ==== JSON EXTRACTOR SERVICE ==== #

"""
Robust JSON extraction from LLM responses for Octup E²A.
Adapted from hireex project with logistics-specific enhancements.

This module provides comprehensive JSON extraction capabilities with
multiple fallback strategies, error repair, and domain-specific
extraction for exception classification and policy linting.
"""

import json
import re
from typing import Optional, Dict, Any
import asyncio
from pydantic import BaseModel, Field, field_validator

# Try importing json5, but don't make it a hard requirement if unavailable
try:
    import json5
    JSON5_AVAILABLE = True
except ImportError:
    json5 = None
    JSON5_AVAILABLE = False

from app.observability.logging import ContextualLogger


logger = ContextualLogger(__name__)


# ==== DATA MODELS ==== #


class JsonBlock(BaseModel):
    """
    Model for validating and representing JSON blocks.
    
    Provides validation for text content containing potential JSON
    data with comprehensive error checking and type validation.
    """
    text: str = Field(..., description="Text content containing potential JSON")
    
    @field_validator('text', mode='before')
    @classmethod
    def check_text_is_str(cls, v):
        """
        Validate that text input is a string.
        
        Ensures input validation for robust JSON extraction
        and prevents type-related errors during processing.
        
        Args:
            v: Input value to validate
            
        Returns:
            str: Validated string value
            
        Raises:
            ValueError: If input is not a string
        """
        if not isinstance(v, str):
            raise ValueError("Text must be a string")
        return v


class JsonExtractResult(BaseModel):
    """
    Model for JSON extraction result.
    
    Provides structured representation of extraction outcomes
    with success status, extracted data, and error information.
    """
    data: Optional[Dict[str, Any]] = Field(None, description="Extracted JSON data")
    success: bool = Field(False, description="Whether extraction was successful")
    error: Optional[str] = Field(None, description="Error message if extraction failed")


# ==== CORE EXTRACTION FUNCTIONS ==== #


async def _find_json_block(text: str) -> Optional[str]:
    """
    Asynchronously find JSON block in text, preferring blocks in markdown format.
    
    Implements intelligent JSON block detection with markdown code block
    support and fallback to brace-level analysis for robust extraction.
    
    Args:
        text (str): Source text to search for JSON block
        
    Returns:
        Optional[str]: Found JSON block or None if not found
    """
    # Pattern for markdown code blocks (json, javascript, or none)
    code_block_match = re.search(r'```(?:json|javascript)?\s*(\{[\s\S]*?\})\s*```', text, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1).strip()

    # If no code block, find the largest top-level JSON object
    # This is more robust than just finding the first and last brace.
    brace_level = 0
    max_len = 0
    best_match = None
    start_index = -1

    for i, char in enumerate(text):
        if char == '{':
            if brace_level == 0:
                start_index = i
            brace_level += 1
        elif char == '}':
            if brace_level > 0:
                brace_level -= 1
                if brace_level == 0 and start_index != -1:
                    length = i - start_index + 1
                    if length > max_len:
                        max_len = length
                        best_match = text[start_index:i+1]
    
    return best_match


async def _repair_json_string(s: str) -> str:
    """
    Asynchronously repair common errors in JSON strings from LLMs.
    
    Implements comprehensive JSON repair strategies including trailing
    comma removal, unquoted key fixing, and formatting normalization
    for reliable parsing across different LLM response formats.
    
    Args:
        s (str): JSON string to repair
        
    Returns:
        str: Repaired JSON string ready for parsing
    """
    # Remove trailing commas
    s = re.sub(r',\s*([\}\]])', r'\1', s)
    
    # Fix unquoted keys - simplified pattern
    s = re.sub(r'([{,]\s*)([a-zA-Z_]\w*)(\s*:)', r'\1"\2"\3', s)
    
    # Replace single quotes with double quotes (basic)
    # A bit risky, but often necessary. Let's make it safer.
    s = re.sub(r"':\s*'([^']*)'", r'": "\1"', s) # For values
    s = re.sub(r"'([\w_]+)':", r'"\1":', s) # For keys

    # Handle python constants
    s = s.replace('True', 'true').replace('False', 'false').replace('None', 'null')
    
    # Clean up whitespace in keys - handle keys with leading newlines/spaces
    # This pattern looks for quoted keys with whitespace and normalizes them
    s = re.sub(r'([{,])\s*"[\s\n]*([\w_]+)"', r'\1 "\2"', s)
    
    # Remove any text before the first { and after the last }
    first_brace = s.find('{')
    last_brace = s.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        s = s[first_brace:last_brace+1]
    
    # Fix common LLM mistakes
    # Remove markdown code block markers if they somehow got through
    s = re.sub(r'```(?:json|javascript)?\s*', '', s)
    s = re.sub(r'\s*```', '', s)
    
    # Fix decimal numbers that might have been formatted incorrectly
    s = re.sub(r':\s*(\d+)\.(\d+)', r': \1.\2', s)
    
    # Ensure proper spacing around colons and commas
    s = re.sub(r'\s*:\s*', ': ', s)
    s = re.sub(r'\s*,\s*', ', ', s)
    
    return s.strip()


# ==== FALLBACK EXTRACTION STRATEGIES ==== #


async def _extract_exception_classification_fallback(text: str) -> Optional[Dict[str, Any]]:
    """
    Fallback extraction using regex patterns for exception classification responses.
    
    Implements pattern-based extraction when JSON parsing fails,
    providing reliable fallback for critical exception classification
    with comprehensive field extraction and validation.
    
    Args:
        text (str): Text to extract exception classification from
        
    Returns:
        Optional[Dict[str, Any]]: Extracted dictionary or None if extraction fails
    """
    try:
        # Pattern for label
        label_patterns = [
            r'["\']?label["\']?\s*:\s*["\']?(PICK_DELAY|PACK_DELAY|CARRIER_ISSUE|STOCK_MISMATCH|ADDRESS_ERROR|SYSTEM_ERROR|OTHER)["\']?',
            r'(PICK_DELAY|PACK_DELAY|CARRIER_ISSUE|STOCK_MISMATCH|ADDRESS_ERROR|SYSTEM_ERROR|OTHER)',
        ]
        
        label = None
        for pattern in label_patterns:
            label_match = re.search(pattern, text, re.IGNORECASE)
            if label_match:
                label = label_match.group(1) if len(label_match.groups()) == 1 else label_match.group(2)
                break
        
        # Pattern for confidence
        confidence_pattern = r'["\']?confidence["\']?\s*:\s*([0-9]*\.?[0-9]+)'
        confidence_match = re.search(confidence_pattern, text, re.IGNORECASE)
        
        # Pattern for ops_note
        ops_note_patterns = [
            r'["\']?ops_note["\']?\s*:\s*["\']([^"\']*)["\']',
            r'ops_note[^:]*:\s*(.+?)(?:\n|,|\})',
        ]
        
        ops_note = None
        for pattern in ops_note_patterns:
            ops_note_match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if ops_note_match:
                ops_note = ops_note_match.group(1).strip().strip('"\'')
                if ops_note and len(ops_note) > 10:
                    break
        
        # Pattern for client_note
        client_note_patterns = [
            r'["\']?client_note["\']?\s*:\s*["\']([^"\']*)["\']',
            r'client_note[^:]*:\s*(.+?)(?:\n|,|\})',
        ]
        
        client_note = None
        for pattern in client_note_patterns:
            client_note_match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if client_note_match:
                client_note = client_note_match.group(1).strip().strip('"\'')
                if client_note and len(client_note) > 5:
                    break
        
        # Pattern for reasoning
        reasoning_patterns = [
            r'["\']?reasoning["\']?\s*:\s*["\']([^"\']*)["\']',
            r'reasoning[^:]*:\s*(.+?)(?:\n|,|\})',
        ]
        
        reasoning = None
        for pattern in reasoning_patterns:
            reasoning_match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if reasoning_match:
                reasoning = reasoning_match.group(1).strip().strip('"\'')
                if reasoning and len(reasoning) > 5:
                    break
        
        if label:
            confidence_val = float(confidence_match.group(1)) if confidence_match else 0.5
            
            result = {
                "label": label.upper(),
                "confidence": max(0.0, min(1.0, confidence_val)),  # Clamp to 0-1
                "ops_note": ops_note or f"AI analysis extracted label: {label}",
                "client_note": client_note or "We're processing your request and will update you soon.",
                "reasoning": reasoning or f"Classified as {label} based on available context"
            }
            
            logger.info(f"Successfully extracted exception classification using regex fallback: {result}")
            return result
    
    except (ValueError, AttributeError) as e:
        logger.debug(f"Exception classification regex fallback failed: {e}")
    
    return None


async def _extract_policy_linting_fallback(text: str) -> Optional[Dict[str, Any]]:
    """
    Fallback extraction using regex patterns for policy linting responses.
    
    Implements pattern-based extraction for policy linting when JSON
    parsing fails, providing structured fallback responses with
    confidence scoring and generic suggestions.
    
    Args:
        text (str): Text to extract policy linting information from
        
    Returns:
        Optional[Dict[str, Any]]: Extracted dictionary or None if extraction fails
    """
    try:
        # Pattern for confidence
        confidence_pattern = r'["\']?confidence["\']?\s*:\s*([0-9]*\.?[0-9]+)'
        confidence_match = re.search(confidence_pattern, text, re.IGNORECASE)
        
        # Look for suggestions or issues mentioned
        suggestion_keywords = ['missing', 'edge case', 'validation', 'performance', 'best practice', 'issue', 'problem']
        has_suggestions = any(keyword in text.lower() for keyword in suggestion_keywords)
        
        confidence_val = float(confidence_match.group(1)) if confidence_match else 0.5
        
        result = {
            "suggestions": [],
            "test_cases": [],
            "confidence": max(0.0, min(1.0, confidence_val))
        }
        
        # If we detect suggestions in the text, add a generic one
        if has_suggestions:
            result["suggestions"].append({
                "type": "best_practice",
                "severity": "medium",
                "message": "AI analysis detected potential improvements in policy configuration",
                "suggested_fix": "Review policy configuration based on AI recommendations in full response",
                "line_number": None
            })
        
        logger.info(f"Successfully extracted policy linting using regex fallback: {result}")
        return result
    
    except (ValueError, AttributeError) as e:
        logger.debug(f"Policy linting regex fallback failed: {e}")
    
    return None


# ==== DEFAULT RESPONSE GENERATION ==== #


async def _create_default_exception_response(text: str) -> Dict[str, Any]:
    """
    Create a default exception classification response when all parsing fails.
    
    Implements intelligent fallback classification based on keyword
    analysis to provide meaningful responses even when parsing fails
    completely.
    
    Args:
        text (str): Original text for context and keyword analysis
        
    Returns:
        Dict[str, Any]: Default exception classification response
    """
    # Try to determine exception type based on keywords
    delay_keywords = ['delay', 'late', 'slow', 'timeout', 'exceeded']
    carrier_keywords = ['carrier', 'shipping', 'transport', 'delivery']
    stock_keywords = ['stock', 'inventory', 'availability', 'out of stock']
    address_keywords = ['address', 'location', 'verification', 'invalid']
    system_keywords = ['system', 'error', 'failure', 'exception', 'technical']
    
    text_lower = text.lower()
    
    if any(keyword in text_lower for keyword in delay_keywords):
        if 'pick' in text_lower:
            label = "PICK_DELAY"
        elif 'pack' in text_lower:
            label = "PACK_DELAY"
        else:
            label = "OTHER"
    elif any(keyword in text_lower for keyword in carrier_keywords):
        label = "CARRIER_ISSUE"
    elif any(keyword in text_lower for keyword in stock_keywords):
        label = "STOCK_MISMATCH"
    elif any(keyword in text_lower for keyword in address_keywords):
        label = "ADDRESS_ERROR"
    elif any(keyword in text_lower for keyword in system_keywords):
        label = "SYSTEM_ERROR"
    else:
        label = "OTHER"
    
    return {
        "label": label,
        "confidence": 0.3,  # Low confidence due to parsing failure
        "ops_note": f"AI response parsing failed. Classified as {label} based on keyword analysis. Manual review recommended.",
        "client_note": "We're reviewing your order and will provide updates soon.",
        "reasoning": "Fallback classification due to AI response parsing failure"
    }


async def _create_default_policy_response(text: str) -> Dict[str, Any]:
    """
    Create a default policy linting response when all parsing fails.
    
    Provides structured fallback response for policy linting
    when all extraction strategies fail, ensuring consistent
    response format and actionable guidance.
    
    Args:
        text (str): Original text for context (unused in current implementation)
        
    Returns:
        Dict[str, Any]: Default policy linting response
    """
    return {
        "suggestions": [{
            "type": "validation_issue",
            "severity": "medium",
            "message": "AI analysis failed to parse - manual policy review recommended",
            "suggested_fix": "Review policy configuration manually for potential issues",
            "line_number": None
        }],
        "test_cases": [{
            "name": "manual_review_required",
            "given": "Policy configuration provided",
            "when": "AI analysis fails to parse",
            "then": "Manual review should be conducted",
            "test_data": {}
        }],
        "confidence": 0.2  # Very low confidence
    }


# ==== MAIN EXTRACTION FUNCTIONS ==== #


async def extract_exception_classification(raw_text: Optional[str]) -> JsonExtractResult:
    """
    Robustly extract exception classification JSON from raw LLM response.
    
    Implements multi-strategy extraction with comprehensive fallback
    mechanisms to ensure reliable exception classification even when
    LLM responses are malformed or contain parsing errors.
    
    Args:
        raw_text (Optional[str]): Raw LLM response text to extract from
        
    Returns:
        JsonExtractResult: Structured result with extraction outcome and data
    """
    result = JsonExtractResult()
    
    if not raw_text or not isinstance(raw_text, str):
        result.error = "Invalid input: text is empty or not a string"
        return result
    
    try:
        logger.debug(f"Extracting exception classification from: {raw_text[:200]}...")
        
        # Find the JSON block
        json_block = await _find_json_block(raw_text)
        if not json_block:
            logger.warning("No JSON block found, trying regex fallback")
            fallback_result = await _extract_exception_classification_fallback(raw_text)
            if fallback_result:
                result.data = fallback_result
                result.success = True
                return result
            
            logger.warning("Regex fallback failed, creating default response")
            result.data = await _create_default_exception_response(raw_text)
            result.success = True
            return result

        # Strategy 1: Try to parse directly
        try:
            result.data = json.loads(json_block)
            result.success = True
            logger.debug("Successfully parsed exception classification JSON directly")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"Initial json.loads failed: {e}. Trying repairs.")

        # Strategy 2: Repair the string and try again
        repaired_block = await _repair_json_string(json_block)
        
        try:
            result.data = json.loads(repaired_block)
            result.success = True
            logger.debug("Successfully parsed repaired exception classification JSON")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"json.loads on repaired string failed: {e}. Trying json5.")

        # Strategy 3: Use json5 for more lenient parsing
        if JSON5_AVAILABLE:
            try:
                result.data = json5.loads(repaired_block)
                result.success = True
                logger.debug("Successfully parsed exception classification with json5")
                return result
            except Exception as e:
                logger.debug(f"json5 parsing failed: {e}. Trying regex fallback.")
        
        # Strategy 4: Regex fallback
        fallback_result = await _extract_exception_classification_fallback(raw_text)
        if fallback_result:
            result.data = fallback_result
            result.success = True
            return result
        
        # Strategy 5: Default response as last resort
        logger.warning("All parsing strategies failed, creating default exception response")
        result.data = await _create_default_exception_response(raw_text)
        result.success = True
        return result
    
    except Exception as e:
        result.error = f"Unexpected error during exception classification extraction: {str(e)}"
        logger.error("Error in extract_exception_classification", error=str(e))
        
        # Even on exception, try to provide a default response
        try:
            result.data = await _create_default_exception_response(raw_text or "")
            result.success = True
            result.error = None
        except Exception:
            pass
        
        return result


async def extract_policy_linting(raw_text: Optional[str]) -> JsonExtractResult:
    """
    Robustly extract policy linting JSON from raw LLM response.
    
    Implements multi-strategy extraction with comprehensive fallback
    mechanisms to ensure reliable policy linting even when LLM
    responses are malformed or contain parsing errors.
    
    Args:
        raw_text (Optional[str]): Raw LLM response text to extract from
        
    Returns:
        JsonExtractResult: Structured result with extraction outcome and data
    """
    result = JsonExtractResult()
    
    if not raw_text or not isinstance(raw_text, str):
        result.error = "Invalid input: text is empty or not a string"
        return result
    
    try:
        logger.debug(f"Extracting policy linting from: {raw_text[:200]}...")
        
        # Find the JSON block
        json_block = await _find_json_block(raw_text)
        if not json_block:
            logger.warning("No JSON block found, trying regex fallback")
            fallback_result = await _extract_policy_linting_fallback(raw_text)
            if fallback_result:
                result.data = fallback_result
                result.success = True
                return result
            
            logger.warning("Regex fallback failed, creating default response")
            result.data = await _create_default_policy_response(raw_text)
            result.success = True
            return result

        # Strategy 1: Try to parse directly
        try:
            result.data = json.loads(json_block)
            result.success = True
            logger.debug("Successfully parsed policy linting JSON directly")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"Initial json.loads failed: {e}. Trying repairs.")

        # Strategy 2: Repair the string and try again
        repaired_block = await _repair_json_string(json_block)
        
        try:
            result.data = json.loads(repaired_block)
            result.success = True
            logger.debug("Successfully parsed repaired policy linting JSON")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"json.loads on repaired string failed: {e}. Trying json5.")

        # Strategy 3: Use json5 for more lenient parsing
        if JSON5_AVAILABLE:
            try:
                result.data = json5.loads(repaired_block)
                result.success = True
                logger.debug("Successfully parsed policy linting with json5")
                return result
            except Exception as e:
                logger.debug(f"json5 parsing failed: {e}. Trying regex fallback.")
        
        # Strategy 4: Regex fallback
        fallback_result = await _extract_policy_linting_fallback(raw_text)
        if fallback_result:
            result.data = fallback_result
            result.success = True
            return result
        
        # Strategy 5: Default response as last resort
        logger.warning("All parsing strategies failed, creating default policy response")
        result.data = await _create_default_policy_response(raw_text)
        result.success = True
        return result
    
    except Exception as e:
        result.error = f"Unexpected error during policy linting extraction: {str(e)}"
        logger.error("Error in extract_policy_linting", error=str(e))
        
        # Even on exception, try to provide a default response
        try:
            result.data = await _create_default_policy_response(raw_text or "")
            result.success = True
            result.error = None
        except Exception:
            pass
        
        return result


# ==== SYNCHRONOUS WRAPPERS ==== #


def extract_exception_classification_sync(raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Synchronous wrapper for exception classification extraction.
    
    Provides backwards compatibility for synchronous code
    by wrapping the async extraction function with asyncio.run.
    
    Args:
        raw_text (Optional[str]): Raw LLM response text to extract from
        
    Returns:
        Optional[Dict[str, Any]]: Extracted data or None if extraction fails
    """
    try:
        result = asyncio.run(extract_exception_classification(raw_text))
        return result.data if result.success else None
    except Exception as e:
        logger.error(f"Error in synchronous exception classification extraction: {e}")
        return None


def extract_policy_linting_sync(raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Synchronous wrapper for policy linting extraction.
    
    Provides backwards compatibility for synchronous code
    by wrapping the async extraction function with asyncio.run.
    
    Args:
        raw_text (Optional[str]): Raw LLM response text to extract from
        
    Returns:
        Optional[Dict[str, Any]]: Extracted data or None if extraction fails
    """
    try:
        result = asyncio.run(extract_policy_linting(raw_text))
        return result.data if result.success else None
    except Exception as e:
        logger.error(f"Error in synchronous policy linting extraction: {e}")
        return None
