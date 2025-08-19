# ==== BILLING MANAGEMENT FLOW ==== #

"""
Prefect flow for comprehensive billing and invoice management in Octup E²A.

This flow implements end-to-end billing operations that reflect real-world
financial processes:
1. Automated invoice generation from completed orders
2. Invoice validation and accuracy verification
3. Billing adjustments and dispute resolution
4. Revenue recognition and financial reporting
5. Customer billing communication

Designed to handle complex billing scenarios including partial fulfillments,
returns, adjustments, and multi-tenant billing configurations.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal

from prefect import flow, task, get_run_logger
from sqlalchemy import select, and_, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import get_session
from app.storage.models import OrderEvent, Invoice, InvoiceAdjustment, ExceptionRecord
from app.services.invoice_generator import InvoiceGeneratorService
from app.services.billing import BillingService, compute_amount_cents
from app.services.policy_loader import get_billing_config
# Removed problematic metrics imports - using basic logging


# ==== INVOICE GENERATION TASKS ==== #


@task
async def identify_billable_orders(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Identify orders that are ready for billing.
    
    This task analyzes order events to determine which orders have
    completed their fulfillment cycle and are ready for invoice generation.
    
    Real-world billing criteria:
    - Order has been fulfilled/shipped
    - No pending exceptions that affect billing
    - Minimum required events are present
    - Not already invoiced
    
    Args:
        tenant: Tenant to analyze
        lookback_hours: Time window to check for completed orders
        
    Returns:
        Dict with billable order information
    """
    logger = get_run_logger()
    logger.info(f"Identifying billable orders for tenant {tenant}")
    
    async with get_session() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Get recent order events
        events_query = select(OrderEvent).where(
            and_(
                OrderEvent.tenant == tenant,
                OrderEvent.created_at >= cutoff_time
            )
        ).order_by(OrderEvent.order_id, OrderEvent.created_at)
        
        result = await db.execute(events_query)
        events = result.scalars().all()
        
        # Group events by order_id
        orders_events = {}
        for event in events:
            if event.order_id not in orders_events:
                orders_events[event.order_id] = []
            orders_events[event.order_id].append(event)
        
        # Analyze each order for billing readiness
        billable_orders = []
        not_ready_orders = []
        
        for order_id, order_events in orders_events.items():
            # Check if already invoiced
            existing_invoice_query = select(Invoice).where(
                and_(
                    Invoice.tenant == tenant,
                    Invoice.order_id == order_id
                )
            )
            invoice_result = await db.execute(existing_invoice_query)
            existing_invoice = invoice_result.scalar_one_or_none()
            
            if existing_invoice:
                continue  # Already invoiced
            
            # Analyze order events for billing readiness
            event_types = [e.event_type for e in order_events]
            latest_event = max(order_events, key=lambda x: x.created_at)
            
            # Define billing criteria
            required_events = ['order_created']
            completion_events = ['order_fulfilled', 'order_shipped', 'order_delivered']
            
            has_required = all(req in event_types for req in required_events)
            has_completion = any(comp in event_types for comp in completion_events)
            
            # Check for blocking exceptions
            exceptions_query = select(ExceptionRecord).where(
                and_(
                    ExceptionRecord.tenant == tenant,
                    ExceptionRecord.order_id == order_id,
                    ExceptionRecord.status.in_(['OPEN', 'IN_PROGRESS'])
                )
            )
            exceptions_result = await db.execute(exceptions_query)
            blocking_exceptions = exceptions_result.scalars().all()
            
            # Determine billing readiness
            if has_required and has_completion and not blocking_exceptions:
                # Calculate billable operations
                operations = {
                    'order_processing': 1,
                    'fulfillment_events': len([e for e in event_types if e in completion_events]),
                    'exception_handling': len([e for e in order_events if 'exception' in e.event_type.lower()])
                }
                
                # Calculate estimated billing amount
                estimated_amount = compute_amount_cents(operations, tenant)
                
                billable_orders.append({
                    'order_id': order_id,
                    'event_count': len(order_events),
                    'latest_event': latest_event.event_type,
                    'completion_date': latest_event.created_at,
                    'operations': operations,
                    'estimated_amount_cents': estimated_amount,
                    'billing_ready': True
                })
            else:
                not_ready_orders.append({
                    'order_id': order_id,
                    'event_count': len(order_events),
                    'latest_event': latest_event.event_type,
                    'missing_requirements': {
                        'has_required_events': has_required,
                        'has_completion_events': has_completion,
                        'blocking_exceptions_count': len(blocking_exceptions)
                    },
                    'billing_ready': False
                })
        
        total_estimated_revenue = sum(order['estimated_amount_cents'] for order in billable_orders)
        
        logger.info(f"Billing analysis complete: {len(billable_orders)} orders ready for billing, "
                   f"estimated revenue: ${total_estimated_revenue/100:.2f}")
        
        return {
            'tenant': tenant,
            'analysis_period_hours': lookback_hours,
            'analysis_timestamp': datetime.utcnow().isoformat(),
            'billable_orders': billable_orders,
            'not_ready_orders': not_ready_orders,
            'summary': {
                'billable_count': len(billable_orders),
                'not_ready_count': len(not_ready_orders),
                'total_estimated_revenue_cents': total_estimated_revenue,
                'average_order_value_cents': total_estimated_revenue // len(billable_orders) if billable_orders else 0
            }
        }


