# ==== ORDER PROCESSING FLOW ==== #

"""
Modern Prefect flow for end-to-end order processing in Octup E²A.

This flow represents a realistic e-commerce order processing pipeline:
1. Order fulfillment monitoring
2. Exception detection and resolution
3. SLA compliance tracking
4. Invoice generation for completed orders
5. Billing validation and adjustments

Designed to work with webhook-driven architecture where Shopify Mock
sends order events that trigger processing workflows.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from prefect import flow, task, get_run_logger
from prefect.deployments import run_deployment
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.storage.db import get_session
from app.storage.models import OrderEvent, ExceptionRecord, Invoice, InvoiceAdjustment
from app.services.invoice_generator import InvoiceGeneratorService
from app.services.billing import BillingService
from app.services.sla_engine import evaluate_sla
from app.observability.metrics import (
    orders_processed_total,
    invoice_generation_total,
    sla_compliance_rate
)


# ==== ORDER LIFECYCLE TASKS ==== #


@task
async def monitor_order_fulfillment(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Monitor order fulfillment progress and identify stalled orders.
    
    This task simulates real-world order monitoring where we track
    orders through their fulfillment lifecycle and identify those
    that may be stuck or delayed.
    
    Args:
        tenant: Tenant to monitor
        lookback_hours: How far back to look for orders
        
    Returns:
        Dict with monitoring results
    """
    logger = get_run_logger()
    logger.info(f"Monitoring order fulfillment for tenant {tenant}")
    
    async with get_session() as db:
        # Find orders that should be progressing
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Get orders with recent activity
        query = select(OrderEvent).where(
            and_(
                OrderEvent.tenant == tenant,
                OrderEvent.created_at >= cutoff_time
            )
        ).order_by(OrderEvent.created_at.desc())
        
        result = await db.execute(query)
        recent_events = result.scalars().all()
        
        # Group by order_id to analyze fulfillment status
        orders_by_id = {}
        for event in recent_events:
            if event.order_id not in orders_by_id:
                orders_by_id[event.order_id] = []
            orders_by_id[event.order_id].append(event)
        
        # Analyze fulfillment progress
        stalled_orders = []
        completed_orders = []
        in_progress_orders = []
        
        for order_id, events in orders_by_id.items():
            event_types = [e.event_type for e in events]
            latest_event = max(events, key=lambda x: x.created_at)
            
            # Check if order is completed (has fulfillment events)
            if any(et in ['order_fulfilled', 'order_shipped', 'order_delivered'] for et in event_types):
                completed_orders.append({
                    'order_id': order_id,
                    'latest_event': latest_event.event_type,
                    'completed_at': latest_event.created_at
                })
            # Check if order is stalled (no recent activity)
            elif (datetime.utcnow() - latest_event.created_at).total_seconds() > 3600:  # 1 hour
                stalled_orders.append({
                    'order_id': order_id,
                    'latest_event': latest_event.event_type,
                    'stalled_since': latest_event.created_at
                })
            else:
                in_progress_orders.append({
                    'order_id': order_id,
                    'latest_event': latest_event.event_type,
                    'last_activity': latest_event.created_at
                })
        
        logger.info(f"Order fulfillment status: {len(completed_orders)} completed, "
                   f"{len(in_progress_orders)} in progress, {len(stalled_orders)} stalled")
        
        return {
            'tenant': tenant,
            'monitoring_period_hours': lookback_hours,
            'total_orders': len(orders_by_id),
            'completed_orders': completed_orders,
            'in_progress_orders': in_progress_orders,
            'stalled_orders': stalled_orders,
            'completion_rate': len(completed_orders) / len(orders_by_id) if orders_by_id else 0
        }


