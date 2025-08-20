# ==== INTELLIGENT BATCHING SYSTEM ==== #

"""
Intelligent batching system for preventing multiple concurrent processing flows.

This module implements smart batching logic that prevents creating hundreds of
parallel flows when multiple records arrive simultaneously. Instead, it
intelligently batches records and creates optimal number of processing flows.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict

from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger
from app.storage.redis import get_redis_client


# ==== MODULE INITIALIZATION ==== #

tracer = get_tracer(__name__)
logger = ContextualLogger(__name__)


# ==== BATCHING DEFINITIONS ==== #

class BatchingStrategy(Enum):
    """Batching strategies for different scenarios."""
    IMMEDIATE = "immediate"        # Process immediately (single record)
    TIME_WINDOW = "time_window"    # Wait for time window to collect batch
    SIZE_THRESHOLD = "size_threshold"  # Wait until batch size reached
    ADAPTIVE = "adaptive"          # Smart adaptive batching


@dataclass
class BatchConfig:
    """Configuration for batching behavior."""
    max_batch_size: int = 50           # Maximum records per batch
    time_window_seconds: int = 10      # Time to wait for more records
    min_batch_size: int = 5            # Minimum size to trigger processing
    max_wait_seconds: int = 30         # Maximum time to wait before forcing processing
    priority_immediate_threshold: int = 1  # Process immediately if <= this many records


@dataclass
class PendingBatch:
    """Represents a batch waiting for processing."""
    tenant: str
    batch_type: str  # "order_analysis", "exception_enrichment", etc.
    records: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    processing_started: bool = False
    
    @property
    def age_seconds(self) -> float:
        """Get age of batch in seconds."""
        return (datetime.utcnow() - self.created_at).total_seconds()
    
    @property
    def size(self) -> int:
        """Get current batch size."""
        return len(self.records)
    
    def add_record(self, record: Dict[str, Any]) -> None:
        """Add record to batch."""
        self.records.append(record)
        self.last_updated = datetime.utcnow()


# ==== INTELLIGENT BATCHING SYSTEM ==== #

class IntelligentBatchingSystem:
    """
    Intelligent batching system to prevent multiple concurrent flows.
    
    Implements smart batching logic that:
    1. Prevents creating hundreds of parallel flows
    2. Optimally batches records based on timing and volume
    3. Ensures critical records are processed immediately
    4. Provides flow deduplication and coordination
    """
    
    def __init__(self, config: Optional[BatchConfig] = None):
        """Initialize the batching system."""
        self.config = config or BatchConfig()
        self.pending_batches: Dict[str, PendingBatch] = {}
        self.active_flows: Set[str] = set()  # Track active flow IDs
        self.batch_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.background_task: Optional[asyncio.Task] = None
        self.running = False
    
    async def start(self) -> None:
        """Start the batching system background processor."""
        self.running = True
        self.background_task = asyncio.create_task(self._background_processor())
        logger.info("Intelligent batching system started")
    
    async def stop(self) -> None:
        """Stop the batching system."""
        self.running = False
        if self.background_task:
            self.background_task.cancel()
            try:
                await self.background_task
            except asyncio.CancelledError:
                pass
        logger.info("Intelligent batching system stopped")
    
    async def add_record_for_processing(
        self,
        tenant: str,
        batch_type: str,
        record: Dict[str, Any],
        priority: str = "normal"
    ) -> Optional[str]:
        """
        Add record for processing with intelligent batching.
        
        Args:
            tenant (str): Tenant identifier
            batch_type (str): Type of processing ("order_analysis", "exception_enrichment")
            record (Dict[str, Any]): Record data to process
            priority (str): Priority level ("immediate", "high", "normal")
            
        Returns:
            Optional[str]: Flow ID if processing started immediately, None if batched
        """
        batch_key = f"{tenant}:{batch_type}"
        
        async with self.batch_locks[batch_key]:
            # Check if immediate processing is needed
            if await self._should_process_immediately(tenant, batch_type, record, priority):
                return await self._start_immediate_processing(tenant, batch_type, [record])
            
            # Add to pending batch
            if batch_key not in self.pending_batches:
                self.pending_batches[batch_key] = PendingBatch(
                    tenant=tenant,
                    batch_type=batch_type
                )
            
            batch = self.pending_batches[batch_key]
            batch.add_record(record)
            
            logger.debug(f"Added record to batch {batch_key} (size: {batch.size})")
            
            # Check if batch should be processed now
            if await self._should_process_batch(batch):
                flow_id = await self._start_batch_processing(batch_key, batch)
                return flow_id
            
            return None  # Record batched, will be processed later
    
    async def _should_process_immediately(
        self,
        tenant: str,
        batch_type: str,
        record: Dict[str, Any],
        priority: str
    ) -> bool:
        """
        Determine if record should be processed immediately.
        
        Args:
            tenant (str): Tenant identifier
            batch_type (str): Processing type
            record (Dict[str, Any]): Record data
            priority (str): Priority level
            
        Returns:
            bool: True if should process immediately
        """
        # Always process critical/high priority immediately
        if priority in ["immediate", "critical"]:
            return True
        
        # Process high-value orders immediately
        if batch_type == "order_analysis":
            order_value = record.get("order_value", 0)
            if order_value > 1000:  # High-value orders
                return True
        
        # Process critical exceptions immediately
        if batch_type == "exception_enrichment":
            severity = record.get("severity", "MEDIUM")
            if severity in ["CRITICAL", "HIGH"]:
                return True
        
        # Check if there's already an active flow for this type
        flow_key = f"{tenant}:{batch_type}"
        if flow_key in self.active_flows:
            return False  # Let existing flow handle it
        
        # Check current system load
        if len(self.active_flows) > 5:  # Too many active flows
            return False
        
        return False
    
    async def _should_process_batch(self, batch: PendingBatch) -> bool:
        """
        Determine if batch should be processed now.
        
        Args:
            batch (PendingBatch): Batch to evaluate
            
        Returns:
            bool: True if batch should be processed
        """
        # Process if batch is full
        if batch.size >= self.config.max_batch_size:
            return True
        
        # Process if time window exceeded
        if batch.age_seconds >= self.config.time_window_seconds:
            return True
        
        # Process if minimum size reached and some time passed
        if (batch.size >= self.config.min_batch_size and 
            batch.age_seconds >= 5):  # At least 5 seconds
            return True
        
        # Force processing if maximum wait time exceeded
        if batch.age_seconds >= self.config.max_wait_seconds:
            return True
        
        return False
    
    async def _start_immediate_processing(
        self,
        tenant: str,
        batch_type: str,
        records: List[Dict[str, Any]]
    ) -> str:
        """
        Start immediate processing for critical records.
        
        Args:
            tenant (str): Tenant identifier
            batch_type (str): Processing type
            records (List[Dict[str, Any]]): Records to process
            
        Returns:
            str: Flow ID
        """
        flow_id = f"{tenant}_{batch_type}_{int(time.time())}_immediate"
        flow_key = f"{tenant}:{batch_type}"
        
        self.active_flows.add(flow_key)
        
        logger.info(f"🚀 Starting immediate processing: {flow_id} ({len(records)} records)")
        
        # Start processing task
        asyncio.create_task(
            self._execute_processing_flow(flow_id, tenant, batch_type, records)
        )
        
        return flow_id
    
    async def _start_batch_processing(
        self,
        batch_key: str,
        batch: PendingBatch
    ) -> str:
        """
        Start batch processing for accumulated records.
        
        Args:
            batch_key (str): Batch identifier
            batch (PendingBatch): Batch to process
            
        Returns:
            str: Flow ID
        """
        flow_id = f"{batch.tenant}_{batch.batch_type}_{int(time.time())}_batch"
        flow_key = f"{batch.tenant}:{batch.batch_type}"
        
        # Mark batch as processing
        batch.processing_started = True
        records = batch.records.copy()
        
        # Remove from pending batches
        del self.pending_batches[batch_key]
        
        # Track active flow
        self.active_flows.add(flow_key)
        
        logger.info(f"📦 Starting batch processing: {flow_id} ({len(records)} records)")
        
        # Start processing task
        asyncio.create_task(
            self._execute_processing_flow(flow_id, batch.tenant, batch.batch_type, records)
        )
        
        return flow_id
    
    async def _execute_processing_flow(
        self,
        flow_id: str,
        tenant: str,
        batch_type: str,
        records: List[Dict[str, Any]]
    ) -> None:
        """
        Execute the actual processing flow.
        
        Args:
            flow_id (str): Flow identifier
            tenant (str): Tenant identifier
            batch_type (str): Processing type
            records (List[Dict[str, Any]]): Records to process
        """
        flow_key = f"{tenant}:{batch_type}"
        
        try:
            logger.info(f"⚙️ Executing {batch_type} flow {flow_id} for {len(records)} records")
            
            # Execute appropriate processing based on batch type
            if batch_type == "order_analysis":
                await self._process_order_analysis_batch(tenant, records)
            elif batch_type == "exception_enrichment":
                await self._process_exception_enrichment_batch(tenant, records)
            else:
                logger.warning(f"Unknown batch type: {batch_type}")
            
            logger.info(f"✅ Completed processing flow {flow_id}")
            
        except Exception as e:
            logger.error(f"❌ Processing flow {flow_id} failed: {e}")
            
        finally:
            # Remove from active flows
            self.active_flows.discard(flow_key)
            
            # Update metrics
            await self._update_flow_metrics(flow_id, batch_type, len(records))
    
    async def _process_order_analysis_batch(
        self,
        tenant: str,
        records: List[Dict[str, Any]]
    ) -> None:
        """
        Process batch of orders for analysis.
        
        Args:
            tenant (str): Tenant identifier
            records (List[Dict[str, Any]]): Order records to analyze
        """
        # This would trigger the order processing pipeline
        # For now, simulate processing
        logger.info(f"🔍 Analyzing {len(records)} orders for tenant {tenant}")
        
        # In real implementation, this would call:
        # from flows.order_processing_flow import order_processing_pipeline
        # await order_processing_pipeline(tenant=tenant, order_batch=records)
        
        # Simulate processing time
        await asyncio.sleep(2)
    
    async def _process_exception_enrichment_batch(
        self,
        tenant: str,
        records: List[Dict[str, Any]]
    ) -> None:
        """
        Process batch of exceptions for AI enrichment.
        
        Args:
            tenant (str): Tenant identifier
            records (List[Dict[str, Any]]): Exception records to enrich
        """
        logger.info(f"🤖 Enriching {len(records)} exceptions for tenant {tenant}")
        
        # In real implementation, this would call:
        # from flows.exception_management_flow import exception_management_pipeline
        # await exception_management_pipeline(tenant=tenant, exception_batch=records)
        
        # Simulate processing time
        await asyncio.sleep(3)
    
    async def _background_processor(self) -> None:
        """
        Background processor to handle batch timeouts and cleanup.
        """
        while self.running:
            try:
                await self._process_expired_batches()
                await self._cleanup_stale_flows()
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Background processor error: {e}")
                await asyncio.sleep(10)  # Wait longer on error
    
    async def _process_expired_batches(self) -> None:
        """Process batches that have exceeded their time limits."""
        expired_batches = []
        
        for batch_key, batch in self.pending_batches.items():
            if not batch.processing_started and await self._should_process_batch(batch):
                expired_batches.append((batch_key, batch))
        
        for batch_key, batch in expired_batches:
            logger.info(f"⏰ Processing expired batch {batch_key} ({batch.size} records)")
            await self._start_batch_processing(batch_key, batch)
    
    async def _cleanup_stale_flows(self) -> None:
        """Clean up stale flow tracking."""
        # In production, this would check actual flow status
        # For now, just log active flows
        if self.active_flows:
            logger.debug(f"Active flows: {len(self.active_flows)} - {list(self.active_flows)}")
    
    async def _update_flow_metrics(
        self,
        flow_id: str,
        batch_type: str,
        record_count: int
    ) -> None:
        """
        Update metrics for completed flow.
        
        Args:
            flow_id (str): Flow identifier
            batch_type (str): Processing type
            record_count (int): Number of records processed
        """
        # Update Prometheus metrics
        # batch_processing_flows_total.labels(batch_type=batch_type).inc()
        # batch_processing_records_total.labels(batch_type=batch_type).inc(record_count)
        
        logger.debug(f"📊 Updated metrics for flow {flow_id}: {record_count} records")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get current batching system status.
        
        Returns:
            Dict[str, Any]: System status information
        """
        return {
            "running": self.running,
            "active_flows": len(self.active_flows),
            "active_flow_keys": list(self.active_flows),
            "pending_batches": len(self.pending_batches),
            "pending_batch_details": {
                key: {
                    "size": batch.size,
                    "age_seconds": batch.age_seconds,
                    "processing_started": batch.processing_started
                }
                for key, batch in self.pending_batches.items()
            },
            "config": {
                "max_batch_size": self.config.max_batch_size,
                "time_window_seconds": self.config.time_window_seconds,
                "min_batch_size": self.config.min_batch_size,
                "max_wait_seconds": self.config.max_wait_seconds
            }
        }


