# ==== BUSINESS OPERATIONS FLOW ==== #

"""
Consolidated business operations flow for Octup E²A.

This flow combines order fulfillment monitoring, invoice generation,
billing validation, and financial reporting into a single, efficient
daily operations pipeline. Replaces the fragmented approach of separate
billing and orchestration flows.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal

from prefect import flow, task, get_run_logger
from sqlalchemy import select, and_, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.storage.db import get_session
from app.storage.models import OrderEvent, Invoice, InvoiceAdjustment, ExceptionRecord
from app.services.invoice_generator import InvoiceGeneratorService
from app.services.billing import BillingService, compute_amount_cents
from app.services.policy_loader import get_billing_config


@task(retries=3, retry_delay_seconds=300)
async def monitor_order_fulfillment(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Monitor order fulfillment progress and identify stalled orders.
    
    Args:
        tenant: Tenant identifier
        lookback_hours: Hours to look back for order analysis
        
    Returns:
        Fulfillment monitoring results
    """
    logger = get_run_logger()
    logger.info(f"Monitoring order fulfillment for tenant {tenant}")
    
    async with get_session() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Get recent order events
        query = select(OrderEvent).where(
            and_(
                OrderEvent.tenant == tenant,
                OrderEvent.created_at >= cutoff_time
            )
        ).order_by(OrderEvent.order_id, OrderEvent.created_at)
        
        result = await db.execute(query)
        events = result.scalars().all()
        
        # Group by order_id and analyze status
        orders_by_status = {
            "created": 0,
            "processing": 0,
            "fulfilled": 0,
            "delivered": 0,
            "stalled": 0
        }
        
        orders_events = {}
        for event in events:
            if event.order_id not in orders_events:
                orders_events[event.order_id] = []
            orders_events[event.order_id].append(event)
        
        for order_id, order_events in orders_events.items():
            event_types = [e.event_type for e in order_events]
            
            if "delivered" in event_types:
                orders_by_status["delivered"] += 1
            elif "order_fulfilled" in event_types or "package_shipped" in event_types:
                orders_by_status["fulfilled"] += 1
            elif any(t in event_types for t in ["pick_completed", "pack_completed"]):
                orders_by_status["processing"] += 1
            elif "order_created" in event_types:
                # Check if stalled (created > 4 hours ago with no progress)
                created_event = next(e for e in order_events if e.event_type == "order_created")
                if datetime.utcnow() - created_event.occurred_at > timedelta(hours=4):
                    orders_by_status["stalled"] += 1
                else:
                    orders_by_status["created"] += 1
        
        return {
            "total_orders": len(orders_events),
            "orders_by_status": orders_by_status,
            "monitoring_period_hours": lookback_hours
        }


