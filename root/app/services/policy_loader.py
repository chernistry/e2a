# ==== POLICY LOADER SERVICE ==== #

"""
Policy loader for SLA and billing configurations.

This module provides comprehensive policy configuration management
including SLA thresholds, billing rates, reason codes, and validation
with intelligent caching and fallback mechanisms for all tenants.
"""

import functools
import os
from typing import Dict, Any

import yaml

from app.observability.tracing import get_tracer


tracer = get_tracer(__name__)


# ==== SLA CONFIGURATION LOADING ==== #


@functools.lru_cache(maxsize=64)
def get_sla_config(tenant: str) -> Dict[str, Any]:
    """
    Get SLA configuration for tenant.
    
    Loads tenant-specific SLA configuration with comprehensive
    caching, fallback defaults, and observability integration
    for optimal performance and reliability.
    
    Args:
        tenant (str): Tenant identifier for configuration lookup
        
    Returns:
        Dict[str, Any]: Dictionary with SLA thresholds and rules
    """
    with tracer.start_as_current_span("load_sla_config") as span:
        span.set_attribute("tenant", tenant)
        
        # For now, use default config for all tenants
        # In production, this would load tenant-specific configs
        config_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "business",
            "policies",
            "default_sla.yaml"
        )
        
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            
            span.set_attribute("config_loaded", True)
            return config
            
        except FileNotFoundError:
            # Fallback to hardcoded defaults
            span.set_attribute("config_loaded", False)
            span.set_attribute("fallback_used", True)
            
            return {
                "pick_minutes": 120,      # 2 hours to pick
                "pack_minutes": 180,      # 3 hours to pack
                "ship_minutes": 1440,     # 24 hours to ship
                "carrier_delivery_days": 5,  # 5 business days for delivery
                "weekend_multiplier": 1.5,   # 50% longer on weekends
                "holiday_multiplier": 2.0,   # 100% longer on holidays
                "high_volume_threshold": 100, # Orders per hour
                "high_volume_multiplier": 1.3 # 30% longer during high volume
            }


# ==== BILLING CONFIGURATION LOADING ==== #


@functools.lru_cache(maxsize=64)
def get_billing_config(tenant: str) -> Dict[str, Any]:
    """
    Get billing configuration for tenant.
    
    Loads tenant-specific billing configuration with comprehensive
    caching, fallback defaults, and observability integration
    for optimal performance and reliability.
    
    Args:
        tenant (str): Tenant identifier for configuration lookup
        
    Returns:
        Dict[str, Any]: Dictionary with billing rates and rules
    """
    with tracer.start_as_current_span("load_billing_config") as span:
        span.set_attribute("tenant", tenant)
        
        config_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "business", 
            "policies",
            "default_tariffs.yaml"
        )
        
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            
            span.set_attribute("config_loaded", True)
            return config
            
        except FileNotFoundError:
            # Fallback to hardcoded defaults
            span.set_attribute("config_loaded", False)
            span.set_attribute("fallback_used", True)
            
            return {
                "pick_fee_cents": 30,     # $0.30 per pick
                "pack_fee_cents": 20,     # $0.20 per pack
                "label_fee_cents": 15,    # $0.15 per label
                "storage_fee_cents_per_day": 5,  # $0.05 per day storage
                "min_order_fee_cents": 50,       # $0.50 minimum per order
                "rush_multiplier": 2.0,          # 2x for rush orders
                "oversized_multiplier": 1.5,     # 1.5x for oversized items
                "hazmat_multiplier": 3.0         # 3x for hazmat items
            }


# ==== REASON CODE CONFIGURATION ==== #


def get_reason_code_config() -> Dict[str, Dict[str, Any]]:
    """
    Get reason code configuration.
    
    Provides comprehensive reason code definitions including
    severity levels, escalation rules, and operational
    characteristics for exception management.
    
    Returns:
        Dict[str, Dict[str, Any]]: Dictionary mapping reason codes to their properties
    """
    return {
        "PICK_DELAY": {
            "severity": "MEDIUM",
            "auto_resolve": False,
            "escalation_hours": 4,
            "client_visible": True,
            "description": "Pick operation exceeded SLA threshold"
        },
        "PACK_DELAY": {
            "severity": "MEDIUM", 
            "auto_resolve": False,
            "escalation_hours": 2,
            "client_visible": True,
            "description": "Pack operation exceeded SLA threshold"
        },
        "CARRIER_ISSUE": {
            "severity": "HIGH",
            "auto_resolve": False,
            "escalation_hours": 1,
            "client_visible": True,
            "description": "Carrier pickup or delivery issue"
        },
        "MISSING_SCAN": {
            "severity": "MEDIUM",
            "auto_resolve": True,
            "escalation_hours": 8,
            "client_visible": False,
            "description": "Expected scan event not received"
        },
        "STOCK_MISMATCH": {
            "severity": "HIGH",
            "auto_resolve": False,
            "escalation_hours": 1,
            "client_visible": False,
            "description": "Inventory count mismatch detected"
        },
        "ADDRESS_ERROR": {
            "severity": "HIGH",
            "auto_resolve": False,
            "escalation_hours": 1,
            "client_visible": True,
            "description": "Shipping address validation failed"
        },
        "SYSTEM_ERROR": {
            "severity": "CRITICAL",
            "auto_resolve": False,
            "escalation_hours": 0.5,
            "client_visible": False,
            "description": "System or integration error"
        },
        "OTHER": {
            "severity": "MEDIUM",
            "auto_resolve": False,
            "escalation_hours": 4,
            "client_visible": True,
            "description": "Other operational issue"
        }
    }


# ==== CONFIGURATION VALIDATION ==== #


def validate_sla_config(config: Dict[str, Any]) -> bool:
    """
    Validate SLA configuration.
    
    Performs comprehensive validation of SLA configuration
    including required field checks and data type validation
    for operational reliability and data integrity.
    
    Args:
        config (Dict[str, Any]): SLA configuration dictionary to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    required_fields = [
        "pick_minutes",
        "pack_minutes", 
        "ship_minutes"
    ]
    
    for field in required_fields:
        if field not in config:
            return False
        
        if not isinstance(config[field], (int, float)) or config[field] <= 0:
            return False
    
    return True


def validate_billing_config(config: Dict[str, Any]) -> bool:
    """
    Validate billing configuration.
    
    Performs comprehensive validation of billing configuration
    including required field checks and data type validation
    for financial accuracy and operational reliability.
    
    Args:
        config (Dict[str, Any]): Billing configuration dictionary to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    required_fields = [
        "pick_fee_cents",
        "pack_fee_cents",
        "label_fee_cents"
    ]
    
    for field in required_fields:
        if field not in config:
            return False
        
        if not isinstance(config[field], (int, float)) or config[field] < 0:
            return False
    
    return True


# ==== CACHE MANAGEMENT ==== #


def clear_cache() -> None:
    """
    Clear policy configuration cache.
    
    Provides manual cache clearing capability for configuration
    updates, testing scenarios, and memory management.
    """
    get_sla_config.cache_clear()
    get_billing_config.cache_clear()
