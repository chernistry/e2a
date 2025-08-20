# ==== EVENT INGEST ROUTES ==== #

"""
Ingest routes for processing Shopify-like e-commerce events in Octup E²A.

This module provides comprehensive event ingestion endpoints with idempotency
protection, SLA evaluation, dead letter queue handling, and comprehensive
observability for high-volume e-commerce event processing.
"""

from datetime import datetime, timezone
from typing import Union, Dict, Any

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.schemas.ingest import (
    ShopifyOrderEvent, 
    WMSEvent, 
    CarrierEvent, 
    IngestResponse
)
from app.storage.db import get_db_session
from app.storage.models import OrderEvent
from app.storage.dlq import push_dlq
from app.services.idempotency import get_idempotency_service
from app.services.sla_engine import evaluate_sla
from app.observability.tracing import get_tracer
from app.observability.metrics import (
    ingest_success_total, 
    ingest_errors_total, 
    ingest_latency_seconds
)
from app.middleware.tenancy import get_tenant_id


# ==== ROUTER INITIALIZATION ==== #


router = APIRouter()
tracer = get_tracer(__name__)


# ==== SHOPIFY EVENT PROCESSING ==== #


@router.post("/events", response_model=IngestResponse)
async def ingest_events_raw(
    event_data: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> IngestResponse:
    """
    Ingest Shopify-like e-commerce events.
    
    Processes realistic e-commerce events including orders, fulfillments,
    and payments with automatic SLA evaluation and exception detection.
    
    Args:
        event_data: Raw event data from Shopify-like simulator
        request: HTTP request with tenant context
        db: Database session dependency
        
    Returns:
        IngestResponse: Processing result with event ID and status
    """
    tenant = get_tenant_id(request)
    
    with tracer.start_as_current_span("ingest_shopify_event") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("event_type", event_data.get("event_type", "unknown"))
        span.set_attribute("source", event_data.get("source", "unknown"))
        
        try:
            # Extract event details
            event_id = event_data.get("event_id")
            event_type = event_data.get("event_type")
            source = event_data.get("source", "shopify")
            order_id = event_data.get("order_id")
            occurred_at_str = event_data.get("occurred_at")
            correlation_id = event_data.get("correlation_id")
            
            # Validate required fields
            if not all([event_id, event_type, order_id, occurred_at_str]):
                raise HTTPException(
                    status_code=400,
                    detail="Missing required fields: event_id, event_type, order_id, occurred_at"
                )
            
            # Parse timestamp
            try:
                occurred_at = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
                # Convert to UTC timezone-naive for consistent database storage
                if occurred_at.tzinfo is not None:
                    occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid timestamp format: {occurred_at_str}"
                )
            
            # Check for idempotency
            idempotency_service = get_idempotency_service()
            if await idempotency_service.is_processed(event_id, "shopify", tenant):
                span.set_attribute("duplicate", True)
                return IngestResponse(
                    event_id=event_id,
                    status="duplicate",
                    message="Event already processed"
                )
            
            # Create order event record
            order_event = OrderEvent(
                event_id=event_id,
                tenant=tenant,
                order_id=order_id,
                event_type=event_type,
                source=source,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
                payload=event_data
            )
            
            # Save to database
            db.add(order_event)
            await db.commit()
            
            # Record idempotency
            await idempotency_service.mark_processed(event_id, "shopify", tenant)
            
            # Evaluate SLA if this is an order-related event
            if event_type in ["order_created", "fulfillment_created", "package_shipped", "delivered"]:
                try:
                    await evaluate_sla(
                        order_id=order_id,
                        event_type=event_type,
                        occurred_at=occurred_at,
                        tenant=tenant,
                        db=db,
                        event_data=event_data
                    )
                except Exception as sla_error:
                    # Log SLA evaluation error but don't fail the ingestion
                    span.record_exception(sla_error)
                    span.set_attribute("sla_evaluation_failed", True)
            
            # Analyze order for problems if this is an order creation event
            if event_type == "order_created":
                try:
                    from app.services.order_analyzer import get_order_analyzer
                    analyzer = get_order_analyzer()
                    problems = await analyzer.analyze_order(event_data)
                    
                    # Create exceptions for detected problems
                    for problem in problems:
                        try:
                            from app.storage.models import ExceptionRecord
                            from app.services.ai_exception_analyst import analyze_exception_or_fallback
                            
                            exception = ExceptionRecord(
                                tenant=tenant,
                                order_id=order_id,
                                reason_code=problem["reason_code"],
                                status="OPEN",
                                severity=problem["severity"],
                                correlation_id=correlation_id,
                                context_data={
                                    "customer_name": event_data.get("data", {}).get("order", {}).get("customer", {}).get("first_name", "") + " " + 
                                                   event_data.get("data", {}).get("order", {}).get("customer", {}).get("last_name", ""),
                                    "customer_email": event_data.get("data", {}).get("order", {}).get("customer", {}).get("email", ""),
                                    "order_value": float(event_data.get("data", {}).get("order", {}).get("total_price", 0)),
                                    "currency": event_data.get("data", {}).get("order", {}).get("currency", "USD"),
                                    "shipping_address": event_data.get("data", {}).get("order", {}).get("shipping_address", {}),
                                    "order_date": event_data.get("data", {}).get("order", {}).get("created_at", ""),
                                    "expected_delivery": event_data.get("data", {}).get("order", {}).get("estimated_delivery_date", ""),
                                    "problem_details": problem.get("context", {})
                                },
                                ops_note=f"Auto-detected: {problem['description']}"
                            )
                            
                            db.add(exception)
                            await db.flush()
                            
                            # Trigger AI analysis
                            await analyze_exception_or_fallback(db, exception)
                            
                            span.set_attribute("problem_detected", True)
                            span.set_attribute("problem_type", problem["reason_code"])
                            
                        except Exception as exc_error:
                            # Log exception creation error but don't fail the ingestion
                            span.record_exception(exc_error)
                            print(f"Warning: Failed to create exception for problem {problem['reason_code']}: {exc_error}")
                            
                except Exception as analysis_error:
                    # Log analysis error but don't fail the ingestion
                    span.record_exception(analysis_error)
                    span.set_attribute("order_analysis_failed", True)
            
            # Update metrics
            ingest_success_total.labels(
                tenant=tenant,
                source=source,
                event_type=event_type
            ).inc()
            
            span.set_attribute("success", True)
            
            return IngestResponse(
                event_id=event_id,
                status="processed",
                message="Event processed successfully"
            )
            
        except HTTPException:
            raise
        except IntegrityError as e:
            # Handle duplicate key violations
            await db.rollback()
            
            if "duplicate key" in str(e).lower():
                return IngestResponse(
                    event_id=event_data.get("event_id", "unknown"),
                    status="duplicate",
                    message="Event already exists"
                )
            else:
                raise HTTPException(status_code=500, detail="Database integrity error")
                
        except Exception as e:
            await db.rollback()
            
            # Push to DLQ for later processing
            try:
                await push_dlq(
                    tenant=tenant,
                    event_data=event_data,
                    error_message=str(e),
                    db=db
                )
            except Exception as dlq_error:
                span.record_exception(dlq_error)
            
            # Update error metrics
            ingest_errors_total.labels(
                tenant=tenant,
                source=event_data.get("source", "unknown"),
                error_type="processing_error"
            ).inc()
            
            span.record_exception(e)
            span.set_attribute("success", False)
            
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process event: {str(e)}"
            )