@task(retries=3, retry_delay_seconds=300)
async def identify_billable_orders(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Identify orders ready for billing and invoice generation.
    
    Args:
        tenant: Tenant identifier
        lookback_hours: Hours to look back for completed orders
        
    Returns:
        Billable orders analysis
    """
    logger = get_run_logger()
    logger.info(f"Identifying billable orders for tenant {tenant}")
    
    async with get_session() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Find fulfilled orders without invoices
        fulfilled_orders_query = text("""
            SELECT oe.order_id
            FROM order_events oe
            WHERE oe.tenant = :tenant
            AND oe.event_type IN ('order_fulfilled', 'package_shipped', 'delivered')
            AND oe.created_at >= :cutoff_time
            AND NOT EXISTS (
                SELECT 1 FROM invoices i 
                WHERE i.tenant = :tenant AND i.order_id = oe.order_id
            )
            GROUP BY oe.order_id
        """)
        
        result = await db.execute(
            fulfilled_orders_query,
            {"tenant": tenant, "cutoff_time": cutoff_time}
        )
        
        billable_orders = []
        for row in result:
            billable_orders.append({
                "order_id": row.order_id,
                "payload": {}  # Simplified - just track order IDs for billing
            })
        
        return {
            "billable_orders_count": len(billable_orders),
            "billable_orders": billable_orders[:10],  # Sample for logging
            "analysis_period_hours": lookback_hours
        }


@task(retries=3, retry_delay_seconds=300)
async def generate_invoices(
    billable_orders: List[Dict[str, Any]],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Generate invoices for billable orders.
    
    Args:
        tenant: Tenant identifier
        billable_orders: List of orders ready for billing
        
    Returns:
        Invoice generation results
    """
    logger = get_run_logger()
    logger.info(f"Generating invoices for {len(billable_orders)} orders")
    
    async with get_session() as db:
        invoice_service = InvoiceGeneratorService()
        
        generated_count = 0
        failed_count = 0
        total_amount = Decimal('0.00')
        
        for order_data in billable_orders:
            try:
                order_id = order_data["order_id"]
                payload = order_data["payload"]
                
                # Extract order details for invoice
                order_info = payload.get("data", {}).get("order", payload)
                
                invoice_data = {
                    "order_id": order_id,
                    "customer_email": order_info.get("customer", {}).get("email", ""),
                    "total_amount": float(order_info.get("total_price", 0)),
                    "currency": order_info.get("currency", "USD"),
                    "line_items": order_info.get("line_items", [])
                }
                
                invoice = await invoice_service.generate_invoice(
                    tenant=tenant,
                    **invoice_data
                )
                
                if invoice:
                    generated_count += 1
                    total_amount += Decimal(str(invoice.amount_cents)) / 100
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to generate invoice for order {order_data.get('order_id')}: {e}")
                failed_count += 1
        
        await db.commit()
        
        return {
            "invoices_generated": generated_count,
            "generation_failures": failed_count,
            "total_invoice_amount": float(total_amount),
            "success_rate": generated_count / len(billable_orders) if billable_orders else 0
        }


@task(retries=2, retry_delay_seconds=180)
async def validate_invoices(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Validate recent invoices for accuracy and completeness.
    
    Args:
        tenant: Tenant identifier
        lookback_hours: Hours to look back for invoice validation
        
    Returns:
        Invoice validation results
    """
    logger = get_run_logger()
    logger.info(f"Validating invoices for tenant {tenant}")
    
    async with get_session() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Get recent invoices
        query = select(Invoice).where(
            and_(
                Invoice.tenant == tenant,
                Invoice.created_at >= cutoff_time
            )
        ).order_by(Invoice.created_at.desc())
        
        result = await db.execute(query)
        invoices = result.scalars().all()
        
        validation_results = {
            "total_invoices": len(invoices),
            "valid_invoices": 0,
            "invalid_invoices": 0,
            "validation_issues": []
        }
        
        for invoice in invoices:
            is_valid = True
            issues = []
            
            # Basic validation checks
            if not invoice.order_id:
                issues.append("Missing order_id")
                is_valid = False
                
            if invoice.amount_cents <= 0:
                issues.append("Invalid amount")
                is_valid = False
                
            if not invoice.currency or len(invoice.currency) != 3:
                issues.append("Invalid currency")
                is_valid = False
            
            if is_valid:
                validation_results["valid_invoices"] += 1
            else:
                validation_results["invalid_invoices"] += 1
                validation_results["validation_issues"].extend(issues)
        
        validation_success_rate = (
            validation_results["valid_invoices"] / validation_results["total_invoices"]
            if validation_results["total_invoices"] > 0 else 1.0
        )
        
        return {
            **validation_results,
            "validation_success_rate": validation_success_rate
        }


@task(retries=2, retry_delay_seconds=180)
async def process_billing_adjustments(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Process billing adjustments for exceptions and disputes.
    
    Args:
        tenant: Tenant identifier
        lookback_hours: Hours to look back for adjustments
        
    Returns:
        Billing adjustment results
    """
    logger = get_run_logger()
    logger.info(f"Processing billing adjustments for tenant {tenant}")
    
    async with get_session() as db:
        billing_service = BillingService()
        
        # Find exceptions that may require billing adjustments
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        query = select(ExceptionRecord).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time,
                ExceptionRecord.severity.in_(["HIGH", "CRITICAL"]),
                ExceptionRecord.status == "RESOLVED"
            )
        )
        
        result = await db.execute(query)
        exceptions = result.scalars().all()
        
        adjustments_created = 0
        total_adjustment_amount = Decimal('0.00')
        
        for exception in exceptions:
            try:
                # Check if adjustment already exists
                existing_adjustment = await db.execute(
                    select(InvoiceAdjustment).where(
                        and_(
                            InvoiceAdjustment.tenant == tenant,
                            InvoiceAdjustment.reference_id == str(exception.id),
                            InvoiceAdjustment.adjustment_type == "exception_credit"
                        )
                    )
                )
                
                if existing_adjustment.scalar_one_or_none():
                    continue  # Already processed
                
                # Create adjustment for qualifying exceptions
                if exception.reason_code.startswith("SLA_"):
                    adjustment_amount = await billing_service.calculate_sla_penalty(
                        tenant, exception.order_id, exception.reason_code
                    )
                    
                    if adjustment_amount > 0:
                        adjustment = InvoiceAdjustment(
                            tenant=tenant,
                            order_id=exception.order_id,
                            adjustment_type="exception_credit",
                            amount_cents=compute_amount_cents(adjustment_amount),
                            currency="USD",
                            reason=f"SLA breach: {exception.reason_code}",
                            reference_id=str(exception.id)
                        )
                        
                        db.add(adjustment)
                        adjustments_created += 1
                        total_adjustment_amount += adjustment_amount
                        
            except Exception as e:
                logger.error(f"Failed to process adjustment for exception {exception.id}: {e}")
                continue
        
        await db.commit()
        
        return {
            "adjustments_created": adjustments_created,
            "total_adjustment_amount": float(total_adjustment_amount),
            "exceptions_reviewed": len(exceptions)
        }


