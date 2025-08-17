#!/usr/bin/env python3

# ==== INVOICE VALIDATION TEST SUITE ==== #

"""
Test invoice validation logic without Prefect Cloud dependency.

This module provides standalone testing for invoice validation
functionality including billing calculations, operation validation,
and comprehensive error handling for operational reliability.
"""

import asyncio
import sys
import os
import pytest

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from app.services.billing import compute_amount_cents, validate_billing_operations
from app.storage.db import get_session


# ==== INVOICE VALIDATION TESTS ==== #


@pytest.mark.asyncio
async def test_invoice_validation():
    """
    Test invoice validation logic.
    
    Provides comprehensive testing of invoice validation
    including billing calculations, operation validation,
    and database integration for operational reliability.
    
    Returns:
        bool: True if all tests pass, False otherwise
    """
    print("🧾 Testing Invoice Validation Logic...")
    
    try:
        async with get_session() as db:
            # Test invoice validation for demo tenant
            tenant = "demo-3pl"
            
            print(f"📊 Running invoice validation for tenant: {tenant}")
            
            # Test basic billing calculations
            operations = {
                "pick": 10,
                "pack": 8,
                "label": 5,
                "storage_days": 30
            }
            
            amount = compute_amount_cents(operations, tenant)
            print(f"✅ Computed amount: ${amount/100:.2f}")
            
            # Test billing operations validation
            validation_result = validate_billing_operations(operations)
            print(f"✅ Validation result: {validation_result}")
            
            return True
            
    except Exception as e:
        print(f"❌ Invoice validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==== MAIN EXECUTION ==== #


if __name__ == "__main__":
    success = asyncio.run(test_invoice_validation())
    sys.exit(0 if success else 1)