# ==== CORE PROCESSING FUNCTIONS ==== #


async def _process_event(
    event: Union[ShopifyOrderEvent, WMSEvent, CarrierEvent],
    request: Request,
    db: AsyncSession
) -> IngestResponse:
    """
    Process incoming event with idempotency and SLA evaluation.
    
    Implements comprehensive event processing with duplicate detection,
    database persistence, SLA breach evaluation, and error handling
    with dead letter queue fallback for failed operations.
    
    Args:
        event (Union[ShopifyOrderEvent, WMSEvent, CarrierEvent]): Event data
        request (Request): HTTP request with correlation context
        db (AsyncSession): Database session for persistence
        
    Returns:
        IngestResponse: Processing result with status and metadata
        
    Raises:
        HTTPException: If processing fails after all retry attempts
    """
    tenant = get_tenant_id(request)
    correlation_id = request.state.correlation_id
    
    with tracer.start_as_current_span("process_event") as span:
        span.set_attribute("tenant", tenant)
        span.set_attribute("source", event.source)
        span.set_attribute("event_type", event.event_type)
        span.set_attribute("order_id", event.order_id)
        span.set_attribute("correlation_id", correlation_id)
        
        idempotency = get_idempotency_service()
        
        try:
            # Check if already processed
            if await idempotency.is_processed(tenant, event.source, event.event_id):
                span.set_attribute("duplicate", True)
                return IngestResponse(
                    message="Event already processed (duplicate)",
                    correlation_id=correlation_id
                )
            
            # Acquire processing lock
            if not await idempotency.acquire_lock(tenant, event.source, event.event_id):
                raise HTTPException(
                    status_code=409,
                    detail="Concurrent processing detected"
                )
            
            try:
                # Parse timestamp and convert to UTC timezone-naive for database
                occurred_at = datetime.fromisoformat(
                    event.occurred_at.replace('Z', '+00:00')
                )
                # Convert to UTC timezone-naive for consistent database storage
                if occurred_at.tzinfo is not None:
                    occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)
                
                # Create order event record
                order_event = OrderEvent(
                    tenant=tenant,
                    source=event.source,
                    event_type=event.event_type,
                    event_id=event.event_id,
                    order_id=event.order_id,
                    occurred_at=occurred_at,
                    payload=event.model_dump(),
                    correlation_id=correlation_id
                )
                
                db.add(order_event)
                await db.flush()
                
                # Evaluate SLA compliance
                exception_result = await evaluate_sla(
                    db, tenant, event.order_id, correlation_id
                )
                
                # Commit transaction
                await db.commit()
                
                # Mark as processed
                await idempotency.mark_processed(tenant, event.source, event.event_id)
                
                # Update metrics
                ingest_success_total.labels(
                    tenant=tenant,
                    source=event.source,
                    event_type=event.event_type
                ).inc()
                
                span.set_attribute("success", True)
                span.set_attribute("exception_created", bool(exception_result))
                
                # Prepare response
                response_data = {
                    "message": "Event processed successfully",
                    "event_id": event.event_id,
                    "order_id": event.order_id,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "exception_created": bool(exception_result),
                    "correlation_id": correlation_id
                }
                
                # Add reason_code and exception_id if exception was created
                if exception_result:
                    try:
                        # Properly handle SQLAlchemy object in async context
                        if hasattr(exception_result, 'reason_code'):
                            # Ensure the object is properly loaded in async context
                            await db.refresh(exception_result)
                            
                            # Access attributes immediately after refresh to avoid MissingGreenlet
                            # Store in local variables to prevent lazy loading issues
                            reason_code = exception_result.reason_code
                            exception_id = exception_result.id if hasattr(exception_result, 'id') else None
                            
                            response_data["reason_code"] = reason_code
                            if exception_id is not None:
                                response_data["exception_id"] = exception_id
                        else:
                            # If exception_result is just a boolean True, use default
                            response_data["reason_code"] = "PICK_DELAY"  # Default for now
                    except Exception as attr_error:
                        # Fallback if SQLAlchemy object access fails (e.g., MissingGreenlet)
                        span.set_attribute("attribute_access_error", str(attr_error))
                        response_data["reason_code"] = "PROCESSING_ERROR"
                        # Log the error but don't fail the entire request
                        print(f"Warning: Could not access exception attributes: {attr_error}")
                
                return IngestResponse(**response_data)
                
            except IntegrityError:
                # Handle duplicate constraint violations gracefully
                await db.rollback()
                
                # This is likely a duplicate that slipped through idempotency check
                # Mark as processed to prevent future attempts
                await idempotency.mark_processed(tenant, event.source, event.event_id)
                
                span.set_attribute("duplicate_constraint", True)
                
                return IngestResponse(
                    message="Event already processed (duplicate detected at database level)",
                    event_id=event.event_id,
                    order_id=event.order_id,
                    processed_at=datetime.now(timezone.utc).isoformat(),
                    exception_created=False,
                    correlation_id=correlation_id,
                    status="duplicate"
                )
                
            finally:
                # Always release lock
                await idempotency.release_lock(tenant, event.source, event.event_id)
                
        except Exception as e:
            await db.rollback()
            
            # Add to DLQ for retry
            await push_dlq(
                db,
                tenant,
                event.model_dump(),
                type(e).__name__,
                str(e),
                correlation_id,
                "ingest_event"
            )
            await db.commit()
            
            # Update error metrics
            ingest_errors_total.labels(
                tenant=tenant,
                source=event.source,
                error_type=type(e).__name__.replace(".", "_").replace(" ", "_")
            ).inc()
            
            span.set_attribute("error", str(e))
            span.set_attribute("error_type", type(e).__name__)
            
            raise HTTPException(
                status_code=500,
                detail=f"Event processing failed: {str(e)}"
            )


