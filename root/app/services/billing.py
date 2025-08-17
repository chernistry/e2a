# ==== BILLING SERVICE ==== #

"""
Billing service for invoice calculations and validations.

This module provides comprehensive billing operations including
invoice validation, amount calculations, adjustment processing,
and detailed billing summaries with tenant-specific configurations.
"""

from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.policy_loader import get_billing_config
from app.observability.tracing import get_tracer
from app.storage.models import Invoice, InvoiceAdjustment, OrderEvent


tracer = get_tracer(__name__)


# ==== BILLING SERVICE CLASS ==== #


class BillingService:
    """
    Service for billing operations and invoice validation.
    
    Provides comprehensive billing functionality including invoice
    validation, adjustment creation, and operational cost calculations
    with tenant-specific configuration support.
    """
    
    def __init__(self):
        """
        Initialize billing service.
        
        Sets up billing service with configuration loading
        and operational readiness for invoice processing.
        """
        pass
    
    # ==== INVOICE VALIDATION ==== #
    
    async def validate_invoice(
        self, 
        db: AsyncSession, 
        invoice: Invoice
    ) -> Optional[InvoiceAdjustment]:
        """
        Validate an invoice and create adjustment if needed.
        
        Performs comprehensive invoice validation by recalculating
        expected amounts based on actual order events and creating
        adjustments when discrepancies are detected.
        
        Args:
            db (AsyncSession): Database session for data access
            invoice (Invoice): Invoice record to validate
            
        Returns:
            Optional[InvoiceAdjustment]: Invoice adjustment if needed, None otherwise
        """
        with tracer.start_as_current_span("validate_invoice") as span:
            span.set_attribute("invoice_id", invoice.id)
            span.set_attribute("tenant", invoice.tenant)
            span.set_attribute("order_id", invoice.order_id)
            
            # Get order events to recalculate expected amount
            query = select(OrderEvent).where(
                OrderEvent.tenant == invoice.tenant,
                OrderEvent.order_id == invoice.order_id
            )
            result = await db.execute(query)
            events = result.scalars().all()
            
            # Calculate expected operations from events
            operations = self._calculate_operations_from_events(events)
            
            # Calculate expected amount
            expected_amount = compute_amount_cents(operations, invoice.tenant)
            
            span.set_attribute("original_amount", invoice.amount_cents)
            span.set_attribute("expected_amount", expected_amount)
            
            # Check if adjustment is needed
            if invoice.amount_cents != expected_amount:
                adjustment_cents = expected_amount - invoice.amount_cents
                
                # Create adjustment record
                adjustment = InvoiceAdjustment(
                    tenant=invoice.tenant,
                    invoice_id=invoice.id,
                    reason="RECALCULATION",
                    delta_cents=adjustment_cents,
                    rationale=f"Recalculated amount based on actual operations. Expected: ${expected_amount/100:.2f}, Original: ${invoice.amount_cents/100:.2f}",
                    created_by="system"
                )
                
                db.add(adjustment)
                await db.flush()
                
                span.set_attribute("adjustment_created", True)
                span.set_attribute("delta_cents", adjustment_cents)
                
                return adjustment
            
            span.set_attribute("adjustment_created", False)
            return None
    
    # ==== OPERATIONS CALCULATION ==== #
    
    def _calculate_operations_from_events(self, events: list) -> Dict[str, Any]:
        """
        Calculate billable operations from order events.
        
        Analyzes order event history to determine billable
        operations including picks, packs, labels, and storage
        duration for accurate billing calculations.
        
        Args:
            events (list): List of order events to analyze
            
        Returns:
            Dict[str, Any]: Dictionary of operations for billing calculations
        """
        operations = {
            "pick": 0,
            "pack": 0,
            "label": 0,
            "kitting": 0,
            "storage_days": 0,
            "returns": 0
        }
        
        # Count operations based on event types
        for event in events:
            if event.event_type == "pick_completed":
                operations["pick"] += 1
            elif event.event_type == "pack_completed":
                operations["pack"] += 1
            elif event.event_type in ["ship_label_printed", "label_created"]:
                operations["label"] += 1
            elif event.event_type == "kitting_completed":
                operations["kitting"] += 1
            elif event.event_type == "return_processed":
                operations["returns"] += 1
        
        # Calculate storage days (simplified - would be more complex in real system)
        if events:
            first_event = min(events, key=lambda e: e.occurred_at)
            last_event = max(events, key=lambda e: e.occurred_at)
            storage_duration = last_event.occurred_at - first_event.occurred_at
            operations["storage_days"] = max(1, storage_duration.days)
        
        return operations


