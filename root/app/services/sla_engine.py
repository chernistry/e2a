# ==== SLA ENGINE SERVICE ==== #

"""
SLA engine for detecting and creating breach exceptions in Octup E²A.

This module provides comprehensive SLA monitoring capabilities with real-time
breach detection, exception creation, and AI-powered analysis integration
for logistics operations.
"""

import datetime as dt
import os
from datetime import timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import OrderEvent, ExceptionRecord
from app.services.policy_loader import get_sla_config, get_reason_code_config
from app.services.ai_exception_analyst import analyze_exception_or_fallback
from app.observability.tracing import get_tracer
from app.observability.metrics import (
    sla_breach_count, 
    sla_evaluation_duration_seconds, 
    active_exceptions
)


# ==== MODULE INITIALIZATION ==== #


tracer = get_tracer(__name__)


# ==== SLA ENGINE CLASS ==== #


class SLAEngine:
    """
    Engine for evaluating SLA compliance and creating exceptions.
    
    Provides real-time SLA monitoring with configurable thresholds,
    automated breach detection, and integration with AI analysis
    for comprehensive exception management.
    """
    
    def __init__(self):
        """
        Initialize SLA engine with configuration caching.
        
        Sets up reason code configuration and SLA config caching
        for optimal performance during high-volume operations.
        """
        self.reason_config = get_reason_code_config()
        # Cache SLA config to avoid repeated file I/O
        self._sla_config_cache = {}
    

    # ==== CONFIGURATION MANAGEMENT ==== #
    
    def _get_cached_sla_config(self, tenant: str) -> Dict[str, any]:
        """
        Get cached SLA configuration for tenant.
        
        Implements intelligent caching with test environment bypass
        to support configuration mocking during testing.
        
        Args:
            tenant (str): Tenant identifier for configuration lookup
            
        Returns:
            Dict[str, any]: SLA configuration dictionary
        """
        # ⚠️ For testing, always reload config to allow mocking
        if os.environ.get("APP_ENV") == "test":
            return get_sla_config(tenant)
            
        if tenant not in self._sla_config_cache:
            self._sla_config_cache[tenant] = get_sla_config(tenant)
        return self._sla_config_cache[tenant]


    # ==== CORE SLA EVALUATION ==== #
    
    async def evaluate_sla(
        self,
        db: AsyncSession,
        tenant: str,
        order_id: str,
        correlation_id: Optional[str] = None
    ) -> Optional[ExceptionRecord]:
        """
        Evaluate SLA compliance for an order and create exception if needed.
        
        Performs comprehensive SLA evaluation by analyzing order events,
        calculating processing times, and detecting threshold breaches
        with automatic exception creation and AI analysis integration.
        
        Args:
            db (AsyncSession): Database session for data access
            tenant (str): Tenant identifier for configuration lookup
            order_id (str): Order identifier to evaluate
            correlation_id (Optional[str]): Request correlation ID for tracing
            
        Returns:
            Optional[ExceptionRecord]: Created exception record if SLA breach 
                                     detected, None otherwise
        """
        with tracer.start_as_current_span("sla_evaluation") as span:
            span.set_attribute("tenant", tenant)
            span.set_attribute("order_id", order_id)
            
            start_time = dt.datetime.utcnow()
            
            try:
                # Get all events for the order
                events = await self._get_order_events(db, tenant, order_id)
                if not events:
                    span.set_attribute("events_found", 0)
                    return None
                
                span.set_attribute("events_found", len(events))
                
                # Get SLA configuration (cached)
                sla_config = self._get_cached_sla_config(tenant)
                
                # Build event timeline
                timeline = self._build_event_timeline(events)
                
                # Check for SLA breaches
                breaches = self._detect_breaches(timeline, sla_config)
                
                if breaches:
                    # Batch check for existing exceptions to reduce DB queries
                    try:
                        existing_exceptions = await self._get_existing_exceptions_batch(
                            db, tenant, order_id, [b["reason_code"] for b in breaches]
                        )
                        existing_reason_codes = {ex.reason_code for ex in existing_exceptions}
                    except Exception as e:
                        # Fallback to individual queries if batch fails
                        print(f"Warning: Batch exception check failed, falling back to individual queries: {e}")
                        existing_reason_codes = set()
                        for breach in breaches:
                            try:
                                existing_ex = await self._get_existing_exception(
                                    db, tenant, order_id, breach["reason_code"]
                                )
                                if existing_ex:
                                    existing_reason_codes.add(breach["reason_code"])
                            except Exception:
                                # If individual query also fails, assume no existing exception
                                pass
                    
                    # Create exceptions for new breaches only
                    created_exceptions = []
                    for breach in breaches:
                        if breach["reason_code"] not in existing_reason_codes:
                            try:
                                exception = await self._create_exception(
                                    db, tenant, order_id, breach, correlation_id
                                )
                                
                                # Update metrics
                                sla_breach_count.labels(
                                    tenant=tenant,
                                    reason_code=breach["reason_code"]
                                ).inc()
                                
                                created_exceptions.append(exception)
                            except Exception as e:
                                print(f"Warning: Failed to create exception for {breach['reason_code']}: {e}")
                                # Continue processing other breaches
                                continue
                    
                    # Return the highest priority newly created exception
                    if created_exceptions:
                        created_exception = min(created_exceptions, 
                                              key=lambda ex: self._get_breach_priority(ex.reason_code))
                        span.set_attribute("breach_detected", True)
                        span.set_attribute("reason_code", created_exception.reason_code)
                        return created_exception
                
                span.set_attribute("breach_detected", False)
                return None
                
            finally:
                # Record evaluation duration
                duration = (dt.datetime.utcnow() - start_time).total_seconds()
                sla_evaluation_duration_seconds.labels(tenant=tenant).observe(duration)
    
    # ==== EXCEPTION MANAGEMENT ==== #
    
    async def _get_existing_exceptions_batch(
        self,
        db: AsyncSession,
        tenant: str,
        order_id: str,
        reason_codes: List[str]
    ) -> List[ExceptionRecord]:
        """
        Batch check for existing exceptions for multiple reason codes.
        
        Optimized batch query to check for existing active exceptions
        across multiple reason codes to avoid duplicate exception creation.
        
        Args:
            db (AsyncSession): Database session for queries
            tenant (str): Tenant identifier for data isolation
            order_id (str): Order identifier to check
            reason_codes (List[str]): List of reason codes to check
            
        Returns:
            List[ExceptionRecord]: List of existing exception records
        """
        if not reason_codes:
            return []
            
        query = select(ExceptionRecord).where(
            ExceptionRecord.tenant == tenant,
            ExceptionRecord.order_id == order_id,
            ExceptionRecord.reason_code.in_(reason_codes),
            ExceptionRecord.status.in_(["OPEN", "IN_PROGRESS"])
        )
        
        result = await db.execute(query)
        return list(result.scalars())


    async def _get_existing_exception(
        self,
        db: AsyncSession,
        tenant: str,
        order_id: str,
        reason_code: str
    ) -> Optional[ExceptionRecord]:
        """
        Check if an exception already exists for this order and reason code.
        
        Prevents duplicate exception creation by checking for existing
        active exceptions with the same order and reason code combination.
        
        Args:
            db (AsyncSession): Database session for queries
            tenant (str): Tenant identifier for data isolation
            order_id (str): Order identifier to check
            reason_code (str): Reason code to check
            
        Returns:
            Optional[ExceptionRecord]: Existing exception record if found, 
                                     None otherwise
        """
        query = select(ExceptionRecord).where(
            ExceptionRecord.tenant == tenant,
            ExceptionRecord.order_id == order_id,
            ExceptionRecord.reason_code == reason_code,
            ExceptionRecord.status.in_(["OPEN", "IN_PROGRESS"])
        )
        
        result = await db.execute(query)
        return result.scalar_one_or_none()


    # ==== DATA RETRIEVAL ==== #
    
    async def _get_order_events(
        self,
        db: AsyncSession,
        tenant: str,
        order_id: str
    ) -> List[OrderEvent]:
        """
        Get all events for an order.
        
        Retrieves complete event history for an order sorted by occurrence
        time to enable accurate SLA calculation and breach detection.
        
        Args:
            db (AsyncSession): Database session for queries
            tenant (str): Tenant identifier for data isolation
            order_id (str): Order identifier to retrieve events for
            
        Returns:
            List[OrderEvent]: List of order events sorted by occurrence time
        """
        query = select(OrderEvent).where(
            OrderEvent.tenant == tenant,
            OrderEvent.order_id == order_id
        ).order_by(OrderEvent.occurred_at)
        
        result = await db.execute(query)
        return list(result.scalars())
    
    # ==== TIMELINE ANALYSIS ==== #
    
    def _build_event_timeline(self, events: List[OrderEvent]) -> Dict[str, dt.datetime]:
        """
        Build event timeline from order events.
        
        Constructs chronological timeline mapping event types to timestamps
        for SLA calculation and breach detection analysis.
        
        Args:
            events (List[OrderEvent]): List of order events to analyze
            
        Returns:
            Dict[str, dt.datetime]: Dictionary mapping event types to timestamps
        """
        timeline = {}
        
        for event in events:
            # Use the latest occurrence of each event type
            if event.event_type not in timeline or event.occurred_at > timeline[event.event_type]:
                timeline[event.event_type] = event.occurred_at
        
        return timeline
    
    def _detect_breaches(
        self,
        timeline: Dict[str, dt.datetime],
        sla_config: Dict[str, any]
    ) -> List[Dict[str, any]]:
        """
        Detect SLA breaches in event timeline.
        
        Analyzes event timeline against SLA configuration to identify
        threshold violations and missing scan scenarios with priority
        sorting for exception management.
        
        Args:
            timeline (Dict[str, dt.datetime]): Event timeline to analyze
            sla_config (Dict[str, any]): SLA configuration with thresholds
            
        Returns:
            List[Dict[str, any]]: List of detected breaches with details
        """
        breaches = []
        
        # Check pick SLA: order_paid -> pick_completed
        pick_breach = self._check_pick_sla(timeline, sla_config)
        if pick_breach:
            breaches.append(pick_breach)
        
        # Check pack SLA: pick_completed -> pack_completed
        pack_breach = self._check_pack_sla(timeline, sla_config)
        if pack_breach:
            breaches.append(pack_breach)
        
        # Check ship SLA: pack_completed -> manifested
        ship_breach = self._check_ship_sla(timeline, sla_config)
        if ship_breach:
            breaches.append(ship_breach)
        
        # Check for missing scans
        missing_scan_breach = self._check_missing_scans(timeline, sla_config)
        if missing_scan_breach:
            breaches.append(missing_scan_breach)
        
        # Sort by severity (most critical first)
        breaches.sort(key=lambda x: self._get_breach_priority(x["reason_code"]))
        
        return breaches
    
    # ==== SLA COMPLIANCE CHECKS ==== #
    
    def _check_pick_sla(
        self,
        timeline: Dict[str, dt.datetime],
        sla_config: Dict[str, any]
    ) -> Optional[Dict[str, any]]:
        """
        Check pick SLA compliance.
        
        Evaluates pick operation timing from order payment to completion
        against configured SLA thresholds for breach detection.
        
        Args:
            timeline (Dict[str, dt.datetime]): Event timeline to analyze
            sla_config (Dict[str, any]): SLA configuration with pick thresholds
            
        Returns:
            Optional[Dict[str, any]]: Breach details if SLA violated, None otherwise
        """
        if "order_paid" not in timeline or "pick_completed" not in timeline:
            return None
        
        pick_duration = self._calculate_duration_minutes(
            timeline["order_paid"],
            timeline["pick_completed"]
        )
        
        pick_sla = sla_config.get("pick_minutes", 120)
        
        if pick_duration > pick_sla:
            return {
                "reason_code": "PICK_DELAY",
                "actual_minutes": pick_duration,
                "sla_minutes": pick_sla,
                "delay_minutes": pick_duration - pick_sla,
                "severity": "MEDIUM"
            }
        
        return None
    
    def _check_pack_sla(
        self,
        timeline: Dict[str, dt.datetime],
        sla_config: Dict[str, any]
    ) -> Optional[Dict[str, any]]:
        """
        Check pack SLA compliance.
        
        Evaluates pack operation timing from pick completion to pack completion
        against configured SLA thresholds for breach detection.
        
        Args:
            timeline (Dict[str, dt.datetime]): Event timeline to analyze
            sla_config (Dict[str, any]): SLA configuration with pack thresholds
            
        Returns:
            Optional[Dict[str, any]]: Breach details if SLA violated, None otherwise
        """
        if "pick_completed" not in timeline or "pack_completed" not in timeline:
            return None
        
        pack_duration = self._calculate_duration_minutes(
            timeline["pick_completed"],
            timeline["pack_completed"]
        )
        
        pack_sla = sla_config.get("pack_minutes", 180)
        
        if pack_duration > pack_sla:
            return {
                "reason_code": "PACK_DELAY",
                "actual_minutes": pack_duration,
                "sla_minutes": pack_sla,
                "delay_minutes": pack_duration - pack_sla,
                "severity": "MEDIUM"
            }
        
        return None
    
    def _check_ship_sla(
        self,
        timeline: Dict[str, dt.datetime],
        sla_config: Dict[str, any]
    ) -> Optional[Dict[str, any]]:
        """
        Check ship SLA compliance.
        
        Evaluates shipping operation timing from pack completion to shipment
        against configured SLA thresholds with comprehensive event detection.
        
        Args:
            timeline (Dict[str, dt.datetime]): Event timeline to analyze
            sla_config (Dict[str, any]): SLA configuration with ship thresholds
            
        Returns:
            Optional[Dict[str, any]]: Breach details if SLA violated, None otherwise
        """
        if "pack_completed" not in timeline:
            return None
        
        # Check if shipped (manifested, picked_up, or shipment_dispatched)
        ship_time = (timeline.get("manifested") or 
                    timeline.get("picked_up") or 
                    timeline.get("shipment_dispatched"))
        if not ship_time:
            # Check if we're past the SLA without shipping
            now = dt.datetime.utcnow()
            ship_duration = self._calculate_duration_minutes(
                timeline["pack_completed"],
                now
            )
            
            ship_sla = sla_config.get("ship_minutes", 1440)  # 24 hours
            
            if ship_duration > ship_sla:
                return {
                    "reason_code": "CARRIER_ISSUE",
                    "actual_minutes": ship_duration,
                    "sla_minutes": ship_sla,
                    "delay_minutes": ship_duration - ship_sla,
                    "severity": "HIGH"
                }
        else:
            # Check actual ship time
            ship_duration = self._calculate_duration_minutes(
                timeline["pack_completed"],
                ship_time
            )
            
            ship_sla = sla_config.get("ship_minutes", 1440)
            
            if ship_duration > ship_sla:
                return {
                    "reason_code": "CARRIER_ISSUE",
                    "actual_minutes": ship_duration,
                    "sla_minutes": ship_sla,
                    "delay_minutes": ship_duration - ship_sla,
                    "severity": "HIGH"
                }
        
        return None
    
    def _check_missing_scans(
        self,
        timeline: Dict[str, dt.datetime],
        sla_config: Dict[str, any]
    ) -> Optional[Dict[str, any]]:
        """
        Check for missing expected scans.
        
        Detects scenarios where expected scan events are missing
        beyond reasonable SLA thresholds with buffer allowances.
        
        Args:
            timeline (Dict[str, dt.datetime]): Event timeline to analyze
            sla_config (Dict[str, any]): SLA configuration with thresholds
            
        Returns:
            Optional[Dict[str, any]]: Breach details if missing scans detected, None otherwise
        """
        # If we have pick_completed but no pack_completed after pack SLA
        if "pick_completed" in timeline and "pack_completed" not in timeline:
            now = dt.datetime.utcnow()
            duration = self._calculate_duration_minutes(
                timeline["pick_completed"],
                now
            )
            
            pack_sla = sla_config.get("pack_minutes", 180)
            
            if duration > pack_sla * 1.5:  # 50% buffer for missing scans
                return {
                    "reason_code": "MISSING_SCAN",
                    "actual_minutes": duration,
                    "expected_event": "pack_completed",
                    "severity": "MEDIUM"
                }
        
        return None
    
    # ==== UTILITY FUNCTIONS ==== #
    
    def _calculate_duration_minutes(
        self,
        start_time: dt.datetime,
        end_time: dt.datetime
    ) -> float:
        """
        Calculate duration between two timestamps in minutes.
        
        Ensures proper timezone handling and provides accurate
        duration calculations for SLA compliance evaluation.
        
        Args:
            start_time (dt.datetime): Start timestamp for calculation
            end_time (dt.datetime): End timestamp for calculation
            
        Returns:
            float: Duration in minutes between timestamps
        """
        # Ensure both datetimes have timezone info
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
            
        return (end_time - start_time).total_seconds() / 60.0
    
    def _get_breach_priority(self, reason_code: str) -> int:
        """
        Get priority for breach sorting (lower = higher priority).
        
        Defines priority ordering for breach handling based on
        business impact and chronological dependencies.
        
        Args:
            reason_code (str): Reason code to determine priority for
            
        Returns:
            int: Priority value (chronological order preferred)
        """
        priority_map = {
            "SYSTEM_ERROR": 1,
            "STOCK_MISMATCH": 2,
            "ADDRESS_ERROR": 3,
            "SHIP_DELAY": 4,
            "PICK_DELAY": 5,  # Pick comes before pack chronologically
            "PACK_DELAY": 6,  # Pack comes after pick
            "CARRIER_ISSUE": 6,  # Same priority as pack delay but higher than missing scan
            "MISSING_SCAN": 7,
            "OTHER": 8
        }
        
        return priority_map.get(reason_code, 10)
    
    # ==== EXCEPTION CREATION ==== #
    
    async def _create_exception(
        self,
        db: AsyncSession,
        tenant: str,
        order_id: str,
        breach: Dict[str, any],
        correlation_id: Optional[str] = None
    ) -> ExceptionRecord:
        """
        Create exception record for SLA breach.
        
        Creates comprehensive exception records with AI analysis
        integration and metrics tracking for operational visibility.
        
        Args:
            db (AsyncSession): Database session for persistence
            tenant (str): Tenant identifier for data isolation
            order_id (str): Order identifier for exception association
            breach (Dict[str, any]): Breach details and context
            correlation_id (Optional[str]): Request correlation ID for tracing
            
        Returns:
            ExceptionRecord: Created exception record with full context
        """
        reason_code = breach["reason_code"]
        reason_config = self.reason_config.get(reason_code, {})
        
        exception = ExceptionRecord(
            tenant=tenant,
            order_id=order_id,
            reason_code=reason_code,
            status="OPEN",
            severity=breach.get("severity", reason_config.get("severity", "MEDIUM")),
            correlation_id=correlation_id,
            context_data=breach
        )
        
        db.add(exception)
        await db.commit()
        await db.refresh(exception)
        
        # Trigger AI analysis (fire and forget to avoid blocking)
        try:
            await analyze_exception_or_fallback(db, exception)
        except Exception as e:
            # Log the error but don't fail the exception creation
            print(f"Warning: AI analysis failed for exception {exception.id}: {e}")
        
        # Update active exceptions metric
        active_exceptions.labels(
            tenant=tenant,
            reason_code=reason_code
        ).inc()
        
        return exception


