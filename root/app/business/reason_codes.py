# ==== BUSINESS REASON CODES AND EXCEPTION HANDLING ==== #

"""
Reason codes and business rules for exception handling in Octup E²A.

This module defines standardized reason codes, severity levels, and business rules
for SLA breaches and operational exceptions with comprehensive configuration
for escalation, notification, and resolution workflows.
"""

from enum import Enum
from typing import Dict, Any


# ==== ENUMERATION DEFINITIONS ==== #


class ReasonCode(str, Enum):
    """
    Standard reason codes for SLA breaches and operational exceptions.
    
    These codes provide consistent categorization of issues across the platform
    and enable automated routing, escalation, and resolution workflows.
    """
    
    PICK_DELAY = "PICK_DELAY"
    PACK_DELAY = "PACK_DELAY"
    CARRIER_ISSUE = "CARRIER_ISSUE"
    MISSING_SCAN = "MISSING_SCAN"
    STOCK_MISMATCH = "STOCK_MISMATCH"
    ADDRESS_ERROR = "ADDRESS_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    OTHER = "OTHER"


class ExceptionSeverity(str, Enum):
    """
    Exception severity levels for prioritization and escalation.
    
    Severity levels determine response time requirements, escalation paths,
    and resource allocation for exception resolution.
    """
    
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExceptionStatus(str, Enum):
    """
    Exception status lifecycle for tracking resolution progress.
    
    Status progression: OPEN → ACKNOWLEDGED → IN_PROGRESS → RESOLVED → CLOSED
    """
    
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


# ==== BUSINESS RULES CONFIGURATION ==== #


REASON_CODE_CONFIG: Dict[str, Dict[str, Any]] = {
    ReasonCode.PICK_DELAY: {
        "severity": ExceptionSeverity.MEDIUM,
        "auto_resolve": False,
        "escalation_hours": 4,
        "client_visible": True,
        "requires_approval": False,
        "sla_impact": "high",
        "description": "Pick operation exceeded SLA threshold",
        "typical_causes": [
            "High order volume",
            "Inventory location issues", 
            "Staff shortage",
            "System downtime"
        ],
        "resolution_actions": [
            "Check picker availability",
            "Verify inventory locations",
            "Review order complexity",
            "Escalate to warehouse manager"
        ]
    },
    
    ReasonCode.PACK_DELAY: {
        "severity": ExceptionSeverity.MEDIUM,
        "auto_resolve": False,
        "escalation_hours": 2,
        "client_visible": True,
        "requires_approval": False,
        "sla_impact": "high",
        "description": "Pack operation exceeded SLA threshold",
        "typical_causes": [
            "Packing station backlog",
            "Special packaging requirements",
            "Missing packaging materials",
            "Quality control holds"
        ],
        "resolution_actions": [
            "Check packing station capacity",
            "Verify packaging material availability",
            "Review special requirements",
            "Expedite through quality control"
        ]
    },
    
    ReasonCode.CARRIER_ISSUE: {
        "severity": ExceptionSeverity.HIGH,
        "auto_resolve": False,
        "escalation_hours": 1,
        "client_visible": True,
        "requires_approval": False,
        "sla_impact": "critical",
        "description": "Carrier pickup or delivery issue",
        "typical_causes": [
            "Carrier pickup delay",
            "Weather conditions",
            "Carrier capacity issues",
            "Address validation failures"
        ],
        "resolution_actions": [
            "Contact carrier representative",
            "Arrange alternative pickup",
            "Update customer with new timeline",
            "Consider carrier escalation"
        ]
    },
    
    ReasonCode.MISSING_SCAN: {
        "severity": ExceptionSeverity.MEDIUM,
        "auto_resolve": True,
        "escalation_hours": 8,
        "client_visible": False,
        "requires_approval": False,
        "sla_impact": "medium",
        "description": "Expected scan event not received",
        "typical_causes": [
            "Scanner connectivity issues",
            "Process compliance gaps",
            "System integration delays",
            "Manual process bypasses"
        ],
        "resolution_actions": [
            "Check scanner connectivity",
            "Verify process compliance",
            "Review system integration logs",
            "Provide additional training"
        ]
    },
    
    ReasonCode.STOCK_MISMATCH: {
        "severity": ExceptionSeverity.HIGH,
        "auto_resolve": False,
        "escalation_hours": 1,
        "client_visible": False,
        "requires_approval": True,
        "sla_impact": "critical",
        "description": "Inventory count mismatch detected",
        "typical_causes": [
            "Inventory counting errors",
            "Damaged or lost items",
            "System synchronization issues",
            "Theft or shrinkage"
        ],
        "resolution_actions": [
            "Perform cycle count",
            "Investigate discrepancy root cause",
            "Update inventory records",
            "Implement corrective measures"
        ]
    },
    
    ReasonCode.ADDRESS_ERROR: {
        "severity": ExceptionSeverity.HIGH,
        "auto_resolve": False,
        "escalation_hours": 1,
        "client_visible": True,
        "requires_approval": False,
        "sla_impact": "high",
        "description": "Shipping address validation failed",
        "typical_causes": [
            "Invalid postal codes",
            "Incomplete address information",
            "Address format issues",
            "Restricted delivery areas"
        ],
        "resolution_actions": [
            "Contact customer for verification",
            "Use address validation service",
            "Check carrier delivery restrictions",
            "Provide alternative delivery options"
        ]
    },
    
    ReasonCode.SYSTEM_ERROR: {
        "severity": ExceptionSeverity.CRITICAL,
        "auto_resolve": False,
        "escalation_hours": 0.5,
        "client_visible": False,
        "requires_approval": False,
        "sla_impact": "critical",
        "description": "System or integration error",
        "typical_causes": [
            "API connectivity issues",
            "Database errors",
            "Integration failures",
            "Software bugs"
        ],
        "resolution_actions": [
            "Check system logs",
            "Verify API connectivity",
            "Escalate to technical team",
            "Implement temporary workaround"
        ]
    },
    
    ReasonCode.OTHER: {
        "severity": ExceptionSeverity.MEDIUM,
        "auto_resolve": False,
        "escalation_hours": 4,
        "client_visible": True,
        "requires_approval": False,
        "sla_impact": "medium",
        "description": "Other operational issue",
        "typical_causes": [
            "Unforeseen circumstances",
            "Process exceptions",
            "Special handling requirements",
            "External dependencies"
        ],
        "resolution_actions": [
            "Investigate specific circumstances",
            "Document root cause",
            "Implement corrective action",
            "Update processes if needed"
        ]
    }
}


