"""Dead Letter Queue operations for failed processing."""

import datetime as dt
import traceback
from typing import Dict, Any, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import DLQ
from app.observability.metrics import dlq_depth, dlq_items_total
from app.observability.tracing import get_tracer


tracer = get_tracer(__name__)


async def push_dlq(
    db: AsyncSession,
    tenant: str,
    payload: Dict[str, Any],
    error_class: str,
    error_message: str,
    correlation_id: str | None = None,
    source_operation: str | None = None,
    max_attempts: int = 3
) -> DLQ:
    """Add item to dead letter queue.
    
    Args:
        db: Database session
        tenant: Tenant identifier
        payload: Original payload that failed processing
        error_class: Exception class name
        error_message: Error message
        correlation_id: Request correlation ID
        source_operation: Operation that failed
        max_attempts: Maximum retry attempts
        
    Returns:
        Created DLQ record
    """
    with tracer.start_as_current_span("dlq_push") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("error_class", error_class)
        
        # Calculate next retry time (exponential backoff)
        next_retry = dt.datetime.utcnow() + dt.timedelta(minutes=5)
        
        dlq_item = DLQ(
            tenant=tenant,
            payload=payload,
            error_class=error_class,
            error_message=error_message,
            stack_trace=traceback.format_exc(),
            max_attempts=max_attempts,
            next_retry_at=next_retry,
            correlation_id=correlation_id,
            source_operation=source_operation
        )
        
        db.add(dlq_item)
        await db.flush()
        
        # Update metrics
        dlq_items_total.labels(tenant=tenant, error_type=error_class).inc()
        await _update_dlq_depth_metric(db, tenant)
        
        return dlq_item


async def fetch_batch(
    db: AsyncSession,
    limit: int = 10,
    tenant: str = "*"
) -> List[DLQ]:
    """Fetch batch of items from DLQ for retry.
    
    Args:
        db: Database session
        limit: Maximum number of items to fetch
        tenant: Tenant filter ("*" for all tenants)
        
    Returns:
        List of DLQ items ready for retry
    """
    with tracer.start_as_current_span("dlq_fetch_batch") as span:
        span.set_attribute("limit", limit)
        span.set_attribute("tenant", tenant)
        
        query = select(DLQ).where(
            DLQ.status == "PENDING",
            DLQ.attempts < DLQ.max_attempts,
            DLQ.next_retry_at <= dt.datetime.utcnow()
        ).order_by(DLQ.created_at).limit(limit)
        
        if tenant != "*":
            query = query.where(DLQ.tenant == tenant)
        
        result = await db.execute(query)
        items = result.scalars().all()
        
        span.set_attribute("items_found", len(items))
        return list(items)


async def mark_retry_attempt(
    db: AsyncSession,
    dlq_item: DLQ,
    success: bool = False,
    error_message: str | None = None
) -> None:
    """Mark retry attempt for DLQ item.
    
    Args:
        db: Database session
        dlq_item: DLQ item being retried
        success: Whether retry was successful
        error_message: Error message if retry failed
    """
    with tracer.start_as_current_span("dlq_mark_retry") as span:
        span.set_attribute("dlq_id", dlq_item.id)
        span.set_attribute("success", success)
        
        if success:
            dlq_item.status = "PROCESSED"
            dlq_item.processed_at = dt.datetime.utcnow()
        else:
            dlq_item.attempts += 1
            dlq_item.updated_at = dt.datetime.utcnow()
            
            if error_message:
                dlq_item.error_message = error_message
            
            # Check if max attempts reached
            if dlq_item.attempts >= dlq_item.max_attempts:
                dlq_item.status = "FAILED"
            else:
                # Calculate next retry with exponential backoff
                backoff_minutes = min(5 * (2 ** dlq_item.attempts), 60)
                dlq_item.next_retry_at = (
                    dt.datetime.utcnow() + dt.timedelta(minutes=backoff_minutes)
                )
        
        await db.flush()
        
        # Update metrics
        await _update_dlq_depth_metric(db, dlq_item.tenant)


async def get_dlq_stats(db: AsyncSession, tenant: str | None = None) -> Dict[str, Any]:
    """Get DLQ statistics.
    
    Args:
        db: Database session
        tenant: Optional tenant filter
        
    Returns:
        Dictionary with DLQ statistics
    """
    with tracer.start_as_current_span("dlq_get_stats") as span:
        if tenant:
            span.set_attribute("tenant", tenant)
        
        # Base query
        base_query = select(DLQ)
        if tenant:
            base_query = base_query.where(DLQ.tenant == tenant)
        
        # Count by status
        pending_query = base_query.where(DLQ.status == "PENDING")
        failed_query = base_query.where(DLQ.status == "FAILED")
        processed_query = base_query.where(DLQ.status == "PROCESSED")
        
        pending_count = len((await db.execute(pending_query)).scalars().all())
        failed_count = len((await db.execute(failed_query)).scalars().all())
        processed_count = len((await db.execute(processed_query)).scalars().all())
        
        return {
            "pending": pending_count,
            "failed": failed_count,
            "processed": processed_count,
            "total": pending_count + failed_count + processed_count
        }


async def cleanup_old_items(
    db: AsyncSession,
    days_old: int = 30,
    tenant: str | None = None
) -> int:
    """Clean up old processed/failed DLQ items.
    
    Args:
        db: Database session
        days_old: Age threshold in days
        tenant: Optional tenant filter
        
    Returns:
        Number of items cleaned up
    """
    with tracer.start_as_current_span("dlq_cleanup") as span:
        span.set_attribute("days_old", days_old)
        if tenant:
            span.set_attribute("tenant", tenant)
        
        cutoff_date = dt.datetime.utcnow() - dt.timedelta(days=days_old)
        
        query = select(DLQ).where(
            DLQ.status.in_(["PROCESSED", "FAILED"]),
            DLQ.updated_at < cutoff_date
        )
        
        if tenant:
            query = query.where(DLQ.tenant == tenant)
        
        items = (await db.execute(query)).scalars().all()
        
        for item in items:
            await db.delete(item)
        
        await db.flush()
        
        span.set_attribute("items_cleaned", len(items))
        return len(items)


async def _update_dlq_depth_metric(db: AsyncSession, tenant: str) -> None:
    """Update DLQ depth metric for tenant.
    
    Args:
        db: Database session
        tenant: Tenant identifier
    """
    query = select(DLQ).where(
        DLQ.tenant == tenant,
        DLQ.status == "PENDING"
    )
    
    count = len((await db.execute(query)).scalars().all())
    dlq_depth.labels(tenant=tenant).set(count)
