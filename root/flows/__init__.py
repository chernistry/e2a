# ==== PREFECT FLOWS PACKAGE ==== #

"""
Modern Prefect flows for Octup E²A business operations.

This package contains realistic business process flows that work with
webhook-driven architecture:

- order_processing_flow: End-to-end order fulfillment monitoring
- exception_management_flow: Proactive exception handling and resolution
- billing_management_flow: Comprehensive invoice generation and validation
- business_operations_orchestrator: Master coordination of all processes

These flows replace the old event streaming approach with realistic
business processes that respond to webhook events from Shopify Mock.
"""

from .order_processing_flow import order_processing_pipeline
from .exception_management_flow import exception_management_pipeline
from .billing_management_flow import billing_management_pipeline
from .business_operations_orchestrator import (
    business_operations_orchestrator,
    hourly_operations,
    daily_operations
)

__all__ = [
    "order_processing_pipeline",
    "exception_management_pipeline", 
    "billing_management_pipeline",
    "business_operations_orchestrator",
    "hourly_operations",
    "daily_operations"
]
