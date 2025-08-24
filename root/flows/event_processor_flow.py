# ==== EVENT PROCESSOR FLOW ==== #

"""
Consolidated event processing flow for Octup E²A.

This flow combines order analysis, exception detection, and AI processing
into a single, efficient pipeline triggered by webhook events.
Replaces the fragmented approach of separate flows with Prefect-native
retry mechanisms and circuit breaker patterns.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from prefect import flow, task, get_run_logger
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.storage.db import get_session
from app.storage.models import OrderEvent, ExceptionRecord
from app.services.order_analyzer import get_order_analyzer
from app.services.ai_exception_analyst import analyze_exception_or_fallback
from app.services.sla_engine import evaluate_sla


@task(retries=3, retry_delay_seconds=300)
async def analyze_order_events(
    tenant: str = "demo-3pl",
    lookback_hours: int = 1
) -> Dict[str, Any]:
    """
    Analyze recent order events for problems and exceptions.
    
    Args:
        tenant: Tenant identifier
        lookback_hours: Hours to look back for unprocessed events
        
    Returns:
        Analysis results with counts and metrics
    """
    logger = get_run_logger()
    logger.info(f"Analyzing order events for tenant {tenant}")
    
    async with get_session() as db:
        # Find recent order_created events that need analysis
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        query = select(OrderEvent).where(
            and_(
                OrderEvent.tenant == tenant,
                OrderEvent.event_type == "order_created",
                OrderEvent.created_at >= cutoff_time
            )
        ).order_by(OrderEvent.created_at.desc()).limit(100)
        
        result = await db.execute(query)
        events = result.scalars().all()
        
        analyzer = get_order_analyzer()
        processed_count = 0
        exceptions_created = 0
        
        for event in events:
            try:
                # Check if already processed (has exceptions)
                existing_exceptions = await db.execute(
                    select(ExceptionRecord).where(
                        and_(
                            ExceptionRecord.tenant == tenant,
                            ExceptionRecord.order_id == event.order_id,
                            ExceptionRecord.correlation_id == event.correlation_id
                        )
                    )
                )
                
                if existing_exceptions.scalars().first():
                    continue  # Already processed
                
                # Analyze order for problems
                problems = await analyzer.analyze_order(event.payload)
                
                # Create exceptions for detected problems
                for problem in problems:
                    exception = ExceptionRecord(
                        tenant=tenant,
                        order_id=event.order_id,
                        reason_code=problem["reason_code"],
                        status="OPEN",
                        severity=problem["severity"],
                        correlation_id=event.correlation_id,
                        max_resolution_attempts=3,
                        context_data=problem.get("context", {}),
                        ops_note=f"Auto-detected: {problem['description']}"
                    )
                    
                    db.add(exception)
                    await db.flush()
                    
                    # Trigger AI analysis asynchronously
                    await analyze_exception_or_fallback(db, exception)
                    exceptions_created += 1
                
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Failed to process event {event.event_id}: {e}")
                continue
        
        await db.commit()
        
        return {
            "events_processed": processed_count,
            "exceptions_created": exceptions_created,
            "total_events_found": len(events)
        }


@task(retries=3, retry_delay_seconds=300)
async def process_sla_evaluations(
    tenant: str = "demo-3pl",
    lookback_hours: int = 1
) -> Dict[str, Any]:
    """
    Process SLA evaluations for recent events.
    
    Args:
        tenant: Tenant identifier
        lookback_hours: Hours to look back for events
        
    Returns:
        SLA evaluation results
    """
    logger = get_run_logger()
    logger.info(f"Processing SLA evaluations for tenant {tenant}")
    
    async with get_session() as db:
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Find SLA-relevant events
        sla_event_types = [
            "order_created", "fulfillment_created", 
            "package_shipped", "delivered"
        ]
        
        query = select(OrderEvent).where(
            and_(
                OrderEvent.tenant == tenant,
                OrderEvent.event_type.in_(sla_event_types),
                OrderEvent.created_at >= cutoff_time
            )
        ).order_by(OrderEvent.created_at.desc()).limit(200)
        
        result = await db.execute(query)
        events = result.scalars().all()
        
        sla_breaches = 0
        processed_orders = set()
        
        for event in events:
            if event.order_id in processed_orders:
                continue
                
            try:
                # Evaluate SLA for this order
                await evaluate_sla(
                    db=db,
                    tenant=tenant,
                    order_id=event.order_id,
                    correlation_id=event.correlation_id
                )
                
                processed_orders.add(event.order_id)
                
            except Exception as e:
                logger.error(f"SLA evaluation failed for order {event.order_id}: {e}")
                continue
        
        # Count recent SLA breaches
        breach_query = select(func.count(ExceptionRecord.id)).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.reason_code.like("SLA_%"),
                ExceptionRecord.created_at >= cutoff_time
            )
        )
        
        breach_result = await db.execute(breach_query)
        sla_breaches = breach_result.scalar() or 0
        
        return {
            "orders_evaluated": len(processed_orders),
            "sla_breaches_detected": sla_breaches,
            "total_events_processed": len(events)
        }


@task(retries=2, retry_delay_seconds=180)
async def process_ai_analysis_queue(
    tenant: str = "demo-3pl",
    batch_size: int = 20
) -> Dict[str, Any]:
    """
    Process pending AI analysis for exceptions.
    
    Args:
        tenant: Tenant identifier
        batch_size: Number of exceptions to process in batch
        
    Returns:
        AI processing results
    """
    logger = get_run_logger()
    logger.info(f"Processing AI analysis queue for tenant {tenant}")
    
    async with get_session() as db:
        # Find exceptions needing AI analysis
        query = select(ExceptionRecord).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.status == "OPEN",
                ExceptionRecord.ai_label.is_(None)
            )
        ).order_by(ExceptionRecord.created_at.desc()).limit(batch_size)
        
        result = await db.execute(query)
        exceptions = result.scalars().all()
        
        processed_count = 0
        success_count = 0
        
        for exception in exceptions:
            try:
                # AI analysis with circuit breaker
                await analyze_exception_or_fallback(db, exception)
                success_count += 1
                processed_count += 1
                
            except Exception as e:
                logger.error(f"AI analysis failed for exception {exception.id}: {e}")
                processed_count += 1
                continue
        
        await db.commit()
        
        return {
            "exceptions_processed": processed_count,
            "ai_analysis_success": success_count,
            "success_rate": success_count / processed_count if processed_count > 0 else 0
        }


@flow(name="event-processor")
async def event_processor_flow(
    tenant: str = "demo-3pl",
    lookback_hours: int = 1,
    enable_ai_processing: bool = True
) -> Dict[str, Any]:
    """
    Main event processing flow combining order analysis, SLA evaluation, and AI processing.
    
    This flow replaces the fragmented approach of separate exception management,
    data enrichment, and orchestration flows with a single, efficient pipeline.
    
    Args:
        tenant: Tenant identifier for processing
        lookback_hours: Hours to look back for unprocessed events
        enable_ai_processing: Whether to enable AI analysis processing
        
    Returns:
        Comprehensive processing results
    """
    logger = get_run_logger()
    logger.info(f"Starting event processor flow for tenant {tenant}")
    
    # Phase 1: Order Analysis and Exception Detection
    order_analysis = await analyze_order_events(tenant, lookback_hours)
    
    # Phase 2: SLA Evaluation
    sla_evaluation = await process_sla_evaluations(tenant, lookback_hours)
    
    # Phase 3: AI Analysis (if enabled)
    ai_processing = {}
    if enable_ai_processing:
        ai_processing = await process_ai_analysis_queue(tenant)
    
    # Compile results
    results = {
        "tenant": tenant,
        "processing_timestamp": datetime.utcnow().isoformat(),
        "order_analysis": order_analysis,
        "sla_evaluation": sla_evaluation,
        "ai_processing": ai_processing,
        "summary": {
            "total_events_processed": (
                order_analysis.get("events_processed", 0) + 
                sla_evaluation.get("orders_evaluated", 0)
            ),
            "exceptions_created": order_analysis.get("exceptions_created", 0),
            "sla_breaches": sla_evaluation.get("sla_breaches_detected", 0),
            "ai_success_rate": ai_processing.get("success_rate", 0)
        }
    }
    
    logger.info(f"Event processor flow completed: {results['summary']}")
    return results


if __name__ == "__main__":
    # For testing
    import asyncio
    result = asyncio.run(event_processor_flow())
    print(f"Flow result: {result}")