# ==== GLOBAL SERVICE INSTANCE ==== #


# Global instance
_sla_engine: Optional[SLAEngine] = None


def get_sla_engine() -> SLAEngine:
    """
    Get global SLA engine instance.
    
    Provides singleton access to the SLA engine for consistent
    configuration and resource management across the application.
    
    Returns:
        SLAEngine: Global SLA engine instance
    """
    global _sla_engine
    if _sla_engine is None:
        _sla_engine = SLAEngine()
    return _sla_engine


# ==== CONVENIENCE FUNCTIONS ==== #


async def evaluate_sla(
    db: AsyncSession,
    tenant: str,
    order_id: str,
    correlation_id: Optional[str] = None
) -> Optional[ExceptionRecord]:
    """
    Convenience function for SLA evaluation.
    
    Provides simplified access to SLA evaluation functionality
    without requiring direct engine instantiation.
    
    Args:
        db (AsyncSession): Database session for data access
        tenant (str): Tenant identifier for configuration lookup
        order_id (str): Order identifier to evaluate
        correlation_id (Optional[str]): Request correlation ID for tracing
        
    Returns:
        Optional[ExceptionRecord]: Created exception record if breach detected, None otherwise
    """
    engine = get_sla_engine()
    return await engine.evaluate_sla(db, tenant, order_id, correlation_id)
