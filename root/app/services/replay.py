# ==== REPLAY SERVICE ==== #

"""
Replay service for processing Dead Letter Queue items.

This module provides comprehensive DLQ replay capabilities including
batch processing, rate limiting, and operation-specific replay logic
for failed operations across all tenant environments.
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.dlq import fetch_batch, mark_retry_attempt
from app.observability.tracing import get_tracer


tracer = get_tracer(__name__)


# ==== MAIN REPLAY FUNCTIONS ==== #


async def replay_dlq_batch(
    db: AsyncSession,
    limit: int = 10,
    tenant: str = "*"
) -> int:
    """
    Replay a batch of items from the Dead Letter Queue.
    
    Processes multiple DLQ items in batch mode with comprehensive
    error handling, success tracking, and database transaction
    management for reliable operation recovery.
    
    Args:
        db (AsyncSession): Database session for data access
        limit (int): Maximum number of items to replay
        tenant (str): Tenant filter ("*" for all tenants)
        
    Returns:
        int: Number of successfully replayed items
    """
    with tracer.start_as_current_span("replay_dlq_batch") as span:
        span.set_attribute("limit", limit)
        span.set_attribute("tenant", tenant)
        
        # Fetch items ready for retry
        items = await fetch_batch(db, limit, tenant)
        
        if not items:
            span.set_attribute("items_found", 0)
            return 0
        
        span.set_attribute("items_found", len(items))
        
        success_count = 0
        
        # Process each item
        for item in items:
            try:
                # Attempt to replay the item
                success = await _replay_single_item(db, item)
                
                if success:
                    await mark_retry_attempt(db, item, success=True)
                    success_count += 1
                else:
                    await mark_retry_attempt(
                        db, item, success=False, error_message="Replay processing failed"
                    )
                
            except Exception as e:
                # Mark as failed retry
                await mark_retry_attempt(
                    db, item, success=False, error_message=str(e)
                )
                
                span.set_attribute(f"item_{item.id}_error", str(e))
        
        # Commit all changes
        await db.commit()
        
        span.set_attribute("success_count", success_count)
        span.set_attribute("failure_count", len(items) - success_count)
        
        return success_count


async def replay_with_rate_limit(
    db: AsyncSession,
    limit: int = 10,
    tenant: str = "*",
    rate_limit_per_second: int = 5
) -> int:
    """
    Replay DLQ items with rate limiting.
    
    Implements controlled DLQ replay with configurable rate limiting
    to prevent system overload while maintaining operational
    recovery capabilities across all tenant environments.
    
    Args:
        db (AsyncSession): Database session for data access
        limit (int): Maximum number of items to replay
        tenant (str): Tenant filter for targeted replay
        rate_limit_per_second (int): Maximum items to process per second
        
    Returns:
        int: Number of successfully replayed items
    """
    with tracer.start_as_current_span("replay_with_rate_limit") as span:
        span.set_attribute("limit", limit)
        span.set_attribute("tenant", tenant)
        span.set_attribute("rate_limit", rate_limit_per_second)
        
        # Fetch items
        items = await fetch_batch(db, limit, tenant)
        
        if not items:
            return 0
        
        success_count = 0
        delay_between_items = 1.0 / rate_limit_per_second
        
        # Process items with rate limiting
        for i, item in enumerate(items):
            try:
                success = await _replay_single_item(db, item)
                
                if success:
                    await mark_retry_attempt(db, item, success=True)
                    success_count += 1
                else:
                    await mark_retry_attempt(
                        db, item, success=False, error_message="Replay failed"
                    )
                
                # Rate limiting delay (except for last item)
                if i < len(items) - 1:
                    await asyncio.sleep(delay_between_items)
                    
            except Exception as e:
                await mark_retry_attempt(
                    db, item, success=False, error_message=str(e)
                )
        
        await db.commit()
        
        span.set_attribute("success_count", success_count)
        return success_count


# ==== INDIVIDUAL ITEM REPLAY ==== #


async def _replay_single_item(db: AsyncSession, dlq_item) -> bool:
    """
    Replay a single DLQ item.
    
    Routes individual DLQ items to appropriate replay handlers
    based on source operation type with comprehensive error
    handling and observability integration.
    
    Args:
        db (AsyncSession): Database session for data access
        dlq_item: DLQ item to replay
        
    Returns:
        bool: True if replay was successful, False otherwise
    """
    with tracer.start_as_current_span("replay_single_item") as span:
        span.set_attribute("dlq_id", dlq_item.id)
        span.set_attribute("tenant", dlq_item.tenant)
        span.set_attribute("source_operation", dlq_item.source_operation or "unknown")
        
        try:
            # Determine the type of operation to replay
            if dlq_item.source_operation == "ingest_event":
                return await _replay_ingest_event(db, dlq_item)
            elif dlq_item.source_operation == "ai_analysis":
                return await _replay_ai_analysis(db, dlq_item)
            elif dlq_item.source_operation == "sla_evaluation":
                return await _replay_sla_evaluation(db, dlq_item)
            else:
                # Unknown operation type
                span.set_attribute("error", "Unknown operation type")
                return False
                
        except Exception as e:
            span.set_attribute("error", str(e))
            return False


# ==== OPERATION-SPECIFIC REPLAY HANDLERS ==== #


async def _replay_ingest_event(db: AsyncSession, dlq_item) -> bool:
    """
    Replay an ingest event.
    
    Reconstructs and reprocesses failed ingest events with
    comprehensive validation, event recreation, and SLA
    evaluation for complete operational recovery.
    
    Args:
        db (AsyncSession): Database session for data access
        dlq_item: DLQ item containing ingest event data
        
    Returns:
        bool: True if successful, False otherwise
    """
    with tracer.start_as_current_span("replay_ingest_event") as span:
        span.set_attribute("dlq_id", dlq_item.id)
        
        try:
            payload = dlq_item.payload
            
            # Validate payload structure
            required_fields = ["source", "event_type", "event_id", "order_id", "occurred_at"]
            if not all(field in payload for field in required_fields):
                span.set_attribute("error", "Invalid payload structure")
                return False
            
            # Re-process the event
            from app.storage.models import OrderEvent
            from app.services.sla_engine import evaluate_sla
            from datetime import datetime
            
            # Create order event record
            order_event = OrderEvent(
                tenant=dlq_item.tenant,
                source=payload["source"],
                event_type=payload["event_type"],
                event_id=payload["event_id"],
                order_id=payload["order_id"],
                occurred_at=datetime.fromisoformat(
                    payload["occurred_at"].replace('Z', '+00:00')
                ),
                payload=payload,
                correlation_id=dlq_item.correlation_id
            )
            
            db.add(order_event)
            await db.flush()
            
            # Evaluate SLA
            await evaluate_sla(
                db, 
                dlq_item.tenant, 
                payload["order_id"], 
                dlq_item.correlation_id
            )
            
            span.set_attribute("success", True)
            return True
            
        except Exception as e:
            span.set_attribute("error", str(e))
            return False


async def _replay_ai_analysis(db: AsyncSession, dlq_item) -> bool:
    """
    Replay an AI analysis operation.
    
    Re-executes failed AI analysis operations by retrieving
    exception records and triggering fresh AI analysis
    for complete operational recovery.
    
    Args:
        db (AsyncSession): Database session for data access
        dlq_item: DLQ item containing AI analysis data
        
    Returns:
        bool: True if successful, False otherwise
    """
    with tracer.start_as_current_span("replay_ai_analysis") as span:
        span.set_attribute("dlq_id", dlq_item.id)
        
        try:
            payload = dlq_item.payload
            
            # Get exception ID from payload
            exception_id = payload.get("exception_id")
            if not exception_id:
                span.set_attribute("error", "Missing exception_id in payload")
                return False
            
            # Get exception record
            from sqlalchemy import select
            from app.storage.models import ExceptionRecord
            
            query = select(ExceptionRecord).where(
                ExceptionRecord.id == exception_id,
                ExceptionRecord.tenant == dlq_item.tenant
            )
            
            result = await db.execute(query)
            exception = result.scalar_one_or_none()
            
            if not exception:
                span.set_attribute("error", "Exception not found")
                return False
            
            # Re-run AI analysis
            from app.services.ai_exception_analyst import analyze_exception_or_fallback
            await analyze_exception_or_fallback(db, exception)
            
            span.set_attribute("success", True)
            return True
            
        except Exception as e:
            span.set_attribute("error", str(e))
            return False


async def _replay_sla_evaluation(db: AsyncSession, dlq_item) -> bool:
    """
    Replay an SLA evaluation operation.
    
    Re-executes failed SLA evaluation operations by retrieving
    order information and triggering fresh SLA analysis
    for complete operational recovery.
    
    Args:
        db (AsyncSession): Database session for data access
        dlq_item: DLQ item containing SLA evaluation data
        
    Returns:
        bool: True if successful, False otherwise
    """
    with tracer.start_as_current_span("replay_sla_evaluation") as span:
        span.set_attribute("dlq_id", dlq_item.id)
        
        try:
            payload = dlq_item.payload
            
            # Get order information from payload
            order_id = payload.get("order_id")
            if not order_id:
                span.set_attribute("error", "Missing order_id in payload")
                return False
            
            # Re-run SLA evaluation
            from app.services.sla_engine import evaluate_sla
            
            await evaluate_sla(
                db,
                dlq_item.tenant,
                order_id,
                dlq_item.correlation_id
            )
            
            span.set_attribute("success", True)
            return True
            
        except Exception as e:
            span.set_attribute("error", str(e))
            return False