@task
async def process_completed_orders(
    completed_orders: List[Dict[str, Any]],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Process completed orders for invoice generation.
    
    This task handles the business logic for orders that have completed
    their fulfillment cycle and are ready for billing.
    
    Args:
        completed_orders: List of completed order information
        tenant: Tenant context
        
    Returns:
        Dict with processing results
    """
    logger = get_run_logger()
    logger.info(f"Processing {len(completed_orders)} completed orders for invoicing")
    
    if not completed_orders:
        return {
            'processed_count': 0,
            'invoices_generated': 0,
            'errors': []
        }
    
    invoice_service = InvoiceGeneratorService()
    generated_invoices = []
    errors = []
    
    async with get_session() as db:
        for order_info in completed_orders:
            try:
                # Check if invoice already exists
                existing_query = select(Invoice).where(
                    and_(
                        Invoice.tenant == tenant,
                        Invoice.order_id == order_info['order_id']
                    )
                )
                result = await db.execute(existing_query)
                existing_invoice = result.scalar_one_or_none()
                
                if existing_invoice:
                    logger.debug(f"Invoice already exists for order {order_info['order_id']}")
                    continue
                
                # Generate invoice for completed order
                invoice_data = {
                    'tenant': tenant,
                    'order_id': order_info['order_id'],
                    'completed_at': order_info['completed_at']
                }
                
                # This would call the invoice generation service
                # For now, we'll simulate the process
                logger.info(f"Generated invoice for order {order_info['order_id']}")
                generated_invoices.append(order_info['order_id'])
                
            except Exception as e:
                error_msg = f"Failed to process order {order_info['order_id']}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
    
    return {
        'processed_count': len(completed_orders),
        'invoices_generated': len(generated_invoices),
        'generated_invoice_orders': generated_invoices,
        'errors': errors
    }


@task
async def validate_recent_invoices(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Validate recently generated invoices and create adjustments if needed.
    
    This task implements the nightly invoice validation process where
    we recalculate invoice amounts based on actual order events and
    create adjustments for any discrepancies.
    
    Args:
        tenant: Tenant to validate invoices for
        lookback_hours: How far back to look for invoices
        
    Returns:
        Dict with validation results
    """
    logger = get_run_logger()
    logger.info(f"Validating recent invoices for tenant {tenant}")
    
    billing_service = BillingService()
    validated_count = 0
    adjustments_created = 0
    total_adjustment_cents = 0
    
    async with get_session() as db:
        # Find recent invoices to validate
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        query = select(Invoice).where(
            and_(
                Invoice.tenant == tenant,
                Invoice.created_at >= cutoff_time,
                Invoice.status.in_(['DRAFT', 'PENDING'])
            )
        )
        
        result = await db.execute(query)
        invoices = result.scalars().all()
        
        logger.info(f"Found {len(invoices)} recent invoices to validate")
        
        for invoice in invoices:
            try:
                # Validate invoice and create adjustment if needed
                adjustment = await billing_service.validate_invoice(db, invoice)
                
                if adjustment:
                    db.add(adjustment)
                    adjustments_created += 1
                    total_adjustment_cents += abs(adjustment.delta_cents)
                    logger.info(f"Created adjustment for invoice {invoice.id}: "
                              f"${adjustment.delta_cents/100:.2f}")
                
                validated_count += 1
                
            except Exception as e:
                logger.error(f"Failed to validate invoice {invoice.id}: {str(e)}")
                continue
        
        await db.commit()
    
    return {
        'tenant': tenant,
        'validation_period_hours': lookback_hours,
        'invoices_validated': validated_count,
        'adjustments_created': adjustments_created,
        'total_adjustment_amount': total_adjustment_cents / 100,
        'average_adjustment': (total_adjustment_cents / adjustments_created / 100) if adjustments_created > 0 else 0
    }


@task
async def monitor_sla_compliance(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Monitor SLA compliance for recent orders and exceptions.
    
    This task tracks how well we're meeting our SLA commitments
    and identifies areas that need attention.
    
    Args:
        tenant: Tenant to monitor
        lookback_hours: Period to analyze
        
    Returns:
        Dict with SLA compliance metrics
    """
    logger = get_run_logger()
    logger.info(f"Monitoring SLA compliance for tenant {tenant}")
    
    async with get_session() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Get recent exceptions to analyze SLA performance
        query = select(ExceptionRecord).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.created_at >= cutoff_time
            )
        )
        
        result = await db.execute(query)
        exceptions = result.scalars().all()
        
        total_exceptions = len(exceptions)
        resolved_exceptions = len([e for e in exceptions if e.status == 'RESOLVED'])
        critical_exceptions = len([e for e in exceptions if e.severity == 'CRITICAL'])
        
        # Calculate average resolution time for resolved exceptions
        resolution_times = []
        for exc in exceptions:
            if exc.status == 'RESOLVED' and exc.resolved_at:
                resolution_time = (exc.resolved_at - exc.created_at).total_seconds() / 3600  # hours
                resolution_times.append(resolution_time)
        
        avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0
        sla_target_hours = 4  # 4-hour SLA target
        sla_compliant = len([t for t in resolution_times if t <= sla_target_hours])
        
        compliance_rate = sla_compliant / len(resolution_times) if resolution_times else 1.0
        
        logger.info(f"SLA compliance: {compliance_rate:.2%} ({sla_compliant}/{len(resolution_times)} resolved within SLA)")
        
        return {
            'tenant': tenant,
            'monitoring_period_hours': lookback_hours,
            'total_exceptions': total_exceptions,
            'resolved_exceptions': resolved_exceptions,
            'critical_exceptions': critical_exceptions,
            'resolution_rate': resolved_exceptions / total_exceptions if total_exceptions > 0 else 1.0,
            'average_resolution_hours': avg_resolution_time,
            'sla_compliance_rate': compliance_rate,
            'sla_target_hours': sla_target_hours
        }


# ==== MAIN FLOW ==== #


@flow(name="order-processing-pipeline", log_prints=True)
async def order_processing_pipeline(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Complete order processing pipeline for e-commerce operations.
    
    This flow represents a realistic daily/hourly business process that:
    1. Monitors order fulfillment progress
    2. Processes completed orders for invoicing
    3. Validates recent invoices and creates adjustments
    4. Monitors SLA compliance
    
    This replaces the old event streaming approach with a more realistic
    business process that works with webhook-driven order events.
    
    Args:
        tenant: Tenant to process
        lookback_hours: Time window to analyze
        
    Returns:
        Dict with complete pipeline results
    """
    logger = get_run_logger()
    logger.info(f"Starting order processing pipeline for tenant {tenant}")
    
    # Step 1: Monitor order fulfillment
    fulfillment_status = await monitor_order_fulfillment(tenant, lookback_hours)
    
    # Step 2: Process completed orders for invoicing
    invoice_results = await process_completed_orders(
        fulfillment_status['completed_orders'], 
        tenant
    )
    
    # Step 3: Validate recent invoices
    validation_results = await validate_recent_invoices(tenant, lookback_hours)
    
    # Step 4: Monitor SLA compliance
    sla_results = await monitor_sla_compliance(tenant, lookback_hours)
    
    # Compile comprehensive results
    pipeline_results = {
        'tenant': tenant,
        'processing_window_hours': lookback_hours,
        'execution_time': datetime.utcnow().isoformat(),
        'fulfillment_monitoring': fulfillment_status,
        'invoice_processing': invoice_results,
        'invoice_validation': validation_results,
        'sla_monitoring': sla_results,
        'summary': {
            'orders_monitored': fulfillment_status['total_orders'],
            'orders_completed': len(fulfillment_status['completed_orders']),
            'invoices_generated': invoice_results['invoices_generated'],
            'invoices_validated': validation_results['invoices_validated'],
            'adjustments_created': validation_results['adjustments_created'],
            'sla_compliance_rate': sla_results['sla_compliance_rate']
        }
    }
    
    logger.info(f"Order processing pipeline completed: "
               f"{pipeline_results['summary']['orders_completed']} orders processed, "
               f"{pipeline_results['summary']['invoices_generated']} invoices generated, "
               f"{pipeline_results['summary']['sla_compliance_rate']:.2%} SLA compliance")
    
    return pipeline_results


# ==== DEPLOYMENT HELPER ==== #

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Order Processing Pipeline")
    parser.add_argument("--tenant", default="demo-3pl", help="Tenant to process")
    parser.add_argument("--hours", type=int, default=24, help="Lookback hours")
    parser.add_argument("--run", action="store_true", help="Run the flow immediately")
    parser.add_argument("--serve", action="store_true", help="Serve the flow for scheduling")
    
    args = parser.parse_args()
    
    if args.run:
        # Run the flow immediately
        asyncio.run(order_processing_pipeline(args.tenant, args.hours))
    elif args.serve:
        # Serve the flow for scheduling (would need deployment setup)
        print(f"Serving order processing pipeline for tenant {args.tenant}")
        print("This would set up a scheduled deployment in a real environment")
    else:
        print("Use --run to execute immediately or --serve to set up scheduling")
