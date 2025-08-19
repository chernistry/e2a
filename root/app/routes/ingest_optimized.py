"""
Optimized ingestion endpoints for high-throughput event processing.

This module implements advanced patterns for handling large volumes of events:
- Batch processing with configurable batch sizes
- Asynchronous background processing with queues
- Database connection pooling and bulk operations
- Circuit breaker pattern for resilience
- Rate limiting and backpressure handling
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.storage.db import get_db_session
from app.storage.models import OrderEvent, ExceptionRecord
from app.schemas.ingest import IngestResponse, BatchIngestRequest, BatchIngestResponse
from app.middleware.tenancy import get_tenant_id
from app.observability.tracing import get_tracer
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest/v2", tags=["ingestion-optimized"])

# Use module-specific tracer
tracer = get_tracer(__name__)

# Configuration
BATCH_SIZE = 100
MAX_CONCURRENT_BATCHES = 10
PROCESSING_TIMEOUT = 30.0

# Global components
circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
rate_limiter = RateLimiter(max_requests=1000, window_seconds=60)

# Background processing queue
processing_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
background_processors: List[asyncio.Task] = []


class BatchProcessor:
    """High-performance batch processor for events."""
    
    def __init__(self, batch_size: int = BATCH_SIZE):
        self.batch_size = batch_size
        self.pending_events: List[Dict[str, Any]] = []
        self.pending_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict[str, Any], tenant: str) -> bool:
        """Add event to pending batch. Returns True if batch is ready for processing."""
        async with self.pending_lock:
            self.pending_events.append({**event_data, "_tenant": tenant})
            return len(self.pending_events) >= self.batch_size
    
    async def flush_batch(self, db: AsyncSession) -> List[str]:
        """Process all pending events in a single batch."""
        async with self.pending_lock:
            if not self.pending_events:
                return []
            
            events_to_process = self.pending_events.copy()
            self.pending_events.clear()
        
        return await self._process_batch(events_to_process, db)
    
    async def _process_batch(self, events: List[Dict[str, Any]], db: AsyncSession) -> List[str]:
        """Process a batch of events with optimized database operations."""
        with tracer.start_as_current_span("batch_process_events") as span:
            span.set_attribute("batch_size", len(events))
            
            try:
                # 1. Prepare batch data for bulk insert
                order_events_data = []
                exceptions_data = []
                processed_event_ids = []
                
                for event_data in events:
                    tenant = event_data.pop("_tenant")
                    event_id = event_data.get("event_id")
                    
                    # Validate and prepare order event
                    order_event_data = await self._prepare_order_event(event_data, tenant)
                    if order_event_data:
                        order_events_data.append(order_event_data)
                        processed_event_ids.append(event_id)
                    
                    # Analyze for exceptions (fast, in-memory analysis)
                    exception_data = await self._analyze_for_exceptions(event_data, tenant)
                    if exception_data:
                        exceptions_data.extend(exception_data)
                
                # 2. Bulk database operations
                await self._bulk_insert_events(db, order_events_data)
                if exceptions_data:
                    await self._bulk_insert_exceptions(db, exceptions_data)
                
                # 3. Single commit for entire batch
                await db.commit()
                
                # 4. Queue background processing (SLA evaluation, AI analysis)
                await self._queue_background_processing(events)
                
                span.set_attribute("events_processed", len(processed_event_ids))
                return processed_event_ids
                
            except Exception as e:
                await db.rollback()
                span.record_exception(e)
                logger.error(f"Batch processing failed: {e}")
                raise
    
    async def _prepare_order_event(self, event_data: Dict[str, Any], tenant: str) -> Optional[Dict[str, Any]]:
        """Prepare order event data for bulk insert."""
        try:
            event_id = event_data.get("event_id")
            event_type = event_data.get("event_type")
            order_id = event_data.get("order_id")
            occurred_at_str = event_data.get("occurred_at")
            
            if not all([event_id, event_type, order_id, occurred_at_str]):
                return None
            
            # Parse timestamp
            occurred_at = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
            if occurred_at.tzinfo is not None:
                occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)
            
            return {
                "event_id": event_id,
                "tenant": tenant,
                "order_id": order_id,
                "event_type": event_type,
                "source": event_data.get("source", "shopify"),
                "occurred_at": occurred_at,
                "correlation_id": event_data.get("correlation_id"),
                "payload": event_data,
                "created_at": datetime.utcnow()
            }
        except Exception as e:
            logger.warning(f"Failed to prepare order event: {e}")
            return None
    
    async def _analyze_for_exceptions(self, event_data: Dict[str, Any], tenant: str) -> List[Dict[str, Any]]:
        """Fast in-memory analysis for exceptions."""
        exceptions = []
        
        # Quick pattern-based analysis (no AI, no external calls)
        order_data = event_data.get("data", {}).get("order", {})
        if not order_data:
            return exceptions
        
        order_id = event_data.get("order_id")
        
        # Check for common problems
        if order_data.get("financial_status") == "pending":
            exceptions.append({
                "tenant": tenant,
                "order_id": order_id,
                "reason_code": "PAYMENT_FAILED",
                "severity": "HIGH",
                "status": "OPEN",
                "ops_note": "[Batch] Payment pending detected",
                "client_note": "We're processing your payment",
                "created_at": datetime.utcnow(),
                "context_data": {"financial_status": "pending"}
            })
        
        if order_data.get("fulfillment_status") == "delayed":
            exceptions.append({
                "tenant": tenant,
                "order_id": order_id,
                "reason_code": "DELIVERY_DELAY",
                "severity": "CRITICAL",
                "status": "OPEN",
                "ops_note": "[Batch] Delivery delay detected",
                "client_note": "Your order is delayed",
                "created_at": datetime.utcnow(),
                "context_data": {"fulfillment_status": "delayed"}
            })
        
        return exceptions
    
    async def _bulk_insert_events(self, db: AsyncSession, events_data: List[Dict[str, Any]]):
        """Bulk insert order events using PostgreSQL COPY or bulk insert."""
        if not events_data:
            return
        
        # Use PostgreSQL's INSERT ... ON CONFLICT for idempotency
        stmt = insert(OrderEvent).values(events_data)
        stmt = stmt.on_conflict_do_nothing(index_elements=['tenant', 'source', 'event_id'])
        await db.execute(stmt)
    
    async def _bulk_insert_exceptions(self, db: AsyncSession, exceptions_data: List[Dict[str, Any]]):
        """Bulk insert exceptions."""
        if not exceptions_data:
            return
        
        stmt = insert(ExceptionRecord).values(exceptions_data)
        await db.execute(stmt)
    
    async def _queue_background_processing(self, events: List[Dict[str, Any]]):
        """Queue events for background processing (SLA, AI analysis)."""
        for event_data in events:
            try:
                await processing_queue.put_nowait({
                    "type": "sla_evaluation",
                    "data": event_data,
                    "timestamp": datetime.utcnow()
                })
            except asyncio.QueueFull:
                logger.warning("Background processing queue is full, skipping SLA evaluation")


# Global batch processor instance
batch_processor = BatchProcessor()


@router.post("/events/batch", response_model=BatchIngestResponse)
async def ingest_events_batch(
    batch_request: BatchIngestRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session)
) -> BatchIngestResponse:
    """
    High-performance batch event ingestion.
    
    Optimized for processing large volumes of events with:
    - Bulk database operations
    - Asynchronous background processing
    - Circuit breaker protection
    - Rate limiting
    """
    tenant = get_tenant_id(request)
    
    # Rate limiting
    if not await rate_limiter.allow_request(f"batch_ingest_{tenant}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    with tracer.start_as_current_span("ingest_events_batch") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("batch_size", len(batch_request.events))
        
        try:
            # Circuit breaker protection
            async with circuit_breaker:
                processed_ids = await batch_processor._process_batch(
                    [{**event.dict(), "_tenant": tenant} for event in batch_request.events],
                    db
                )
                
                return BatchIngestResponse(
                    processed_count=len(processed_ids),
                    event_ids=processed_ids,
                    status="success",
                    message=f"Processed {len(processed_ids)} events"
                )
                
        except Exception as e:
            span.record_exception(e)
            logger.error(f"Batch ingestion failed: {e}")
            raise HTTPException(status_code=500, detail="Batch processing failed")


@router.post("/events/stream", response_model=IngestResponse)
async def ingest_event_stream(
    event_data: Dict[str, Any],
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session)
) -> IngestResponse:
    """
    Streaming event ingestion with automatic batching.
    
    Events are automatically batched for optimal performance.
    When batch is full, it's processed immediately.
    """
    tenant = get_tenant_id(request)
    
    # Rate limiting per tenant
    if not await rate_limiter.allow_request(f"stream_ingest_{tenant}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    with tracer.start_as_current_span("ingest_event_stream") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("event_type", event_data.get("event_type", "unknown"))
        
        try:
            # Add to batch processor
            batch_ready = await batch_processor.add_event(event_data, tenant)
            
            # If batch is ready, process it immediately
            if batch_ready:
                background_tasks.add_task(process_ready_batch, db)
            
            return IngestResponse(
                event_id=event_data.get("event_id"),
                status="queued",
                message="Event queued for batch processing"
            )
            
        except Exception as e:
            span.record_exception(e)
            logger.error(f"Stream ingestion failed: {e}")
            raise HTTPException(status_code=500, detail="Stream processing failed")


async def process_ready_batch(db: AsyncSession):
    """Background task to process ready batches."""
    try:
        processed_ids = await batch_processor.flush_batch(db)
        logger.info(f"Processed batch of {len(processed_ids)} events")
    except Exception as e:
        logger.error(f"Background batch processing failed: {e}")


async def background_processor():
    """Background worker for SLA evaluation and AI analysis."""
    while True:
        try:
            # Get task from queue with timeout
            task = await asyncio.wait_for(processing_queue.get(), timeout=1.0)
            
            if task["type"] == "sla_evaluation":
                await process_sla_evaluation(task["data"])
            
            processing_queue.task_done()
            
        except asyncio.TimeoutError:
            # No tasks in queue, continue
            continue
        except Exception as e:
            logger.error(f"Background processing error: {e}")


async def process_sla_evaluation(event_data: Dict[str, Any]):
    """Process SLA evaluation in background."""
    try:
        # Import here to avoid circular imports
        from app.services.sla_engine import evaluate_sla
        
        # Get fresh DB session for background processing
        async with get_db_session() as db:
            await evaluate_sla(
                order_id=event_data.get("order_id"),
                event_type=event_data.get("event_type"),
                occurred_at=datetime.fromisoformat(event_data.get("occurred_at").replace('Z', '+00:00')),
                tenant=event_data.get("_tenant"),
                db=db,
                event_data=event_data
            )
    except Exception as e:
        logger.error(f"SLA evaluation failed: {e}")


@router.get("/stats/performance")
async def get_performance_stats():
    """Get performance statistics for the optimized ingestion."""
    return {
        "batch_processor": {
            "pending_events": len(batch_processor.pending_events),
            "batch_size": batch_processor.batch_size
        },
        "background_queue": {
            "queue_size": processing_queue.qsize(),
            "max_size": processing_queue.maxsize
        },
        "circuit_breaker": {
            "state": circuit_breaker.state.name,
            "failure_count": circuit_breaker.failure_count
        },
        "rate_limiter": {
            "active": True
        }
    }


# Startup and shutdown handlers
async def start_background_processors():
    """Start background processing workers."""
    global background_processors
    
    for i in range(MAX_CONCURRENT_BATCHES):
        task = asyncio.create_task(background_processor())
        background_processors.append(task)
    
    logger.info(f"Started {len(background_processors)} background processors")


async def stop_background_processors():
    """Stop background processing workers."""
    global background_processors
    
    for task in background_processors:
        task.cancel()
    
    await asyncio.gather(*background_processors, return_exceptions=True)
    background_processors.clear()
    
    logger.info("Stopped background processors")