# ==== BILLING CALCULATION FUNCTIONS ==== #


def compute_amount_cents(
    operations: Dict[str, Any], 
    tenant: str = "default"
) -> int:
    """
    Compute invoice amount in cents based on operations.
    
    Calculates comprehensive billing amounts including core operations,
    storage fees, value-added services, and volume discounts with
    tenant-specific configuration support.
    
    Args:
        operations (Dict[str, Any]): Dictionary of billable operations
        tenant (str): Tenant identifier for billing configuration
        
    Returns:
        int: Total amount in cents
    """
    with tracer.start_as_current_span("compute_billing_amount") as span:
        span.set_attribute("tenant", tenant)
        
        # Get billing configuration
        billing_config = get_billing_config(tenant)
        
        total_cents = 0
        
        # Core operation fees
        pick_count = operations.get("pick", 0)
        pack_count = operations.get("pack", 0)
        label_count = operations.get("label", 0)
        kitting_count = operations.get("kitting", 0)
        
        total_cents += pick_count * billing_config.get("pick_fee_cents", 30)
        total_cents += pack_count * billing_config.get("pack_fee_cents", 20)
        total_cents += label_count * billing_config.get("label_fee_cents", 15)
        total_cents += kitting_count * billing_config.get("kitting_fee_cents", 50)
        
        # Storage fees
        storage_days = operations.get("storage_days", 0)
        if storage_days > 0:
            storage_rate = billing_config.get("storage_fee_cents_per_day", 5)
            
            # Check for long-term storage
            long_term_days = billing_config.get("long_term_storage_days", 90)
            long_term_multiplier = billing_config.get("long_term_storage_multiplier", 2.0)
            
            if storage_days > long_term_days:
                # Apply long-term storage rate
                regular_days = long_term_days
                long_term_days_count = storage_days - long_term_days
                
                total_cents += regular_days * storage_rate
                total_cents += int(long_term_days_count * storage_rate * long_term_multiplier)
            else:
                total_cents += storage_days * storage_rate
        
        # Value-added services
        if operations.get("photo", False):
            total_cents += billing_config.get("photo_fee_cents", 25)
        
        if operations.get("quality_check", False):
            total_cents += billing_config.get("quality_check_fee_cents", 50)
        
        if operations.get("custom_packaging", False):
            total_cents += billing_config.get("custom_packaging_fee_cents", 200)
        
        if operations.get("gift_wrap", False):
            total_cents += billing_config.get("gift_wrap_fee_cents", 100)
        
        # Return processing
        return_count = operations.get("returns", 0)
        if return_count > 0:
            return_fee = billing_config.get("return_processing_fee_cents", 75)
            restocking_fee = billing_config.get("restocking_fee_cents", 150)
            inspection_fee = billing_config.get("inspection_fee_cents", 25)
            
            total_cents += return_count * (return_fee + restocking_fee + inspection_fee)
        
        # Apply minimum fee
        min_fee = billing_config.get("min_order_fee_cents", 50)
        total_cents = max(total_cents, min_fee)
        
        # Apply multipliers for special handling
        if operations.get("rush", False):
            rush_multiplier = billing_config.get("rush_multiplier", 2.0)
            total_cents = int(total_cents * rush_multiplier)
        
        if operations.get("oversized", False):
            oversized_multiplier = billing_config.get("oversized_multiplier", 1.5)
            total_cents = int(total_cents * oversized_multiplier)
        
        if operations.get("hazmat", False):
            hazmat_multiplier = billing_config.get("hazmat_multiplier", 3.0)
            total_cents = int(total_cents * hazmat_multiplier)
        
        if operations.get("fragile", False):
            fragile_multiplier = billing_config.get("fragile_multiplier", 1.2)
            total_cents = int(total_cents * fragile_multiplier)
        
        # Apply volume discounts
        monthly_orders = operations.get("monthly_order_count", 0)
        if monthly_orders >= billing_config.get("volume_tier_3_orders", 1000):
            discount = billing_config.get("volume_tier_3_discount", 0.15)
            total_cents = int(total_cents * (1 - discount))
        elif monthly_orders >= billing_config.get("volume_tier_2_orders", 500):
            discount = billing_config.get("volume_tier_2_discount", 0.10)
            total_cents = int(total_cents * (1 - discount))
        elif monthly_orders >= billing_config.get("volume_tier_1_orders", 100):
            discount = billing_config.get("volume_tier_1_discount", 0.05)
            total_cents = int(total_cents * (1 - discount))
        
        span.set_attribute("total_amount_cents", total_cents)
        span.set_attribute("operations_count", sum([
            pick_count, pack_count, label_count, kitting_count
        ]))
        
        return total_cents


