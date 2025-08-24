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
    start_time = datetime.utcnow()
    correlation_id = f"batch_{int(start_time.timestamp())}"
    
    logger.info("Order analysis batch started", extra={
        "tenant": tenant,
        "lookback_hours": lookback_hours,
        "batch_id": correlation_id,
        "start_time": start_time.isoformat()
    })
    
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
        
        logger.info("Events discovered for analysis", extra={
            "tenant": tenant,
            "events_found": len(events),
            "batch_id": correlation_id,
            "cutoff_time": cutoff_time.isoformat()
        })
        
        analyzer = get_order_analyzer()
        processed_count = 0
        exceptions_created = 0
        skipped_count = 0
        error_count = 0
        
        for event in events:
            order_start_time = datetime.utcnow()
            
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
                    skipped_count += 1
                    logger.debug("Order already processed, skipping", extra={
                        "order_id": event.order_id,
                        "tenant": tenant,
                        "batch_id": correlation_id
                    })
                    continue  # Already processed
                
                # Analyze order for problems
                problems = await analyzer.analyze_order(event.payload)
                exceptions_created_for_order = 0
                
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
                    exceptions_created_for_order += 1
                
                processed_count += 1
                processing_time = (datetime.utcnow() - order_start_time).total_seconds()
                
                logger.info("Order processed successfully", extra={
                    "order_id": event.order_id,
                    "tenant": tenant,
                    "batch_id": correlation_id,
                    "event_type": event.event_type,
                    "problems_detected": len(problems),
                    "exceptions_created": exceptions_created_for_order,
                    "processing_time_seconds": round(processing_time, 3)
                })
                
            except Exception as e:
                error_count += 1
                processing_time = (datetime.utcnow() - order_start_time).total_seconds()
                
                logger.error("Failed to process order event", extra={
                    "order_id": event.order_id,
                    "event_id": event.event_id,
                    "tenant": tenant,
                    "batch_id": correlation_id,
                    "error": str(e),
                    "processing_time_seconds": round(processing_time, 3)
                })
                continue
        
        await db.commit()
        
        total_processing_time = (datetime.utcnow() - start_time).total_seconds()
        success_rate = processed_count / len(events) if len(events) > 0 else 0
        
        logger.info("Order analysis batch completed", extra={
            "tenant": tenant,
            "batch_id": correlation_id,
            "events_processed": processed_count,
            "events_skipped": skipped_count,
            "events_failed": error_count,
            "exceptions_created": exceptions_created,
            "success_rate": round(success_rate, 3),
            "processing_time_seconds": round(total_processing_time, 2),
            "avg_exceptions_per_order": round(exceptions_created / processed_count, 2) if processed_count > 0 else 0
        })
        
        return {
            "events_processed": processed_count,
            "exceptions_created": exceptions_created,
            "total_events_found": len(events),
            "events_skipped": skipped_count,
            "events_failed": error_count,
            "success_rate": success_rate,
            "processing_time_seconds": total_processing_time,
            "batch_id": correlation_id
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
    start_time = datetime.utcnow()
    correlation_id = f"sla_batch_{int(start_time.timestamp())}"
    
    logger.info("SLA evaluation batch started", extra={
        "tenant": tenant,
        "lookback_hours": lookback_hours,
        "batch_id": correlation_id,
        "start_time": start_time.isoformat()
    })
    
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
        
        logger.info("SLA events discovered for evaluation", extra={
            "tenant": tenant,
            "events_found": len(events),
            "event_types": sla_event_types,
            "batch_id": correlation_id,
            "cutoff_time": cutoff_time.isoformat()
        })
        
        sla_breaches_detected = 0
        processed_orders = set()
        evaluation_errors = 0
        
        for event in events:
            if event.order_id in processed_orders:
                continue
                
            order_start_time = datetime.utcnow()
            
            try:
                # Count existing SLA breaches for this order before evaluation
                pre_breach_query = select(func.count(ExceptionRecord.id)).where(
                    and_(
                        ExceptionRecord.tenant == tenant,
                        ExceptionRecord.order_id == event.order_id,
                        ExceptionRecord.reason_code.like("SLA_%")
                    )
                )
                pre_breach_count = await db.scalar(pre_breach_query) or 0
                
                # Evaluate SLA for this order
                await evaluate_sla(
                    db=db,
                    tenant=tenant,
                    order_id=event.order_id,
                    correlation_id=event.correlation_id
                )
                
                # Count SLA breaches after evaluation
                post_breach_query = select(func.count(ExceptionRecord.id)).where(
                    and_(
                        ExceptionRecord.tenant == tenant,
                        ExceptionRecord.order_id == event.order_id,
                        ExceptionRecord.reason_code.like("SLA_%")
                    )
                )
                post_breach_count = await db.scalar(post_breach_query) or 0
                
                new_breaches = post_breach_count - pre_breach_count
                sla_breaches_detected += new_breaches
                
                processing_time = (datetime.utcnow() - order_start_time).total_seconds()
                
                logger.info("SLA evaluation completed for order", extra={
                    "order_id": event.order_id,
                    "tenant": tenant,
                    "batch_id": correlation_id,
                    "event_type": event.event_type,
                    "sla_breaches_detected": new_breaches,
                    "total_sla_breaches": post_breach_count,
                    "processing_time_seconds": round(processing_time, 3)
                })
                
                processed_orders.add(event.order_id)
                
            except Exception as e:
                evaluation_errors += 1
                processing_time = (datetime.utcnow() - order_start_time).total_seconds()
                
                logger.error("SLA evaluation failed for order", extra={
                    "order_id": event.order_id,
                    "tenant": tenant,
                    "batch_id": correlation_id,
                    "error": str(e),
                    "processing_time_seconds": round(processing_time, 3)
                })
                continue
        
        # Count total recent SLA breaches for summary
        total_breach_query = select(func.count(ExceptionRecord.id)).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.reason_code.like("SLA_%"),
                ExceptionRecord.created_at >= cutoff_time
            )
        )
        
        total_breaches = await db.scalar(total_breach_query) or 0
        
        total_processing_time = (datetime.utcnow() - start_time).total_seconds()
        success_rate = len(processed_orders) / len(events) if len(events) > 0 else 0
        
        logger.info("SLA evaluation batch completed", extra={
            "tenant": tenant,
            "batch_id": correlation_id,
            "orders_evaluated": len(processed_orders),
            "sla_breaches_detected": sla_breaches_detected,
            "total_sla_breaches_in_period": total_breaches,
            "evaluation_errors": evaluation_errors,
            "success_rate": round(success_rate, 3),
            "processing_time_seconds": round(total_processing_time, 2),
            "avg_breaches_per_order": round(sla_breaches_detected / len(processed_orders), 2) if len(processed_orders) > 0 else 0
        })
        
        return {
            "orders_evaluated": len(processed_orders),
            "sla_breaches_detected": sla_breaches_detected,
            "total_sla_breaches_in_period": total_breaches,
            "evaluation_errors": evaluation_errors,
            "success_rate": success_rate,
            "processing_time_seconds": total_processing_time,
            "batch_id": correlation_id
        }
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
        
        logger.info(f"Found {len(exceptions)} exceptions requiring AI analysis")
        
        if not exceptions:
            logger.info("No exceptions require AI analysis at this time")
            return {
                "exceptions_processed": 0,
                "ai_analysis_success": 0,
                "success_rate": 0,
                "details": "No pending exceptions found"
            }
        
        processed_count = 0
        success_count = 0
        
        # Capture exception details before processing
        exception_details = [
            {"id": exc.id, "order_id": exc.order_id, "reason_code": exc.reason_code}
            for exc in exceptions[:5]  # Sample for logging
        ]
        
        for exception in exceptions:
            logger.info(f"Processing exception {exception.id} - Order: {exception.order_id}, Reason: {exception.reason_code}")
            logger.info(f"Exception details - Status: {exception.status}, Severity: {exception.severity}")
            
            try:
                # AI analysis with circuit breaker
                logger.info(f"Starting AI analysis for exception {exception.id}")
                await analyze_exception_or_fallback(db, exception)
                success_count += 1
                processed_count += 1
                logger.info(f"✓ Successfully analyzed exception {exception.id}")
                
            except Exception as e:
                logger.error(f"✗ AI analysis failed for exception {exception.id}: {e}")
                processed_count += 1
                continue
        
        await db.commit()
        
        logger.info(f"AI analysis batch complete - Total: {processed_count}, Success: {success_count}, Success Rate: {success_count/processed_count*100:.1f}%")
        
        return {
            "exceptions_processed": processed_count,
            "ai_analysis_success": success_count,
            "success_rate": success_count / processed_count if processed_count > 0 else 0,
            "batch_details": exception_details
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
    flow_start_time = datetime.utcnow()
    flow_correlation_id = f"event_processor_{int(flow_start_time.timestamp())}"
    
    logger.info("Event processor flow started", extra={
        "tenant": tenant,
        "lookback_hours": lookback_hours,
        "enable_ai_processing": enable_ai_processing,
        "flow_correlation_id": flow_correlation_id,
        "start_time": flow_start_time.isoformat()
    })
    
    # Phase 1: Order Analysis and Exception Detection
    phase1_start = datetime.utcnow()
    logger.info("Starting Phase 1: Order Analysis", extra={
        "tenant": tenant,
        "flow_correlation_id": flow_correlation_id,
        "phase": "order_analysis"
    })
    
    order_analysis = await analyze_order_events(tenant, lookback_hours)
    phase1_duration = (datetime.utcnow() - phase1_start).total_seconds()
    
    logger.info("Phase 1 completed", extra={
        "tenant": tenant,
        "flow_correlation_id": flow_correlation_id,
        "phase": "order_analysis",
        "duration_seconds": round(phase1_duration, 2),
        "events_processed": order_analysis.get("events_processed", 0),
        "exceptions_created": order_analysis.get("exceptions_created", 0)
    })
    
    # Phase 2: SLA Evaluation
    phase2_start = datetime.utcnow()
    logger.info("Starting Phase 2: SLA Evaluation", extra={
        "tenant": tenant,
        "flow_correlation_id": flow_correlation_id,
        "phase": "sla_evaluation"
    })
    
    sla_evaluation = await process_sla_evaluations(tenant, lookback_hours)
    phase2_duration = (datetime.utcnow() - phase2_start).total_seconds()
    
    logger.info("Phase 2 completed", extra={
        "tenant": tenant,
        "flow_correlation_id": flow_correlation_id,
        "phase": "sla_evaluation",
        "duration_seconds": round(phase2_duration, 2),
        "orders_evaluated": sla_evaluation.get("orders_evaluated", 0),
        "sla_breaches_detected": sla_evaluation.get("sla_breaches_detected", 0)
    })
    
    # Phase 3: AI Analysis (if enabled)
    ai_processing = {}
    phase3_duration = 0
    
    if enable_ai_processing:
        phase3_start = datetime.utcnow()
        logger.info("Starting Phase 3: AI Processing", extra={
            "tenant": tenant,
            "flow_correlation_id": flow_correlation_id,
            "phase": "ai_processing"
        })
        
        ai_processing = await process_ai_analysis_queue(tenant)
        phase3_duration = (datetime.utcnow() - phase3_start).total_seconds()
        
        logger.info("Phase 3 completed", extra={
            "tenant": tenant,
            "flow_correlation_id": flow_correlation_id,
            "phase": "ai_processing",
            "duration_seconds": round(phase3_duration, 2),
            "exceptions_processed": ai_processing.get("exceptions_processed", 0),
            "ai_success_rate": ai_processing.get("success_rate", 0)
        })
    else:
        logger.info("Phase 3 skipped - AI processing disabled", extra={
            "tenant": tenant,
            "flow_correlation_id": flow_correlation_id,
            "phase": "ai_processing"
        })
    
    # Calculate total metrics
    total_flow_duration = (datetime.utcnow() - flow_start_time).total_seconds()
    total_events_processed = (
        order_analysis.get("events_processed", 0) + 
        sla_evaluation.get("orders_evaluated", 0)
    )
    total_exceptions_created = order_analysis.get("exceptions_created", 0)
    total_sla_breaches = sla_evaluation.get("sla_breaches_detected", 0)
    
    # Compile comprehensive results
    results = {
        "tenant": tenant,
        "flow_correlation_id": flow_correlation_id,
        "processing_timestamp": datetime.utcnow().isoformat(),
        "configuration": {
            "lookback_hours": lookback_hours,
            "enable_ai_processing": enable_ai_processing
        },
        "order_analysis": order_analysis,
        "sla_evaluation": sla_evaluation,
        "ai_processing": ai_processing,
        "performance_metrics": {
            "total_duration_seconds": round(total_flow_duration, 2),
            "phase1_duration_seconds": round(phase1_duration, 2),
            "phase2_duration_seconds": round(phase2_duration, 2),
            "phase3_duration_seconds": round(phase3_duration, 2),
            "events_per_second": round(total_events_processed / total_flow_duration, 2) if total_flow_duration > 0 else 0
        },
        "summary": {
            "total_events_processed": total_events_processed,
            "exceptions_created": total_exceptions_created,
            "sla_breaches": total_sla_breaches,
            "ai_success_rate": ai_processing.get("success_rate", 0),
            "avg_exceptions_per_event": round(total_exceptions_created / total_events_processed, 2) if total_events_processed > 0 else 0,
            "overall_success": True  # Flow completed successfully
        }
    }
    
    logger.info("Event processor flow completed successfully", extra={
        "tenant": tenant,
        "flow_correlation_id": flow_correlation_id,
        "total_duration_seconds": round(total_flow_duration, 2),
        "total_events_processed": total_events_processed,
        "exceptions_created": total_exceptions_created,
        "sla_breaches_detected": total_sla_breaches,
        "ai_processing_enabled": enable_ai_processing,
        "performance_rating": "excellent" if total_flow_duration < 60 else "good" if total_flow_duration < 120 else "needs_optimization"
    })
    
    return results


if __name__ == "__main__":
    # For testing
    import asyncio
    result = asyncio.run(event_processor_flow())
    print(f"Flow result: {result}")
