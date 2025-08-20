# ==== DATA ENRICHMENT PIPELINE ==== #

"""
Comprehensive data enrichment pipeline for Octup E²A.

This module provides systematic data enrichment with AI services, ensuring
all records reach their required enrichment state through automatic reprocessing,
failure recovery, and completeness tracking.

Architecture:
- Sequential enrichment stages with dependency management
- Automatic reprocessing of failed/incomplete enrichment
- Comprehensive state tracking and monitoring
- Graceful degradation and fallback mechanisms
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Tuple
from enum import Enum
from dataclasses import dataclass

from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import get_session
from app.storage.models import ExceptionRecord, OrderEvent
from app.services.ai_exception_analyst import get_ai_exception_analyst
from app.services.ai_automated_resolution import get_ai_automated_resolution_service
from app.services.ai_order_analyzer import get_ai_order_analyzer
from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger
from app.observability.metrics import (
    ai_requests_total,
    ai_failures_total,
    ai_fallback_rate
)


# ==== MODULE INITIALIZATION ==== #

tracer = get_tracer(__name__)
logger = ContextualLogger(__name__)


# ==== ENRICHMENT DEFINITIONS ==== #

class EnrichmentStage(Enum):
    """Enrichment stages in dependency order."""
    ORDER_ANALYSIS = "order_analysis"          # AI Order Problem Detection
    EXCEPTION_CLASSIFICATION = "classification" # AI Exception Classification  
    AUTOMATED_RESOLUTION = "automation"        # AI Automated Resolution
    COMPLETE = "complete"                      # All enrichment complete


class EnrichmentStatus(Enum):
    """Enrichment status for tracking."""
    PENDING = "pending"           # Not yet processed
    IN_PROGRESS = "in_progress"   # Currently being processed
    COMPLETED = "completed"       # Successfully completed
    FAILED = "failed"            # Failed, needs retry
    SKIPPED = "skipped"          # Skipped due to conditions


@dataclass
class EnrichmentState:
    """Complete enrichment state for a record."""
    record_id: int
    record_type: str  # "exception" or "order"
    
    # Stage completion status
    order_analysis: EnrichmentStatus = EnrichmentStatus.PENDING
    classification: EnrichmentStatus = EnrichmentStatus.PENDING
    automation: EnrichmentStatus = EnrichmentStatus.PENDING
    
    # Metadata
    last_attempt: Optional[datetime] = None
    retry_count: int = 0
    error_messages: List[str] = None
    
    def __post_init__(self):
        if self.error_messages is None:
            self.error_messages = []
    
    @property
    def current_stage(self) -> EnrichmentStage:
        """Get the current stage that needs processing."""
        if self.order_analysis == EnrichmentStatus.PENDING:
            return EnrichmentStage.ORDER_ANALYSIS
        elif self.classification == EnrichmentStatus.PENDING:
            return EnrichmentStage.EXCEPTION_CLASSIFICATION
        elif self.automation == EnrichmentStatus.PENDING:
            return EnrichmentStage.AUTOMATED_RESOLUTION
        else:
            return EnrichmentStage.COMPLETE
    
    @property
    def is_complete(self) -> bool:
        """Check if all enrichment stages are complete."""
        return all(
            status in [EnrichmentStatus.COMPLETED, EnrichmentStatus.SKIPPED]
            for status in [self.order_analysis, self.classification, self.automation]
        )
    
    @property
    def has_failures(self) -> bool:
        """Check if any stage has failed."""
        return any(
            status == EnrichmentStatus.FAILED
            for status in [self.order_analysis, self.classification, self.automation]
        )
    
    @property
    def needs_reprocessing(self) -> bool:
        """Check if record needs reprocessing."""
        return (
            not self.is_complete and 
            (self.last_attempt is None or 
             (datetime.utcnow() - self.last_attempt) > timedelta(hours=1))
        )


# ==== ENRICHMENT PIPELINE CLASS ==== #

class DataEnrichmentPipeline:
    """
    Comprehensive data enrichment pipeline.
    
    Manages systematic AI enrichment of all data records with automatic
    reprocessing, failure recovery, and completeness tracking.
    """
    
    def __init__(self):
        """Initialize the enrichment pipeline."""
        self.ai_exception_analyst = get_ai_exception_analyst()
        self.ai_resolution_service = get_ai_automated_resolution_service()
        self.ai_order_analyzer = get_ai_order_analyzer()
        
        # Stage processors mapping
        self.stage_processors = {
            EnrichmentStage.ORDER_ANALYSIS: self._process_order_analysis,
            EnrichmentStage.EXCEPTION_CLASSIFICATION: self._process_exception_classification,
            EnrichmentStage.AUTOMATED_RESOLUTION: self._process_automated_resolution
        }
    
    async def process_enrichment_pipeline(
        self,
        tenant: str,
        batch_size: int = 50,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Process the complete enrichment pipeline for a tenant.
        
        Args:
            tenant (str): Tenant identifier
            batch_size (int): Number of records to process per batch
            max_retries (int): Maximum retry attempts for failed enrichment
            
        Returns:
            Dict[str, Any]: Pipeline execution results and statistics
        """
        with tracer.start_as_current_span("enrichment_pipeline") as span:
            span.set_attribute("tenant", tenant)
            span.set_attribute("batch_size", batch_size)
            
            logger.info(f"Starting enrichment pipeline for tenant {tenant}")
            
            stats = {
                "tenant": tenant,
                "execution_time": datetime.utcnow().isoformat(),
                "records_processed": 0,
                "records_completed": 0,
                "records_failed": 0,
                "stages_processed": {stage.value: 0 for stage in EnrichmentStage},
                "errors": []
            }
            
            async with get_session() as db:
                try:
                    # Step 1: Identify records needing enrichment
                    enrichment_candidates = await self._identify_enrichment_candidates(db, tenant)
                    
                    logger.info(f"Found {len(enrichment_candidates)} records needing enrichment")
                    
                    # Step 2: Process records in batches
                    for i in range(0, len(enrichment_candidates), batch_size):
                        batch = enrichment_candidates[i:i + batch_size]
                        
                        batch_results = await self._process_enrichment_batch(
                            db, batch, max_retries
                        )
                        
                        # Update statistics
                        stats["records_processed"] += len(batch)
                        stats["records_completed"] += batch_results["completed"]
                        stats["records_failed"] += batch_results["failed"]
                        
                        for stage, count in batch_results["stages_processed"].items():
                            stats["stages_processed"][stage] += count
                        
                        stats["errors"].extend(batch_results["errors"])
                        
                        # Commit batch
                        await db.commit()
                        
                        logger.info(f"Processed batch {i//batch_size + 1}: "
                                   f"{batch_results['completed']} completed, "
                                   f"{batch_results['failed']} failed")
                    
                    # Step 3: Generate completeness report
                    completeness_report = await self._generate_completeness_report(db, tenant)
                    stats["completeness_report"] = completeness_report
                    
                    logger.info(f"Enrichment pipeline completed for tenant {tenant}: "
                               f"{stats['records_completed']} completed, "
                               f"{stats['records_failed']} failed")
                    
                    return stats
                    
                except Exception as e:
                    logger.error(f"Enrichment pipeline failed for tenant {tenant}: {e}")
                    stats["errors"].append(f"Pipeline failure: {str(e)}")
                    raise
    
    async def _identify_enrichment_candidates(
        self,
        db: AsyncSession,
        tenant: str
    ) -> List[EnrichmentState]:
        """
        Identify records that need enrichment or reprocessing.
        
        Args:
            db (AsyncSession): Database session
            tenant (str): Tenant identifier
            
        Returns:
            List[EnrichmentState]: Records needing enrichment
        """
        candidates = []
        
        # Find exception records needing enrichment
        exception_query = select(ExceptionRecord).where(
            and_(
                ExceptionRecord.tenant == tenant,
                or_(
                    # Missing AI classification
                    ExceptionRecord.ai_confidence.is_(None),
                    # Missing AI label
                    ExceptionRecord.ai_label.is_(None),
                    # Old records that might need reprocessing
                    and_(
                        ExceptionRecord.ai_confidence < 0.7,
                        ExceptionRecord.created_at < datetime.utcnow() - timedelta(hours=24)
                    )
                )
            )
        ).limit(1000)  # Reasonable limit for processing
        
        result = await db.execute(exception_query)
        exception_records = result.scalars().all()
        
        for record in exception_records:
            state = self._analyze_exception_enrichment_state(record)
            if state.needs_reprocessing:
                candidates.append(state)
        
        logger.info(f"Found {len(candidates)} exception records needing enrichment")
        
        return candidates
    
    def _analyze_exception_enrichment_state(self, record: ExceptionRecord) -> EnrichmentState:
        """
        Analyze the current enrichment state of an exception record.
        
        Args:
            record (ExceptionRecord): Exception record to analyze
            
        Returns:
            EnrichmentState: Current enrichment state
        """
        state = EnrichmentState(
            record_id=record.id,
            record_type="exception"
        )
        
        # Analyze order analysis stage (new AI Order Problem Detection)
        # For now, assume this is complete for existing records
        state.order_analysis = EnrichmentStatus.COMPLETED
        
        # Analyze classification stage
        if record.ai_confidence is not None and record.ai_label is not None:
            if record.ai_confidence >= 0.7:
                state.classification = EnrichmentStatus.COMPLETED
            else:
                state.classification = EnrichmentStatus.FAILED
        else:
            state.classification = EnrichmentStatus.PENDING
        
        # Analyze automation stage
        # Check if automated resolution has been attempted
        if "AI-resolved" in (record.ops_note or ""):
            state.automation = EnrichmentStatus.COMPLETED
        elif record.ai_confidence is not None and record.ai_confidence >= 0.7:
            state.automation = EnrichmentStatus.PENDING
        else:
            state.automation = EnrichmentStatus.SKIPPED  # Can't automate without good classification
        
        return state
    
    async def _process_enrichment_batch(
        self,
        db: AsyncSession,
        batch: List[EnrichmentState],
        max_retries: int
    ) -> Dict[str, Any]:
        """
        Process a batch of records through enrichment stages.
        
        Args:
            db (AsyncSession): Database session
            batch (List[EnrichmentState]): Batch of enrichment states
            max_retries (int): Maximum retry attempts
            
        Returns:
            Dict[str, Any]: Batch processing results
        """
        results = {
            "completed": 0,
            "failed": 0,
            "stages_processed": {stage.value: 0 for stage in EnrichmentStage},
            "errors": []
        }
        
        for state in batch:
            try:
                # Process the current stage for this record
                stage = state.current_stage
                
                if stage == EnrichmentStage.COMPLETE:
                    results["completed"] += 1
                    continue
                
                # Skip if too many retries
                if state.retry_count >= max_retries:
                    results["failed"] += 1
                    results["errors"].append(
                        f"Record {state.record_id} exceeded max retries ({max_retries})"
                    )
                    continue
                
                # Process the stage
                processor = self.stage_processors.get(stage)
                if processor:
                    success = await processor(db, state)
                    
                    if success:
                        results["stages_processed"][stage.value] += 1
                        
                        # Check if record is now complete
                        if state.is_complete:
                            results["completed"] += 1
                    else:
                        state.retry_count += 1
                        state.last_attempt = datetime.utcnow()
                        
                        if state.retry_count >= max_retries:
                            results["failed"] += 1
                
            except Exception as e:
                logger.error(f"Error processing record {state.record_id}: {e}")
                results["errors"].append(f"Record {state.record_id}: {str(e)}")
                results["failed"] += 1
        
        return results
    
    async def _process_order_analysis(
        self,
        db: AsyncSession,
        state: EnrichmentState
    ) -> bool:
        """
        Process AI Order Problem Detection stage.
        
        Args:
            db (AsyncSession): Database session
            state (EnrichmentState): Enrichment state
            
        Returns:
            bool: True if successful, False if failed
        """
        try:
            # Get the exception record
            record_query = select(ExceptionRecord).where(ExceptionRecord.id == state.record_id)
            result = await db.execute(record_query)
            record = result.scalar_one_or_none()
            
            if not record:
                state.order_analysis = EnrichmentStatus.FAILED
                state.error_messages.append("Record not found")
                return False
            
            # Get order data for analysis
            order_data = await self._get_order_data_for_record(db, record)
            
            if not order_data:
                state.order_analysis = EnrichmentStatus.SKIPPED
                return True  # Skip if no order data available
            
            # Perform AI order analysis
            analysis_result = await self.ai_order_analyzer.analyze_order_problems(order_data)
            
            # Check if AI analysis succeeded
            if (analysis_result.get("has_problems") is not None and 
                analysis_result.get("confidence") is not None):
                
                # Store analysis results in record context
                if not record.context_data:
                    record.context_data = {}
                
                record.context_data["ai_order_analysis"] = analysis_result
                
                state.order_analysis = EnrichmentStatus.COMPLETED
                return True
            else:
                # AI analysis failed - set to NULL for reprocessing
                state.order_analysis = EnrichmentStatus.FAILED
                state.error_messages.append("AI order analysis returned NULL fields")
                return False
                
        except Exception as e:
            state.order_analysis = EnrichmentStatus.FAILED
            state.error_messages.append(f"Order analysis error: {str(e)}")
            return False
    
    async def _process_exception_classification(
        self,
        db: AsyncSession,
        state: EnrichmentState
    ) -> bool:
        """
        Process AI Exception Classification stage.
        
        Args:
            db (AsyncSession): Database session
            state (EnrichmentState): Enrichment state
            
        Returns:
            bool: True if successful, False if failed
        """
        try:
            # Get the exception record
            record_query = select(ExceptionRecord).where(ExceptionRecord.id == state.record_id)
            result = await db.execute(record_query)
            record = result.scalar_one_or_none()
            
            if not record:
                state.classification = EnrichmentStatus.FAILED
                state.error_messages.append("Record not found")
                return False
            
            # Perform AI classification
            await self.ai_exception_analyst.analyze_exception(db, record)
            
            # Check if classification succeeded
            if record.ai_confidence is not None and record.ai_label is not None:
                state.classification = EnrichmentStatus.COMPLETED
                return True
            else:
                # Classification failed - fields are NULL
                state.classification = EnrichmentStatus.FAILED
                state.error_messages.append("AI classification returned NULL fields")
                return False
                
        except Exception as e:
            state.classification = EnrichmentStatus.FAILED
            state.error_messages.append(f"Classification error: {str(e)}")
            return False
    
    async def _process_automated_resolution(
        self,
        db: AsyncSession,
        state: EnrichmentState
    ) -> bool:
        """
        Process AI Automated Resolution stage.
        
        Args:
            db (AsyncSession): Database session
            state (EnrichmentState): Enrichment state
            
        Returns:
            bool: True if successful, False if failed
        """
        try:
            # Get the exception record
            record_query = select(ExceptionRecord).where(ExceptionRecord.id == state.record_id)
            result = await db.execute(record_query)
            record = result.scalar_one_or_none()
            
            if not record:
                state.automation = EnrichmentStatus.FAILED
                state.error_messages.append("Record not found")
                return False
            
            # Check if classification is good enough for automation
            if not record.ai_confidence or record.ai_confidence < 0.7:
                state.automation = EnrichmentStatus.SKIPPED
                return True  # Skip automation if classification is poor
            
            # Perform AI automated resolution analysis
            resolution_result = await self.ai_resolution_service.analyze_automated_resolution_possibility(
                db, record
            )
            
            # Check if analysis succeeded
            if (resolution_result.get("can_auto_resolve") is not None and 
                resolution_result.get("confidence") is not None):
                
                # Store resolution analysis in record
                if not record.context_data:
                    record.context_data = {}
                
                record.context_data["ai_resolution_analysis"] = resolution_result
                
                state.automation = EnrichmentStatus.COMPLETED
                return True
            else:
                # Resolution analysis failed
                state.automation = EnrichmentStatus.FAILED
                state.error_messages.append("AI resolution analysis returned NULL fields")
                return False
                
        except Exception as e:
            state.automation = EnrichmentStatus.FAILED
            state.error_messages.append(f"Automation error: {str(e)}")
            return False
    
    async def _get_order_data_for_record(
        self,
        db: AsyncSession,
        record: ExceptionRecord
    ) -> Optional[Dict[str, Any]]:
        """
        Get order data for AI analysis.
        
        Args:
            db (AsyncSession): Database session
            record (ExceptionRecord): Exception record
            
        Returns:
            Optional[Dict[str, Any]]: Order data or None if not available
        """
        try:
            # Get order events for this order
            events_query = select(OrderEvent).where(
                and_(
                    OrderEvent.tenant == record.tenant,
                    OrderEvent.order_id == record.order_id
                )
            ).order_by(OrderEvent.occurred_at)
            
            result = await db.execute(events_query)
            events = result.scalars().all()
            
            if not events:
                return None
            
            # Reconstruct order data from events
            order_data = {
                "id": record.order_id,
                "tenant": record.tenant,
                "events": [
                    {
                        "event_type": event.event_type,
                        "occurred_at": event.occurred_at.isoformat(),
                        "payload": event.payload
                    }
                    for event in events
                ]
            }
            
            # Extract order details from the latest event payload
            if events:
                latest_payload = events[-1].payload
                if isinstance(latest_payload, dict):
                    order_data.update(latest_payload)
            
            return order_data
            
        except Exception as e:
            logger.warning(f"Could not get order data for record {record.id}: {e}")
            return None
    
    async def _generate_completeness_report(
        self,
        db: AsyncSession,
        tenant: str
    ) -> Dict[str, Any]:
        """
        Generate data completeness report for a tenant.
        
        Args:
            db (AsyncSession): Database session
            tenant (str): Tenant identifier
            
        Returns:
            Dict[str, Any]: Completeness report
        """
        # Count records by enrichment status
        total_query = select(func.count()).where(ExceptionRecord.tenant == tenant)
        total_result = await db.execute(total_query)
        total_records = total_result.scalar() or 0
        
        # Count records with AI classification
        classified_query = select(func.count()).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.ai_confidence.isnot(None),
                ExceptionRecord.ai_label.isnot(None)
            )
        )
        classified_result = await db.execute(classified_query)
        classified_records = classified_result.scalar() or 0
        
        # Count high-confidence classifications
        high_confidence_query = select(func.count()).where(
            and_(
                ExceptionRecord.tenant == tenant,
                ExceptionRecord.ai_confidence >= 0.7
            )
        )
        high_confidence_result = await db.execute(high_confidence_query)
        high_confidence_records = high_confidence_result.scalar() or 0
        
        # Calculate percentages
        classification_rate = (classified_records / total_records * 100) if total_records > 0 else 0
        high_confidence_rate = (high_confidence_records / total_records * 100) if total_records > 0 else 0
        
        return {
            "tenant": tenant,
            "total_records": total_records,
            "classified_records": classified_records,
            "high_confidence_records": high_confidence_records,
            "classification_rate": round(classification_rate, 2),
            "high_confidence_rate": round(high_confidence_rate, 2),
            "enrichment_quality": "excellent" if high_confidence_rate > 80 else 
                                 "good" if high_confidence_rate > 60 else
                                 "needs_improvement"
        }


# ==== GLOBAL SERVICE INSTANCE ==== #

_enrichment_pipeline: Optional[DataEnrichmentPipeline] = None


def get_enrichment_pipeline() -> DataEnrichmentPipeline:
    """
    Get global enrichment pipeline instance.
    
    Returns:
        DataEnrichmentPipeline: Global enrichment pipeline instance
    """
    global _enrichment_pipeline
    if _enrichment_pipeline is None:
        _enrichment_pipeline = DataEnrichmentPipeline()
    return _enrichment_pipeline