# ==== VALIDATION AND ANALYSIS FUNCTIONS ==== #


def validate_billing_operations(operations: Dict[str, Any]) -> Dict[str, str]:
    """
    Validate billing operations for completeness and accuracy.
    
    Performs comprehensive validation of billing operations
    including data type checks, range validation, and required
    field verification for data integrity.
    
    Args:
        operations (Dict[str, Any]): Dictionary of billing operations to validate
        
    Returns:
        Dict[str, str]: Dictionary of validation errors (empty if valid)
    """
    errors = {}
    
    # Check for required operations
    if not any(operations.get(op, 0) > 0 for op in ["pick", "pack", "label"]):
        errors["operations"] = "At least one core operation (pick, pack, label) is required"
    
    # Validate operation counts
    for op in ["pick", "pack", "label", "kitting", "returns"]:
        count = operations.get(op, 0)
        if not isinstance(count, int) or count < 0:
            errors[op] = f"Invalid {op} count: must be non-negative integer"
    
    # Validate storage days
    storage_days = operations.get("storage_days", 0)
    if not isinstance(storage_days, (int, float)) or storage_days < 0:
        errors["storage_days"] = "Invalid storage_days: must be non-negative number"
    
    # Validate boolean flags
    for flag in ["rush", "oversized", "hazmat", "fragile", "photo", "quality_check", "custom_packaging", "gift_wrap"]:
        value = operations.get(flag, False)
        if not isinstance(value, bool):
            errors[flag] = f"Invalid {flag}: must be boolean"
    
    return errors


def calculate_adjustment_impact(
    original_operations: Dict[str, Any],
    adjusted_operations: Dict[str, Any],
    tenant: str = "default"
) -> Dict[str, Any]:
    """
    Calculate the impact of billing adjustments.
    
    Analyzes the financial impact of billing adjustments by
    comparing original and adjusted operations with detailed
    change tracking and approval requirements.
    
    Args:
        original_operations (Dict[str, Any]): Original billing operations
        adjusted_operations (Dict[str, Any]): Adjusted billing operations
        tenant (str): Tenant identifier for configuration
        
    Returns:
        Dict[str, Any]: Dictionary with adjustment impact details
    """
    with tracer.start_as_current_span("calculate_adjustment_impact") as span:
        span.set_attribute("tenant", tenant)
        
        original_amount = compute_amount_cents(original_operations, tenant)
        adjusted_amount = compute_amount_cents(adjusted_operations, tenant)
        
        delta_cents = adjusted_amount - original_amount
        delta_percentage = (delta_cents / original_amount * 100) if original_amount > 0 else 0
        
        # Identify changed operations
        changed_operations = {}
        all_ops = set(original_operations.keys()) | set(adjusted_operations.keys())
        
        for op in all_ops:
            original_value = original_operations.get(op, 0)
            adjusted_value = adjusted_operations.get(op, 0)
            
            if original_value != adjusted_value:
                changed_operations[op] = {
                    "original": original_value,
                    "adjusted": adjusted_value,
                    "delta": adjusted_value - original_value
                }
        
        impact = {
            "original_amount_cents": original_amount,
            "adjusted_amount_cents": adjusted_amount,
            "delta_cents": delta_cents,
            "delta_percentage": round(delta_percentage, 2),
            "changed_operations": changed_operations,
            "requires_approval": abs(delta_cents) > 500  # Require approval for changes > $5
        }
        
        span.set_attribute("delta_cents", delta_cents)
        span.set_attribute("delta_percentage", delta_percentage)
        span.set_attribute("requires_approval", impact["requires_approval"])
        
        return impact