# ==== BUSINESS RULE FUNCTIONS ==== #


def get_reason_config(reason_code: ReasonCode) -> Dict[str, Any]:
    """
    Get configuration for a specific reason code.
    
    Retrieves the complete business rule configuration including severity,
    escalation rules, visibility settings, and resolution guidance.
    
    Args:
        reason_code (ReasonCode): Reason code to get configuration for
        
    Returns:
        Dict[str, Any]: Configuration dictionary for the reason code
    """
    return REASON_CODE_CONFIG.get(
        reason_code, 
        REASON_CODE_CONFIG[ReasonCode.OTHER]
    )


def get_escalation_priority(reason_code: ReasonCode) -> int:
    """
    Get escalation priority for a reason code.
    
    Returns priority value where lower numbers indicate higher priority
    for escalation and resource allocation decisions.
    
    Args:
        reason_code (ReasonCode): Reason code to evaluate
        
    Returns:
        int: Priority value (1-10, where 1 is highest priority)
    """
    priority_map = {
        ReasonCode.SYSTEM_ERROR: 1,
        ReasonCode.STOCK_MISMATCH: 2,
        ReasonCode.ADDRESS_ERROR: 3,
        ReasonCode.CARRIER_ISSUE: 4,
        ReasonCode.PACK_DELAY: 5,
        ReasonCode.PICK_DELAY: 6,
        ReasonCode.MISSING_SCAN: 7,
        ReasonCode.OTHER: 8
    }
    
    return priority_map.get(reason_code, 9)


def should_notify_customer(reason_code: ReasonCode) -> bool:
    """
    Check if customer should be notified for this reason code.
    
    Determines whether the exception should trigger customer-facing
    notifications based on business visibility rules.
    
    Args:
        reason_code (ReasonCode): Reason code to check
        
    Returns:
        bool: True if customer should be notified, False otherwise
    """
    config = get_reason_config(reason_code)
    return config.get("client_visible", False)


def requires_management_approval(reason_code: ReasonCode) -> bool:
    """
    Check if reason code requires management approval.
    
    Determines whether resolution actions require management approval
    based on business impact and operational significance.
    
    Args:
        reason_code (ReasonCode): Reason code to check
        
    Returns:
        bool: True if management approval is required, False otherwise
    """
    config = get_reason_config(reason_code)
    return config.get("requires_approval", False)


def get_auto_resolution_eligible(reason_code: ReasonCode) -> bool:
    """
    Check if exception can be auto-resolved.
    
    Determines whether the exception type supports automatic resolution
    without human intervention based on business rules.
    
    Args:
        reason_code (ReasonCode): Reason code to check
        
    Returns:
        bool: True if auto-resolution is enabled, False otherwise
    """
    config = get_reason_config(reason_code)
    return config.get("auto_resolve", False)
