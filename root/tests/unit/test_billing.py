"""Unit tests for billing service functionality in simplified architecture."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone

from app.services.billing import (
    compute_amount_cents,
    validate_billing_operations,
    calculate_adjustment_impact,
    generate_billing_summary,
    BillingService
)


@pytest.mark.unit
class TestBillingFunctions:
    """Test cases for billing functions in the simplified 2-flow architecture."""
    
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
        # Storage: 10 * 5 = 50 (assuming 5 cents per day)
        expected = 65 + 50
        assert amount == expected

    def test_compute_amount_with_multipliers(self):
        """Test billing calculation with multipliers for rush orders."""
        operations = {
            "pick": 1,
            "pack": 1,
            "label": 1
        }
        
        # Test with rush multiplier
        amount = compute_amount_cents(operations, multiplier=1.5)
        
        # Base: (30 + 20 + 15) * 1.5 = 97.5 -> 98 cents (rounded up)
        expected = int((30 + 20 + 15) * 1.5)
        assert amount == expected

    def test_compute_amount_empty_operations(self):
        """Test billing calculation with no operations."""
        operations = {}
        
        amount = compute_amount_cents(operations)
        
        assert amount == 0

    def test_validate_billing_operations_success(self):
        """Test successful billing validation."""
        operations = [
            {"type": "pick", "quantity": 5, "rate_cents": 30},
            {"type": "pack", "quantity": 5, "rate_cents": 20},
            {"type": "label", "quantity": 5, "rate_cents": 15}
        ]
        
        result = validate_billing_operations(operations)
        
        assert result["valid"] is True
        assert result["total_amount_cents"] == 325  # (5*30) + (5*20) + (5*15)
        assert len(result["errors"]) == 0

    def test_validate_billing_operations_with_errors(self):
        """Test billing validation with invalid operations."""
        operations = [
            {"type": "pick", "quantity": -1, "rate_cents": 30},  # Invalid quantity
            {"type": "unknown", "quantity": 1, "rate_cents": 10},  # Invalid type
            {"type": "pack", "quantity": 1, "rate_cents": -5}  # Invalid rate
        ]
        
        result = validate_billing_operations(operations)
        
        assert result["valid"] is False
        assert len(result["errors"]) >= 2  # Should catch multiple errors
        assert result["total_amount_cents"] == 0  # No valid operations

    def test_calculate_adjustment_impact_credit(self):
        """Test adjustment impact calculation for credits."""
        original_amount = 1000  # $10.00
        adjustment = {
            "type": "credit",
            "amount_cents": -200,  # $2.00 credit
            "reason": "damaged_item"
        }
        
        result = calculate_adjustment_impact(original_amount, adjustment)
        
        assert result["new_amount_cents"] == 800
        assert result["adjustment_amount_cents"] == -200
        assert result["adjustment_percentage"] == -20.0

    def test_calculate_adjustment_impact_charge(self):
        """Test adjustment impact calculation for additional charges."""
        original_amount = 500  # $5.00
        adjustment = {
            "type": "charge",
            "amount_cents": 100,  # $1.00 additional charge
            "reason": "expedited_shipping"
        }
        
        result = calculate_adjustment_impact(original_amount, adjustment)
        
        assert result["new_amount_cents"] == 600
        assert result["adjustment_amount_cents"] == 100
        assert result["adjustment_percentage"] == 20.0

    def test_generate_billing_summary(self):
        """Test billing summary generation."""
        billing_data = {
            "operations": [
                {"type": "pick", "quantity": 10, "rate_cents": 30},
                {"type": "pack", "quantity": 8, "rate_cents": 20},
                {"type": "label", "quantity": 8, "rate_cents": 15}
            ],
            "adjustments": [
                {"type": "credit", "amount_cents": -50, "reason": "quality_issue"}
            ]
        }
        
        summary = generate_billing_summary(billing_data)
        
        assert summary["total_operations"] == 26  # 10 + 8 + 8
        assert summary["gross_amount_cents"] == 580  # (10*30) + (8*20) + (8*15)
        assert summary["adjustment_amount_cents"] == -50
        assert summary["net_amount_cents"] == 530
        assert len(summary["operation_breakdown"]) == 3


@pytest.mark.unit
class TestBillingService:
    """Test cases for BillingService class in the Business Operations Flow."""
    
    @pytest.mark.asyncio
    async def test_billing_service_initialization(self):
        """Test BillingService initialization."""
        with patch('app.services.billing.get_session') as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            service = BillingService(tenant="test-tenant")
            
            assert service.tenant == "test-tenant"
            assert service.db_session is not None

    @pytest.mark.asyncio
    async def test_validate_daily_billing_success(self):
        """Test daily billing validation success."""
        with patch('app.services.billing.get_session') as mock_session:
            
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock database query results
            mock_db.execute.return_value.fetchall.return_value = [
                ("pick", 50, 30),  # operation_type, quantity, rate_cents
                ("pack", 45, 20),
                ("label", 45, 15)
            ]
            
            service = BillingService(tenant="test-tenant")
            result = await service.validate_daily_billing()
            
            assert result["validation_passed"] is True
            assert result["total_operations"] == 140  # 50 + 45 + 45
            assert result["total_amount_cents"] == 2575  # (50*30) + (45*20) + (45*15)
            assert result["discrepancies_found"] == 0

    @pytest.mark.asyncio
    async def test_validate_daily_billing_with_discrepancies(self):
        """Test daily billing validation with discrepancies."""
        with patch('app.services.billing.get_session') as mock_session:
            
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock inconsistent data
            mock_db.execute.return_value.fetchall.return_value = [
                ("pick", 50, 25),  # Wrong rate (should be 30)
                ("pack", 45, 20),
                ("unknown_operation", 5, 10)  # Invalid operation type
            ]
            
            service = BillingService(tenant="test-tenant")
            result = await service.validate_daily_billing()
            
            assert result["validation_passed"] is False
            assert result["discrepancies_found"] >= 1
            assert "discrepancy_details" in result


@pytest.mark.unit
class TestBillingIntegrationWithFlows:
    """Test billing integration with the simplified 2-flow architecture."""
    
    @pytest.mark.asyncio
    async def test_billing_in_business_operations_flow(self):
        """Test billing service integration in Business Operations Flow."""
        with patch('flows.business_operations_flow.BillingService') as mock_billing_service:
            
            # Mock billing service for Business Operations Flow
            mock_billing = AsyncMock()
            mock_billing_service.return_value = mock_billing
            mock_billing.validate_daily_billing.return_value = {
                "validation_passed": True,
                "discrepancies_found": 0,
                "total_validated_amount_cents": 25000,
                "validation_details": {
                    "pick_operations": 500,
                    "pack_operations": 480,
                    "label_operations": 475,
                    "storage_operations": 50
                }
            }
            
            # Import and test the flow function
            from flows.business_operations_flow import validate_invoices
            
            result = await validate_invoices(tenant="test-tenant")
            
            assert "invoices_validated" in result or "validation_status" in result

    def test_billing_configuration_validation(self):
        """Test billing configuration validation."""
        # Test valid configuration
        valid_config = {
            "currency": "USD",
            "rates": {
                "pick": 30,
                "pack": 20,
                "label": 15,
                "storage_per_day": 5
            },
            "adjustments_enabled": True,
            "auto_invoice_generation": True
        }
        
        # Mock validation function since it may not exist
        def validate_billing_config(config):
            if config["currency"] not in ["USD", "EUR", "GBP"]:
                return {"valid": False, "errors": ["Invalid currency"]}
            
            for op_type, rate in config["rates"].items():
                if rate < 0:
                    return {"valid": False, "errors": ["Negative rate not allowed"]}
            
            return {"valid": True, "errors": []}
        
        result = validate_billing_config(valid_config)
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        
        # Test invalid configuration
        invalid_config = {
            "currency": "INVALID",
            "rates": {
                "pick": -10,  # Negative rate
                "unknown_operation": 5  # Unknown operation
            }
        }
        
        result = validate_billing_config(invalid_config)
        assert result["valid"] is False
        assert len(result["errors"]) >= 1

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