@task
async def generate_invoices(
    billable_orders: List[Dict[str, Any]],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Generate invoices for billable orders.
    
    This task creates formal invoice records with proper numbering,
    billing details, and audit trails for financial compliance.
    
    Args:
        billable_orders: List of orders ready for billing
        tenant: Tenant context
        
    Returns:
        Dict with invoice generation results
    """
    logger = get_run_logger()
    logger.info(f"Generating invoices for {len(billable_orders)} orders")
    
    if not billable_orders:
        return {
            'tenant': tenant,
            'invoices_generated': 0,
            'total_amount_cents': 0,
            'generated_invoices': []
        }
    
    invoice_service = InvoiceGeneratorService()
    generated_invoices = []
    total_amount_cents = 0
    errors = []
    
    async with get_session() as db:
        # Get billing configuration
        billing_config = get_billing_config(tenant)
        
        for order_data in billable_orders:
            try:
                # Generate invoice number
                invoice_number = await _generate_invoice_number(db, tenant)
                
                # Create invoice record
                invoice = Invoice(
                    tenant=tenant,
                    order_id=order_data['order_id'],
                    invoice_number=invoice_number,
                    amount_cents=order_data['estimated_amount_cents'],
                    currency=billing_config.get('currency', 'USD'),
                    billable_ops=order_data['operations'],
                    status='DRAFT',
                    invoice_date=datetime.utcnow(),
                    due_date=datetime.utcnow() + timedelta(days=30),  # 30-day payment terms
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                db.add(invoice)
                await db.flush()  # Get the ID
                
                generated_invoices.append({
                    'invoice_id': invoice.id,
                    'invoice_number': invoice_number,
                    'order_id': order_data['order_id'],
                    'amount_cents': order_data['estimated_amount_cents'],
                    'operations': order_data['operations']
                })
                
                total_amount_cents += order_data['estimated_amount_cents']
                
                logger.info(f"Generated invoice {invoice_number} for order {order_data['order_id']}: "
                           f"${order_data['estimated_amount_cents']/100:.2f}")
                
            except Exception as e:
                error_msg = f"Failed to generate invoice for order {order_data['order_id']}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        await db.commit()
    
    logger.info(f"Invoice generation complete: {len(generated_invoices)} invoices generated, "
               f"total amount: ${total_amount_cents/100:.2f}")
    
    return {
        'tenant': tenant,
        'invoices_generated': len(generated_invoices),
        'total_amount_cents': total_amount_cents,
        'generated_invoices': generated_invoices,
        'errors': errors
    }


@task
async def validate_invoice_accuracy(
    generated_invoices: List[Dict[str, Any]],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Validate invoice accuracy by recalculating amounts from source data.
    
    This task implements financial controls by independently verifying
    invoice amounts against actual order events and operations performed.
    
    Args:
        generated_invoices: List of generated invoice data
        tenant: Tenant context
        
    Returns:
        Dict with validation results and any required adjustments
    """
    logger = get_run_logger()
    logger.info(f"Validating accuracy of {len(generated_invoices)} invoices")
    
    if not generated_invoices:
        return {
            'tenant': tenant,
            'invoices_validated': 0,
            'adjustments_needed': 0,
            'validation_results': []
        }
    
    billing_service = BillingService()
    validation_results = []
    adjustments_needed = 0
    total_adjustment_cents = 0
    
    async with get_session() as db:
        for invoice_data in generated_invoices:
            try:
                # Get the invoice record
                invoice_query = select(Invoice).where(Invoice.id == invoice_data['invoice_id'])
                result = await db.execute(invoice_query)
                invoice = result.scalar_one()
                
                # Validate the invoice
                adjustment = await billing_service.validate_invoice(db, invoice)
                
                validation_result = {
                    'invoice_id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                    'order_id': invoice.order_id,
                    'original_amount_cents': invoice.amount_cents,
                    'validation_passed': adjustment is None
                }
                
                if adjustment:
                    # Add adjustment to database
                    db.add(adjustment)
                    adjustments_needed += 1
                    total_adjustment_cents += abs(adjustment.delta_cents)
                    
                    validation_result.update({
                        'adjustment_needed': True,
                        'adjustment_amount_cents': adjustment.delta_cents,
                        'adjustment_reason': adjustment.reason,
                        'corrected_amount_cents': invoice.amount_cents + adjustment.delta_cents
                    })
                    
                    logger.warning(f"Invoice {invoice.invoice_number} requires adjustment: "
                                 f"${adjustment.delta_cents/100:.2f}")
                else:
                    validation_result['adjustment_needed'] = False
                
                validation_results.append(validation_result)
                
            except Exception as e:
                logger.error(f"Failed to validate invoice {invoice_data['invoice_id']}: {str(e)}")
                validation_results.append({
                    'invoice_id': invoice_data['invoice_id'],
                    'validation_passed': False,
                    'error': str(e)
                })
        
        await db.commit()
    
    validation_rate = len([r for r in validation_results if r.get('validation_passed', False)]) / len(validation_results)
    
    logger.info(f"Invoice validation complete: {validation_rate:.1%} passed validation, "
               f"{adjustments_needed} adjustments needed")
    
    return {
        'tenant': tenant,
        'invoices_validated': len(validation_results),
        'validation_success_rate': validation_rate,
        'adjustments_needed': adjustments_needed,
        'total_adjustment_amount_cents': total_adjustment_cents,
        'validation_results': validation_results
    }


@task
async def process_billing_adjustments(
    validation_results: Dict[str, Any],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Process billing adjustments and update invoice statuses.
    
    This task handles the financial reconciliation process by applying
    approved adjustments and updating invoice statuses for billing.
    
    Args:
        validation_results: Output from validate_invoice_accuracy
        tenant: Tenant context
        
    Returns:
        Dict with adjustment processing results
    """
    logger = get_run_logger()
    logger.info(f"Processing billing adjustments for tenant {tenant}")
    
    validation_data = validation_results.get('validation_results', [])
    adjustments_to_process = [r for r in validation_data if r.get('adjustment_needed', False)]
    
    if not adjustments_to_process:
        return {
            'tenant': tenant,
            'adjustments_processed': 0,
            'invoices_finalized': len(validation_data),
            'total_revenue_impact_cents': 0
        }
    
    processed_adjustments = 0
    total_revenue_impact_cents = 0
    finalized_invoices = 0
    
    async with get_session() as db:
        for adjustment_data in adjustments_to_process:
            try:
                # Get the invoice
                invoice_query = select(Invoice).where(Invoice.id == adjustment_data['invoice_id'])
                result = await db.execute(invoice_query)
                invoice = result.scalar_one()
                
                # Apply the adjustment to the invoice amount
                adjustment_cents = adjustment_data['adjustment_amount_cents']
                invoice.amount_cents += adjustment_cents
                invoice.updated_at = datetime.utcnow()
                
                # Add note about adjustment
                if not invoice.notes:
                    invoice.notes = ""
                invoice.notes += f"\nAdjustment applied: ${adjustment_cents/100:.2f} - {adjustment_data.get('adjustment_reason', 'Validation correction')}"
                
                processed_adjustments += 1
                total_revenue_impact_cents += adjustment_cents
                
                logger.info(f"Applied adjustment to invoice {invoice.invoice_number}: "
                           f"${adjustment_cents/100:.2f}")
                
            except Exception as e:
                logger.error(f"Failed to process adjustment for invoice {adjustment_data['invoice_id']}: {str(e)}")
                continue
        
        # Finalize all validated invoices (move from DRAFT to PENDING)
        for result_data in validation_data:
            try:
                invoice_query = select(Invoice).where(Invoice.id == result_data['invoice_id'])
                result = await db.execute(invoice_query)
                invoice = result.scalar_one()
                
                if invoice.status == 'DRAFT':
                    invoice.status = 'PENDING'
                    invoice.updated_at = datetime.utcnow()
                    finalized_invoices += 1
                
            except Exception as e:
                logger.error(f"Failed to finalize invoice {result_data['invoice_id']}: {str(e)}")
                continue
        
        await db.commit()
    
    logger.info(f"Adjustment processing complete: {processed_adjustments} adjustments applied, "
               f"{finalized_invoices} invoices finalized")
    
    return {
        'tenant': tenant,
        'adjustments_processed': processed_adjustments,
        'invoices_finalized': finalized_invoices,
        'total_revenue_impact_cents': total_revenue_impact_cents,
        'net_revenue_adjustment': total_revenue_impact_cents / 100
    }


@task
async def generate_billing_report(
    billing_results: Dict[str, Any],
    tenant: str = "demo-3pl"
) -> Dict[str, Any]:
    """
    Generate comprehensive billing report for financial analysis.
    
    This task creates detailed billing analytics and financial summaries
    for business intelligence and financial reporting purposes.
    
    Args:
        billing_results: Combined results from billing pipeline
        tenant: Tenant context
        
    Returns:
        Dict with comprehensive billing report
    """
    logger = get_run_logger()
    logger.info(f"Generating billing report for tenant {tenant}")
    
    async with get_session() as db:
        # Get current period statistics
        current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Monthly invoice statistics
        monthly_invoices_query = select(
            func.count(Invoice.id).label('invoice_count'),
            func.sum(Invoice.amount_cents).label('total_amount_cents'),
            func.avg(Invoice.amount_cents).label('avg_amount_cents')
        ).where(
            and_(
                Invoice.tenant == tenant,
                Invoice.created_at >= current_month_start
            )
        )
        
        result = await db.execute(monthly_invoices_query)
        monthly_stats = result.first()
        
        # Adjustment statistics
        adjustments_query = select(
            func.count(InvoiceAdjustment.id).label('adjustment_count'),
            func.sum(InvoiceAdjustment.delta_cents).label('total_adjustment_cents')
        ).join(Invoice).where(
            and_(
                Invoice.tenant == tenant,
                InvoiceAdjustment.created_at >= current_month_start
            )
        )
        
        result = await db.execute(adjustments_query)
        adjustment_stats = result.first()
        
        # Status breakdown
        status_query = select(
            Invoice.status,
            func.count(Invoice.id).label('count'),
            func.sum(Invoice.amount_cents).label('amount_cents')
        ).where(Invoice.tenant == tenant).group_by(Invoice.status)
        
        result = await db.execute(status_query)
        status_breakdown = {row.status: {'count': row.count, 'amount_cents': row.amount_cents} 
                          for row in result}
        
        # Compile comprehensive report
        report = {
            'tenant': tenant,
            'report_date': datetime.utcnow().isoformat(),
            'reporting_period': 'current_month',
            'current_billing_cycle': {
                'invoices_generated': billing_results.get('invoices_generated', 0),
                'total_amount_cents': billing_results.get('total_amount_cents', 0),
                'adjustments_processed': billing_results.get('adjustments_processed', 0),
                'revenue_impact_cents': billing_results.get('total_revenue_impact_cents', 0)
            },
            'monthly_statistics': {
                'total_invoices': monthly_stats.invoice_count or 0,
                'total_revenue_cents': monthly_stats.total_amount_cents or 0,
                'average_invoice_cents': monthly_stats.avg_amount_cents or 0,
                'total_adjustments': adjustment_stats.adjustment_count or 0,
                'total_adjustment_amount_cents': adjustment_stats.total_adjustment_cents or 0
            },
            'invoice_status_breakdown': status_breakdown,
            'financial_metrics': {
                'gross_revenue': (monthly_stats.total_amount_cents or 0) / 100,
                'net_adjustments': (adjustment_stats.total_adjustment_cents or 0) / 100,
                'net_revenue': ((monthly_stats.total_amount_cents or 0) + (adjustment_stats.total_adjustment_cents or 0)) / 100,
                'adjustment_rate': (adjustment_stats.adjustment_count or 0) / (monthly_stats.invoice_count or 1),
                'average_invoice_value': (monthly_stats.avg_amount_cents or 0) / 100
            }
        }
        
        logger.info(f"Billing report generated: ${report['financial_metrics']['net_revenue']:.2f} net revenue, "
                   f"{report['monthly_statistics']['total_invoices']} invoices this month")
        
        return report


# ==== HELPER FUNCTIONS ==== #


async def _generate_invoice_number(db: AsyncSession, tenant: str) -> str:
    """Generate unique invoice number for tenant."""
    # Get current year and month
    now = datetime.utcnow()
    year_month = now.strftime("%Y%m")
    
    # Get next sequence number for this month
    query = text("""
        SELECT COALESCE(MAX(CAST(SUBSTRING(invoice_number FROM '[0-9]+$') AS INTEGER)), 0) + 1
        FROM invoices 
        WHERE tenant = :tenant 
        AND invoice_number LIKE :pattern
    """)
    
    pattern = f"{tenant.upper()}-{year_month}-%"
    result = await db.execute(query, {"tenant": tenant, "pattern": pattern})
    next_seq = result.scalar()
    
    return f"{tenant.upper()}-{year_month}-{next_seq:04d}"


# ==== MAIN FLOW ==== #


@flow(name="billing-management-pipeline", log_prints=True)
async def billing_management_pipeline(
    tenant: str = "demo-3pl",
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Comprehensive billing management pipeline.
    
    This flow implements end-to-end billing operations including:
    1. Identification of billable orders
    2. Automated invoice generation
    3. Invoice accuracy validation
    4. Billing adjustments processing
    5. Financial reporting and analytics
    
    Args:
        tenant: Tenant to process billing for
        lookback_hours: Time window for identifying billable orders
        
    Returns:
        Dict with complete billing pipeline results
    """
    logger = get_run_logger()
    logger.info(f"Starting billing management pipeline for tenant {tenant}")
    
    # Step 1: Identify orders ready for billing
    billable_analysis = await identify_billable_orders(tenant, lookback_hours)
    
    # Step 2: Generate invoices for billable orders
    invoice_generation = await generate_invoices(
        billable_analysis['billable_orders'], 
        tenant
    )
    
    # Step 3: Validate invoice accuracy
    validation_results = await validate_invoice_accuracy(
        invoice_generation['generated_invoices'], 
        tenant
    )
    
    # Step 4: Process billing adjustments
    adjustment_results = await process_billing_adjustments(
        validation_results, 
        tenant
    )
    
    # Step 5: Generate comprehensive billing report
    billing_report = await generate_billing_report(
        {
            **invoice_generation,
            **adjustment_results
        },
        tenant
    )
    
    # Compile comprehensive results
    pipeline_results = {
        'tenant': tenant,
        'execution_time': datetime.utcnow().isoformat(),
        'billable_analysis': billable_analysis,
        'invoice_generation': invoice_generation,
        'validation_results': validation_results,
        'adjustment_processing': adjustment_results,
        'billing_report': billing_report,
        'summary': {
            'billable_orders_identified': billable_analysis['summary']['billable_count'],
            'invoices_generated': invoice_generation['invoices_generated'],
            'total_billed_amount': invoice_generation['total_amount_cents'] / 100,
            'validation_success_rate': validation_results.get('validation_success_rate', 0),
            'adjustments_processed': adjustment_results['adjustments_processed'],
            'net_revenue_impact': adjustment_results.get('net_revenue_adjustment', 0)
        }
    }
    
    logger.info(f"Billing management pipeline completed: "
               f"{pipeline_results['summary']['invoices_generated']} invoices generated, "
               f"${pipeline_results['summary']['total_billed_amount']:.2f} billed, "
               f"{pipeline_results['summary']['validation_success_rate']:.1%} validation success rate")
    
    return pipeline_results


# ==== DEPLOYMENT HELPER ==== #

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Billing Management Pipeline")
    parser.add_argument("--tenant", default="demo-3pl", help="Tenant to process")
    parser.add_argument("--hours", type=int, default=24, help="Lookback hours for billable orders")
    parser.add_argument("--run", action="store_true", help="Run the flow immediately")
    parser.add_argument("--serve", action="store_true", help="Serve the flow for scheduling")
    
    args = parser.parse_args()
    
    if args.run:
        # Run the flow immediately
        asyncio.run(billing_management_pipeline(args.tenant, args.hours))
    elif args.serve:
        # Serve the flow for scheduling
        print(f"Serving billing management pipeline for tenant {args.tenant}")
        print("This would set up a scheduled deployment in a real environment")
    else:
        print("Use --run to execute immediately or --serve to set up scheduling")