# ==== EVENT INGESTION ENDPOINTS ==== #


@router.post("/shopify", response_model=IngestResponse)
async def ingest_shopify_event(
    event: ShopifyOrderEvent,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> IngestResponse:
    """
    Ingest Shopify order event.
    
    Processes Shopify order events with comprehensive validation,
    idempotency protection, and SLA evaluation.
    
    Args:
        event (ShopifyOrderEvent): Shopify event data
        request (Request): HTTP request with correlation context
        db (AsyncSession): Database session dependency
        
    Returns:
        IngestResponse: Processing result with status and metadata
    """
    with ingest_latency_seconds.labels(
        tenant=get_tenant_id(request),
        source="shopify",
        event_type=event.event_type
    ).time():
        return await _process_event(event, request, db)


@router.post("/wms", response_model=IngestResponse)
async def ingest_wms_event(
    event: WMSEvent,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> IngestResponse:
    """
    Ingest WMS (Warehouse Management System) event.
    
    Processes warehouse management system events with comprehensive
    validation, idempotency protection, and SLA evaluation.
    
    Args:
        event (WMSEvent): WMS event data
        request (Request): HTTP request with correlation context
        db (AsyncSession): Database session dependency
        
    Returns:
        IngestResponse: Processing result with status and metadata
    """
    with ingest_latency_seconds.labels(
        tenant=get_tenant_id(request),
        source="wms",
        event_type=event.event_type
    ).time():
        return await _process_event(event, request, db)


@router.post("/carrier", response_model=IngestResponse)
async def ingest_carrier_event(
    event: CarrierEvent,
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> IngestResponse:
    """
    Ingest carrier tracking event.
    
    Processes carrier tracking events with comprehensive validation,
    idempotency protection, and SLA evaluation.
    
    Args:
        event (CarrierEvent): Carrier event data
        request (Request): HTTP request with correlation context
        db (AsyncSession): Database session dependency
        
    Returns:
        IngestResponse: Processing result with status and metadata
    """
    with ingest_latency_seconds.labels(
        tenant=get_tenant_id(request),
        source="carrier",
        event_type=event.event_type
    ).time():
        return await _process_event(event, request, db)


# ==== INGESTION ANALYTICS ==== #


@router.get("/stats")
async def get_ingest_stats(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """
    Get ingestion statistics for tenant.
    
    Provides comprehensive statistics on event ingestion including
    counts by source, type, and recent activity patterns.
    
    Args:
        request (Request): HTTP request with tenant context
        db (AsyncSession): Database session dependency
        
    Returns:
        dict: Ingestion statistics with breakdown by source and type
    """
    from sqlalchemy import select, func
    from app.storage.models import OrderEvent
    
    tenant = get_tenant_id(request)
    
    with tracer.start_as_current_span("get_ingest_stats") as span:
        span.set_attribute("tenant", tenant)
        
        try:
            # Get total events count
            total_result = await db.execute(
                select(func.count(OrderEvent.id)).where(OrderEvent.tenant == tenant)
            )
            total_events = total_result.scalar() or 0
            
            # Get events by source
            source_result = await db.execute(
                select(OrderEvent.source, func.count(OrderEvent.id))
                .where(OrderEvent.tenant == tenant)
                .group_by(OrderEvent.source)
            )
            events_by_source = {
                "shopify": 0,
                "wms": 0,
                "carrier": 0
            }
            for source, count in source_result.fetchall():
                if source in events_by_source:
                    events_by_source[source] = count
            
            # Get events by type
            type_result = await db.execute(
                select(OrderEvent.event_type, func.count(OrderEvent.id))
                .where(OrderEvent.tenant == tenant)
                .group_by(OrderEvent.event_type)
            )
            events_by_type = {}
            for event_type, count in type_result.fetchall():
                events_by_type[event_type] = count
            
            # Get recent activity (last 10 events)
            recent_result = await db.execute(
                select(OrderEvent.event_type, OrderEvent.source, OrderEvent.created_at)
                .where(OrderEvent.tenant == tenant)
                .order_by(OrderEvent.created_at.desc())
                .limit(10)
            )
            recent_activity = []
            for event_type, source, created_at in recent_result.fetchall():
                recent_activity.append({
                    "event_type": event_type,
                    "source": source,
                    "timestamp": created_at.isoformat() if created_at else None
                })
            
            span.set_attribute("total_events", total_events)
            
            return {
                "tenant": tenant,
                "total_events": total_events,
                "events_by_source": events_by_source,
                "events_by_type": events_by_type,
                "recent_activity": recent_activity
            }
            
        except Exception as e:
            span.record_exception(e)
            span.set_attribute("error", str(e))
            
            # Return empty stats on error
            return {
                "tenant": tenant,
                "total_events": 0,
                "events_by_source": {
                    "shopify": 0,
                    "wms": 0,
                    "carrier": 0
                },
                "events_by_type": {},
                "recent_activity": []
            }
