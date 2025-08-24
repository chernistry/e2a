# ==== PREFECT FLOWS PACKAGE ==== #

"""
Simplified Prefect flows for Octup E²A business operations.

This package contains consolidated business process flows:

- event_processor_flow: Real-time event processing with AI analysis
- business_operations_flow: Daily business operations and billing

These flows replace the fragmented approach with streamlined,
Prefect-native patterns for better performance and maintainability.
"""

from .event_processor_flow import event_processor_flow
from .business_operations_flow import business_operations_flow

__all__ = [
    "event_processor_flow",
    "business_operations_flow"
]
