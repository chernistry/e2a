"""Unit tests for billing service functionality."""

import pytest
from unittest.mock import patch, MagicMock

from app.services.billing import (
    compute_amount_cents,
    validate_billing_operations,
    calculate_adjustment_impact,
    generate_billing_summary
)


@pytest.mark.unit
class TestBillingFunctions:
    """Test cases for billing functions."""
    
    def test_compute_amount_basic_operations(self):
        """Test basic operation billing calculation."""
        operations = {
            "pick": 2,
            "pack": 1,
            "label": 1
        }
        
        amount = compute_amount_cents(operations)
        
        # Default rates: pick=30, pack=20, label=15
        expected = (2 * 30) + (1 * 20) + (1 * 15)  # 95 cents
        assert amount == expected

    def test_compute_amount_with_storage(self):
        """Test billing calculation with storage fees."""
        operations = {
            "pick": 1,
            "pack": 1,
            "label": 1,
            "storage_days": 10
        }
        
        amount = compute_amount_cents(operations)
        
        # Base operations: 30 + 20 + 15 = 65
        # Storage: 10 * 5 = 50
        expected = 65 + 50
        assert amount == expected

    def test_compute_amount_with_multipliers(self):
        """Test billing calculation with multipliers."""
        operations = {
            "pick": 1,
            "pack": 1,
            "label": 1,
            "rush": True
        }
        
        amount = compute_amount_cents(operations)
        
        # Base operations: 30 + 20 + 15 = 65
        # Rush multiplier: 2.0
        expected = int(65 * 2.0)
        assert amount == expected

    def test_compute_amount_minimum_fee(self):
        """Test minimum fee application."""
        operations = {
            "pick": 1  # Only 30 cents, below minimum
        }
        
        amount = compute_amount_cents(operations)
        
        # Should apply minimum fee of 50 cents
        assert amount == 50

    def test_validate_billing_operations_valid(self):
        """Test validation of valid billing operations."""
        operations = {
            "pick": 2,
            "pack": 1,
            "label": 1
        }
        
        errors = validate_billing_operations(operations)
        
        assert errors == {}

    def test_validate_billing_operations_missing_operations(self):
        """Test validation with missing core operations."""
        operations = {
            "storage_days": 5
        }
        
        errors = validate_billing_operations(operations)
        
        assert "operations" in errors

    def test_validate_billing_operations_invalid_counts(self):
        """Test validation with invalid operation counts."""
        operations = {
            "pick": -1,
            "pack": 1.5  # Should be integer
        }
        
        errors = validate_billing_operations(operations)
        
        assert "pick" in errors

    def test_calculate_adjustment_impact(self):
        """Test adjustment impact calculation."""
        original_ops = {"pick": 1, "pack": 1, "label": 1}
        adjusted_ops = {"pick": 2, "pack": 1, "label": 1}
        
        impact = calculate_adjustment_impact(original_ops, adjusted_ops)
        
        assert impact["original_amount_cents"] == 65  # 30+20+15
        assert impact["adjusted_amount_cents"] == 95  # 60+20+15
        assert impact["delta_cents"] == 30
        assert "changed_operations" in impact

    def test_generate_billing_summary(self):
        """Test billing summary generation."""
        operations = {
            "pick": 2,
            "pack": 1,
            "label": 1
        }
        
        summary = generate_billing_summary(operations)
        
        assert "line_items" in summary
        assert "total_cents" in summary
        assert len(summary["line_items"]) == 3  # pick, pack, label
        assert summary["total_cents"] == 95

    @patch('app.services.billing.get_billing_config')
    def test_compute_amount_custom_config(self, mock_config):
        """Test billing calculation with custom configuration."""
        mock_config.return_value = {
            "pick_fee_cents": 50,
            "pack_fee_cents": 30,
            "label_fee_cents": 20,
            "min_order_fee_cents": 100
        }
        
        operations = {"pick": 1, "pack": 1, "label": 1}
        
        amount = compute_amount_cents(operations, "custom-tenant")
        
        # Custom rates: 50 + 30 + 20 = 100
        assert amount == 100
        mock_config.assert_called_once_with("custom-tenant")
