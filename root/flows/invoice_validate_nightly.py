# ==== PREFECT NIGHTLY INVOICE VALIDATION FLOW ==== #

"""
Prefect flow for nightly invoice validation and adjustment creation in Octup E²A.

This module provides comprehensive nightly invoice validation with automated
adjustment creation, billing policy enforcement, and comprehensive observability
for accurate billing reconciliation and dispute prevention.
"""

import asyncio
import argparse
from typing import Dict, Any, List

from prefect import flow, task, get_run_logger
from prefect.deployments import run_deployment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import get_session, engine
from app.storage.models import Invoice, InvoiceAdjustment
from app.services.policy_loader import get_billing_config
from app.observability.metrics import (
    invoice_adjustments_total, 
    invoice_adjustment_amount_cents
)


# ==== TASK DEFINITIONS ==== #


@task
async def trigger_event_streaming(
    duration_minutes: int = 3, 
    eps: int = 5
) -> Dict[str, Any]:
    """
    Trigger event streaming to simulate real-world data flow.
    
    Simulates Shopify/WMS systems sending events during business hours
    to provide realistic data for invoice validation testing and development.
    
    Args:
        duration_minutes (int): How long to stream events in minutes
        eps (int): Events per second rate for simulation
        
    Returns:
        Dict[str, Any]: Streaming trigger result with execution metadata
    """
    logger = get_run_logger()
    logger.info(f"Triggering event streaming for {duration_minutes} minutes at {eps} EPS")
    
    try:
        # In a real deployment, this would trigger the event-streaming flow
        # For now, we'll import and run it directly
        from flows.event_streaming import event_streaming_flow
        
        # Run the streaming flow
        streaming_result = await event_streaming_flow(
            duration_minutes=duration_minutes,
            eps=eps,
            auto_stop=True
        )
        
        logger.info(f"Event streaming completed: {streaming_result.get('summary', 'No summary')}")
        return streaming_result
        
    except Exception as e:
        logger.error(f"Failed to trigger event streaming: {str(e)}")
        # Don't fail the main flow if streaming fails
        return {"status": "streaming_failed", "error": str(e)}


@task
async def wait_for_event_processing(wait_seconds: int = 30) -> Dict[str, Any]:
    """
    Wait for events to be processed by the system.
    
    Provides controlled delay to allow event processing
    completion before proceeding with invoice validation.
    
    Args:
        wait_seconds (int): How long to wait for processing completion
        
    Returns:
        Dict[str, Any]: Wait completion status and duration
    """
    logger = get_run_logger()
    logger.info(f"Waiting {wait_seconds} seconds for event processing...")
    
    await asyncio.sleep(wait_seconds)
    
    logger.info("Event processing wait completed")
    return {"status": "completed", "wait_seconds": wait_seconds}


@task
async def fetch_invoices_for_validation() -> List[Dict[str, Any]]:
    """
    Fetch invoices that need validation.
    
    Retrieves draft invoices from the database for
    comprehensive validation against billing policies.
    
    Returns:
        List[Dict[str, Any]]: List of invoice data dictionaries
    """
    logger = get_run_logger()
    
    async with get_session() as db:
        # Get invoices that haven't been validated recently
        query = select(Invoice).where(Invoice.status == "DRAFT")
        result = await db.execute(query)
        invoices = result.scalars().all()
        
        invoice_data = []
        for invoice in invoices:
            invoice_data.append({
                "id": invoice.id,
                "tenant": invoice.tenant,
                "order_id": invoice.order_id,
                "billable_ops": invoice.billable_ops,
                "amount_cents": invoice.amount_cents,
                "currency": invoice.currency
            })
        
        logger.info(f"Found {len(invoice_data)} invoices for validation")
        return invoice_data