# ==== INTEGRATION WITH TRIGGERS ==== #

class SmartTriggerSystem:
    """
    Smart trigger system that integrates with intelligent batching.
    
    Prevents creating multiple flows by using intelligent batching
    to optimize processing of incoming records.
    """
    
    def __init__(self):
        """Initialize smart trigger system."""
        self.batching_system = IntelligentBatchingSystem()
    
    async def start(self) -> None:
        """Start the smart trigger system."""
        await self.batching_system.start()
        logger.info("Smart trigger system started with intelligent batching")
    
    async def stop(self) -> None:
        """Stop the smart trigger system."""
        await self.batching_system.stop()
        logger.info("Smart trigger system stopped")
    
    async def handle_new_order(self, event_data: Dict[str, Any]) -> None:
        """
        Handle new order with intelligent batching.
        
        Args:
            event_data (Dict[str, Any]): Order event data
        """
        tenant = event_data.get('tenant', 'demo-3pl')
        order_value = event_data.get('order_value', 0)
        
        # Determine priority
        priority = "immediate" if order_value > 1000 else "normal"
        
        flow_id = await self.batching_system.add_record_for_processing(
            tenant=tenant,
            batch_type="order_analysis",
            record=event_data,
            priority=priority
        )
        
        if flow_id:
            logger.info(f"🚀 Started immediate order processing: {flow_id}")
        else:
            logger.info(f"📦 Order batched for processing: {event_data.get('order_id')}")
    
    async def handle_new_exception(self, event_data: Dict[str, Any]) -> None:
        """
        Handle new exception with intelligent batching.
        
        Args:
            event_data (Dict[str, Any]): Exception event data
        """
        tenant = event_data.get('tenant', 'demo-3pl')
        severity = event_data.get('severity', 'MEDIUM')
        
        # Determine priority
        priority = "immediate" if severity in ["CRITICAL", "HIGH"] else "normal"
        
        flow_id = await self.batching_system.add_record_for_processing(
            tenant=tenant,
            batch_type="exception_enrichment",
            record=event_data,
            priority=priority
        )
        
        if flow_id:
            logger.info(f"🚀 Started immediate exception enrichment: {flow_id}")
        else:
            logger.info(f"📦 Exception batched for enrichment: {event_data.get('exception_id')}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get smart trigger system status."""
        return await self.batching_system.get_system_status()


# ==== GLOBAL SERVICE INSTANCE ==== #

_smart_trigger_system: Optional[SmartTriggerSystem] = None


def get_smart_trigger_system() -> SmartTriggerSystem:
    """
    Get global smart trigger system instance.
    
    Returns:
        SmartTriggerSystem: Global smart trigger system instance
    """
    global _smart_trigger_system
    if _smart_trigger_system is None:
        _smart_trigger_system = SmartTriggerSystem()
    return _smart_trigger_system