# ==== BILLING SUMMARY GENERATION ==== #


def generate_billing_summary(
    operations: Dict[str, Any],
    tenant: str = "default"
) -> Dict[str, Any]:
    """
    Generate a detailed billing summary.
    
    Creates comprehensive billing summaries with line items,
    multipliers, and total calculations for operational
    transparency and customer billing accuracy.
    
    Args:
        operations (Dict[str, Any]): Billing operations to summarize
        tenant (str): Tenant identifier for configuration
        
    Returns:
        Dict[str, Any]: Detailed billing summary with line items
    """
    billing_config = get_billing_config(tenant)
    
    # Calculate line items
    line_items = []
    
    # Core operations
    for op, rate_key in [
        ("pick", "pick_fee_cents"),
        ("pack", "pack_fee_cents"),
        ("label", "label_fee_cents"),
        ("kitting", "kitting_fee_cents")
    ]:
        count = operations.get(op, 0)
        if count > 0:
            rate = billing_config.get(rate_key, 0)
            line_items.append({
                "description": f"{op.title()} operations",
                "quantity": count,
                "rate_cents": rate,
                "amount_cents": count * rate
            })
    
    # Storage
    storage_days = operations.get("storage_days", 0)
    if storage_days > 0:
        rate = billing_config.get("storage_fee_cents_per_day", 5)
        line_items.append({
            "description": f"Storage ({storage_days} days)",
            "quantity": storage_days,
            "rate_cents": rate,
            "amount_cents": storage_days * rate
        })
    
    # Value-added services
    for service, rate_key in [
        ("photo", "photo_fee_cents"),
        ("quality_check", "quality_check_fee_cents"),
        ("custom_packaging", "custom_packaging_fee_cents"),
        ("gift_wrap", "gift_wrap_fee_cents")
    ]:
        if operations.get(service, False):
            rate = billing_config.get(rate_key, 0)
            line_items.append({
                "description": service.replace("_", " ").title(),
                "quantity": 1,
                "rate_cents": rate,
                "amount_cents": rate
            })
    
    subtotal = sum(item["amount_cents"] for item in line_items)
    
    # Apply minimum fee
    min_fee = billing_config.get("min_order_fee_cents", 50)
    minimum_applied = subtotal < min_fee
    if minimum_applied:
        subtotal = min_fee
    
    # Apply multipliers
    multipliers = []
    total = subtotal
    
    for multiplier_key, description in [
        ("rush_multiplier", "Rush processing"),
        ("oversized_multiplier", "Oversized handling"),
        ("hazmat_multiplier", "Hazardous materials"),
        ("fragile_multiplier", "Fragile handling")
    ]:
        flag_key = multiplier_key.replace("_multiplier", "")
        if operations.get(flag_key, False):
            multiplier = billing_config.get(multiplier_key, 1.0)
            multipliers.append({
                "description": description,
                "multiplier": multiplier
            })
            total = int(total * multiplier)
    
    return {
        "line_items": line_items,
        "subtotal_cents": subtotal,
        "minimum_fee_applied": minimum_applied,
        "multipliers": multipliers,
        "total_cents": total,
        "currency": "USD"
    }