@task(retries=2, retry_delay_seconds=120)
async def generate_business_metrics(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Generate business intelligence metrics and reports.
    
    Args:
        tenant: Tenant identifier
        lookback_hours: Hours to look back for metrics
        
    Returns:
        Business metrics and KPIs
    """
    logger = get_run_logger()
    logger.info(f"Generating business metrics for tenant {tenant}")
    
    async with get_session() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Order metrics
        order_count_query = select(func.count(func.distinct(OrderEvent.order_id))).where(
            and_(
                OrderEvent.tenant == tenant,
                OrderEvent.created_at >= cutoff_time
            )
        )
        order_count = await db.scalar(order_count_query) or 0
        
        # Exception metrics
        exception_count_query = select(func.count(ExceptionRecord.id)).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time
            )
        )
        exception_count = await db.scalar(exception_count_query) or 0
        
        # Invoice metrics
        invoice_metrics_query = select(
            func.count(Invoice.id),
            func.sum(Invoice.amount_cents)
        ).where(
            and_(
                Invoice.tenant == tenant,
                Invoice.created_at >= cutoff_time
            )
        )
        
        invoice_result = await db.execute(invoice_metrics_query)
        invoice_count, total_revenue_cents = invoice_result.first()
        
        invoice_count = invoice_count or 0
        total_revenue = float(total_revenue_cents or 0) / 100
        
        return {
            "period_hours": lookback_hours,
            "orders_processed": order_count,
            "exceptions_created": exception_count,
            "invoices_generated": invoice_count,
            "total_revenue": total_revenue,
            "exception_rate": exception_count / order_count if order_count > 0 else 0,
            "average_order_value": total_revenue / invoice_count if invoice_count > 0 else 0
        }


@flow(name="business-operations")
async def business_operations_flow(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24,
    enable_billing: bool = True
) -> Dict[str, Any]:
    """
    Main business operations flow for daily operations management.
    
    This flow consolidates order monitoring, invoice generation, billing validation,
    and business reporting into a single efficient pipeline.
    
    Args:
        tenant: Tenant identifier for operations
        lookback_hours: Hours to look back for processing
        enable_billing: Whether to enable billing operations
        
    Returns:
        Comprehensive business operations results
    """
    logger = get_run_logger()
    logger.info(f"Starting business operations flow for tenant {tenant}")
    
    # Phase 1: Order Fulfillment Monitoring
    fulfillment_results = await monitor_order_fulfillment(tenant, lookback_hours)
    
    # Phase 2: Billing Operations (if enabled)
    billing_results = {}
    if enable_billing:
        # Identify billable orders
        billable_analysis = await identify_billable_orders(tenant, lookback_hours)
        
        # Generate invoices for billable orders
        invoice_generation = await generate_invoices(
            billable_analysis.get("billable_orders", []),
            tenant
        )
        
        # Validate invoices
        invoice_validation = await validate_invoices(tenant, lookback_hours)
        
        # Process billing adjustments
        adjustment_processing = await process_billing_adjustments(tenant, lookback_hours)
        
        billing_results = {
            "billable_analysis": billable_analysis,
            "invoice_generation": invoice_generation,
            "invoice_validation": invoice_validation,
            "adjustment_processing": adjustment_processing
        }
    
    # Phase 3: Business Intelligence
    business_metrics = await generate_business_metrics(tenant, lookback_hours)
    
    # Compile comprehensive results
    results = {
        "tenant": tenant,
        "processing_timestamp": datetime.utcnow().isoformat(),
        "fulfillment_monitoring": fulfillment_results,
        "billing_operations": billing_results,
        "business_metrics": business_metrics,
        "summary": {
            "orders_monitored": fulfillment_results.get("total_orders", 0),
            "invoices_generated": billing_results.get("invoice_generation", {}).get("invoices_generated", 0),
            "total_revenue": business_metrics.get("total_revenue", 0),
            "exception_rate": business_metrics.get("exception_rate", 0)
        }
    }
    
    logger.info(f"Business operations flow completed: {results['summary']}")
    return results


if __name__ == "__main__":
    # For testing
    import asyncio
    result = asyncio.run(business_operations_flow())
    print(f"Flow result: {result}")