@task
async def validate_single_invoice(invoice_data: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Validate a single invoice against billing rules.
    
    Performs comprehensive invoice validation by calculating
    expected amounts and comparing against actual amounts
    with detailed discrepancy analysis.
    
    Args:
        invoice_data (Dict[str, Any]): Invoice data dictionary
        
    Returns:
        Dict[str, Any] | None: Adjustment data if needed, None otherwise
    """
    logger = get_run_logger()
    
    # Get billing configuration for tenant
    billing_config = get_billing_config(invoice_data["tenant"])
    
    # Calculate expected amount
    expected_amount = _calculate_expected_amount(
        invoice_data["billable_ops"], 
        billing_config
    )
    
    # Check for discrepancy
    actual_amount = invoice_data["amount_cents"]
    delta = expected_amount - actual_amount
    
    if delta != 0:
        logger.info(
            f"Invoice {invoice_data['id']} discrepancy: "
            f"expected {expected_amount}¢, actual {actual_amount}¢, delta {delta}¢"
        )
        
        # Generate rationale
        rationale = _generate_adjustment_rationale(
            invoice_data, expected_amount, actual_amount, billing_config
        )
        
        return {
            "invoice_id": invoice_data["id"],
            "tenant": invoice_data["tenant"],
            "reason": "BILLING_DISCREPANCY",
            "delta_cents": delta,
            "rationale": rationale,
            "ai_generated": False,
            "ai_confidence": None
        }
    
    return None


@task
async def create_adjustments(adjustments: List[Dict[str, Any]]) -> int:
    """
    Create invoice adjustments in the database.
    
    Persists invoice adjustments with comprehensive
    metrics tracking and audit logging for operational
    transparency and compliance.
    
    Args:
        adjustments (List[Dict[str, Any]]): List of adjustment data
        
    Returns:
        int: Number of adjustments successfully created
    """
    logger = get_run_logger()
    
    if not adjustments:
        logger.info("No adjustments needed")
        return 0
    
    async with get_session() as db:
        created_count = 0
        
        for adj_data in adjustments:
            adjustment = InvoiceAdjustment(
                invoice_id=adj_data["invoice_id"],
                tenant=adj_data["tenant"],
                reason=adj_data["reason"],
                delta_cents=adj_data["delta_cents"],
                rationale=adj_data["rationale"],
                ai_generated=adj_data["ai_generated"],
                ai_confidence=adj_data["ai_confidence"],
                created_by="system"
            )
            
            db.add(adjustment)
            created_count += 1
            
            # Update metrics
            invoice_adjustments_total.labels(
                tenant=adj_data["tenant"],
                reason=adj_data["reason"]
            ).inc()
            
            invoice_adjustment_amount_cents.labels(
                tenant=adj_data["tenant"],
                reason=adj_data["reason"]
            ).observe(abs(adj_data["delta_cents"]))
        
        await db.commit()
        logger.info(f"Created {created_count} invoice adjustments")
        
        return created_count


# ==== UTILITY FUNCTIONS ==== #


def _calculate_expected_amount(billable_ops: Dict[str, Any], billing_config: Dict[str, Any]) -> int:
    """
    Calculate expected invoice amount based on operations and rates.
    
    Implements comprehensive billing calculation including
    core operations, storage fees, and special handling
    multipliers for accurate invoice validation.
    
    Args:
        billable_ops (Dict[str, Any]): Billable operations dictionary
        billing_config (Dict[str, Any]): Billing configuration with rates
        
    Returns:
        int: Expected amount in cents
    """
    total_cents = 0
    
    # Core operation fees
    total_cents += billable_ops.get("pick", 0) * billing_config.get("pick_fee_cents", 30)
    total_cents += billable_ops.get("pack", 0) * billing_config.get("pack_fee_cents", 20)
    total_cents += billable_ops.get("label", 0) * billing_config.get("label_fee_cents", 15)
    total_cents += billable_ops.get("kitting", 0) * billing_config.get("kitting_fee_cents", 50)
    
    # Storage fees (if applicable)
    storage_days = billable_ops.get("storage_days", 0)
    if storage_days > 0:
        storage_rate = billing_config.get("storage_fee_cents_per_day", 5)
        total_cents += storage_days * storage_rate
    
    # Apply minimum fee
    min_fee = billing_config.get("min_order_fee_cents", 50)
    total_cents = max(total_cents, min_fee)
    
    # Apply multipliers for special handling
    if billable_ops.get("rush", False):
        total_cents = int(total_cents * billing_config.get("rush_multiplier", 2.0))
    
    if billable_ops.get("oversized", False):
        total_cents = int(total_cents * billing_config.get("oversized_multiplier", 1.5))
    
    if billable_ops.get("hazmat", False):
        total_cents = int(total_cents * billing_config.get("hazmat_multiplier", 3.0))
    
    return total_cents


def _generate_adjustment_rationale(
    invoice_data: Dict[str, Any],
    expected_amount: int,
    actual_amount: int,
    billing_config: Dict[str, Any]
) -> str:
    """
    Generate human-readable rationale for invoice adjustment.
    
    Creates comprehensive adjustment explanations with
    detailed operation breakdowns and rate calculations
    for operational transparency and audit compliance.
    
    Args:
        invoice_data (Dict[str, Any]): Invoice data for context
        expected_amount (int): Expected amount in cents
        actual_amount (int): Actual amount in cents
        billing_config (Dict[str, Any]): Billing configuration
        
    Returns:
        str: Human-readable adjustment rationale
    """
    ops = invoice_data["billable_ops"]
    
    # Build operation breakdown
    breakdown = []
    if ops.get("pick", 0) > 0:
        rate = billing_config.get("pick_fee_cents", 30)
        breakdown.append(f"{ops['pick']} picks @ {rate}¢ = {ops['pick'] * rate}¢")
    
    if ops.get("pack", 0) > 0:
        rate = billing_config.get("pack_fee_cents", 20)
        breakdown.append(f"{ops['pack']} packs @ {rate}¢ = {ops['pack'] * rate}¢")
    
    if ops.get("label", 0) > 0:
        rate = billing_config.get("label_fee_cents", 15)
        breakdown.append(f"{ops['label']} labels @ {rate}¢ = {ops['label'] * rate}¢")
    
    breakdown_text = "; ".join(breakdown)
    
    rationale = (
        f"Billing discrepancy detected for order {invoice_data['order_id']}. "
        f"Expected: {expected_amount}¢ ({breakdown_text}), "
        f"Actual: {actual_amount}¢, "
        f"Difference: {expected_amount - actual_amount}¢. "
        f"Adjustment recommended based on current tariff rates."
    )
    
    return rationale


# ==== MAIN INVOICE VALIDATION FLOW ==== #


@flow(name="invoice-validate-nightly", log_prints=True)
async def invoice_validate_nightly(
    with_event_streaming: bool = True,
    streaming_duration_minutes: int = 3,
    streaming_eps: int = 5
) -> Dict[str, Any]:
    """
    Main flow for nightly invoice validation.
    
    This flow simulates a real production scenario where:
    1. External systems (Shopify/WMS) send events during business hours
    2. Invoice validation runs nightly to process accumulated data
    3. The validation waits for events to be processed, then validates invoices
    
    Args:
        with_event_streaming (bool): Whether to trigger event streaming
        streaming_duration_minutes (int): How long to stream events
        streaming_eps (int): Events per second for streaming
        
    Returns:
        Dict[str, Any]: Flow execution summary with detailed results
    """
    logger = get_run_logger()
    logger.info("Starting nightly invoice validation with event streaming simulation")
    
    flow_start_time = asyncio.get_event_loop().time()
    
    try:
        streaming_result = None
        
        # Step 1: Trigger event streaming (simulates Shopify/WMS activity)
        if with_event_streaming:
            logger.info("🎭 Simulating external system activity (Shopify/WMS events)...")
            streaming_result = await trigger_event_streaming(
                duration_minutes=streaming_duration_minutes,
                eps=streaming_eps
            )
            
            # Step 2: Wait for events to be processed by our system
            logger.info("⏳ Waiting for events to be processed...")
            await wait_for_event_processing(wait_seconds=30)
        
        # Step 3: Fetch invoices that need validation
        logger.info("📋 Fetching invoices for validation...")
        invoices = await fetch_invoices_for_validation()
        
        if not invoices:
            logger.info("No invoices found for validation")
            return {
                "status": "success",
                "adjustments_created": 0,
                "streaming": streaming_result,
                "summary": "No invoices to validate"
            }
        
        # Step 4: Validate each invoice
        logger.info(f"🔍 Validating {len(invoices)} invoices...")
        validation_tasks = []
        for invoice in invoices:
            validation_tasks.append(validate_single_invoice(invoice))
        
        # Wait for all validations to complete
        adjustment_results = await asyncio.gather(*validation_tasks)
        
        # Filter out None results
        adjustments = [adj for adj in adjustment_results if adj is not None]
        
        # Step 5: Create adjustments
        created_count = 0
        if adjustments:
            created_count = await create_adjustments(adjustments)
            logger.info(f"✅ Invoice validation completed. Created {created_count} adjustments.")
        else:
            logger.info("✅ Invoice validation completed. No adjustments needed.")
        
        flow_duration = asyncio.get_event_loop().time() - flow_start_time
        
        return {
            "status": "success",
            "invoices_processed": len(invoices),
            "adjustments_created": created_count,
            "streaming": streaming_result,
            "flow_duration_seconds": flow_duration,
            "summary": f"Processed {len(invoices)} invoices, created {created_count} adjustments"
        }
    
    except Exception as e:
        logger.error(f"Invoice validation failed: {str(e)}")
        raise


# ==== COMMAND LINE INTERFACE ==== #


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Invoice validation flow")
    parser.add_argument("--run", action="store_true", help="Run flow locally")
    parser.add_argument("--serve", action="store_true", help="Serve flow locally")
    parser.add_argument("--no-streaming", action="store_true", help="Skip event streaming")
    parser.add_argument("--duration", type=int, default=3, help="Streaming duration (minutes)")
    parser.add_argument("--eps", type=int, default=5, help="Events per second")
    
    args = parser.parse_args()
    
    if args.serve:
        print("Serving invoice validation flow locally...")
        # For local Prefect server, we use serve() method
        invoice_validate_nightly.serve(
            name="local-invoice-validation",
            tags=["invoice", "validation", "local"],
            interval=3600  # Check every hour for development
        )
        
    elif args.run:
        print("Running invoice validation flow locally...")
        result = asyncio.run(invoice_validate_nightly(
            with_event_streaming=not args.no_streaming,
            streaming_duration_minutes=args.duration,
            streaming_eps=args.eps
        ))
        print(f"Flow completed: {result}")
        
    else:
        print("Usage: python flows/invoice_validate_nightly.py [--run|--serve] [options]")
        print("  --run: Execute flow once locally")
        print("  --serve: Start flow server for scheduled execution")
        print("  --no-streaming: Skip event streaming simulation")
        print("  --duration N: Streaming duration in minutes (default: 3)")
        print("  --eps N: Events per second (default: 5)")
        print("")
        print("For deployment to local Prefect server, use: python deploy_prefect_local.py")
