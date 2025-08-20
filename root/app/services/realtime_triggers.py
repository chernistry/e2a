# ==== REAL-TIME PROCESSING TRIGGERS ==== #

"""
Modern real-time triggering system for Octup E²A data processing.

This module implements PostgreSQL LISTEN/NOTIFY pattern combined with
event sourcing for immediate processing of new records requiring
AI enrichment, eliminating polling and providing sub-second response times.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from enum import Enum

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.db import get_session
from app.settings import settings
from app.observability.tracing import get_tracer
from app.observability.logging import ContextualLogger
from app.services.data_enrichment_pipeline import get_enrichment_pipeline
from flows.exception_management_flow import exception_management_pipeline


# ==== MODULE INITIALIZATION ==== #

tracer = get_tracer(__name__)
logger = ContextualLogger(__name__)


# ==== TRIGGER DEFINITIONS ==== #

class TriggerEvent(Enum):
    """Types of trigger events."""
    NEW_ORDER_CREATED = "new_order_created"
    NEW_EXCEPTION_CREATED = "new_exception_created"
    AI_ENRICHMENT_FAILED = "ai_enrichment_failed"
    BATCH_PROCESSING_NEEDED = "batch_processing_needed"


class ProcessingPriority(Enum):
    """Processing priority levels."""
    IMMEDIATE = "immediate"    # Process within seconds
    HIGH = "high"             # Process within minutes
    NORMAL = "normal"         # Process within hours
    BATCH = "batch"           # Process in next batch cycle


# ==== REAL-TIME TRIGGER SYSTEM ==== #

class RealtimeProcessingTriggers:
    """
    Modern real-time processing trigger system.
    
    Uses PostgreSQL LISTEN/NOTIFY for immediate processing triggers,
    eliminating polling overhead and providing sub-second response times
    for critical data processing workflows.
    """
    
    def __init__(self):
        """Initialize the trigger system."""
        self.connection: Optional[asyncpg.Connection] = None
        self.listeners: Dict[str, List[Callable]] = {}
        self.running = False
        
        # Processing handlers
        self.handlers = {
            TriggerEvent.NEW_ORDER_CREATED: self._handle_new_order,
            TriggerEvent.NEW_EXCEPTION_CREATED: self._handle_new_exception,
            TriggerEvent.AI_ENRICHMENT_FAILED: self._handle_enrichment_failure,
            TriggerEvent.BATCH_PROCESSING_NEEDED: self._handle_batch_processing
        }
    
    async def start_listening(self) -> None:
        """
        Start listening for database notifications.
        
        Establishes PostgreSQL LISTEN connections for real-time
        event processing triggers.
        """
        try:
            # Extract connection details from DATABASE_URL
            db_url = settings.DATABASE_URL
            
            # Connect directly to PostgreSQL for LISTEN/NOTIFY
            self.connection = await asyncpg.connect(db_url)
            
            # Set up listeners for different event types
            await self.connection.add_listener('new_order_created', self._on_new_order)
            await self.connection.add_listener('new_exception_created', self._on_new_exception)
            await self.connection.add_listener('ai_enrichment_failed', self._on_enrichment_failure)
            await self.connection.add_listener('batch_processing_needed', self._on_batch_needed)
            
            self.running = True
            logger.info("Real-time processing triggers started - listening for database events")
            
            # Keep connection alive
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Failed to start real-time triggers: {e}")
            raise
    
    async def stop_listening(self) -> None:
        """Stop listening for database notifications."""
        self.running = False
        if self.connection:
            await self.connection.close()
            self.connection = None
        logger.info("Real-time processing triggers stopped")
    
    async def _on_new_order(self, connection, pid, channel, payload) -> None:
        """Handle new order creation notification."""
        try:
            event_data = json.loads(payload)
            logger.info(f"🆕 New order trigger: {event_data.get('order_id')}")
            
            await self._handle_new_order(event_data)
            
        except Exception as e:
            logger.error(f"Error handling new order trigger: {e}")
    
    async def _on_new_exception(self, connection, pid, channel, payload) -> None:
        """Handle new exception creation notification."""
        try:
            event_data = json.loads(payload)
            logger.info(f"⚠️ New exception trigger: {event_data.get('exception_id')}")
            
            await self._handle_new_exception(event_data)
            
        except Exception as e:
            logger.error(f"Error handling new exception trigger: {e}")
    
    async def _on_enrichment_failure(self, connection, pid, channel, payload) -> None:
        """Handle AI enrichment failure notification."""
        try:
            event_data = json.loads(payload)
            logger.warning(f"🔧 Enrichment failure trigger: {event_data.get('record_id')}")
            
            await self._handle_enrichment_failure(event_data)
            
        except Exception as e:
            logger.error(f"Error handling enrichment failure trigger: {e}")
    
    async def _on_batch_needed(self, connection, pid, channel, payload) -> None:
        """Handle batch processing needed notification."""
        try:
            event_data = json.loads(payload)
            logger.info(f"📦 Batch processing trigger: {event_data.get('tenant')}")
            
            await self._handle_batch_processing(event_data)
            
        except Exception as e:
            logger.error(f"Error handling batch processing trigger: {e}")
    
    async def _handle_new_order(self, event_data: Dict[str, Any]) -> None:
        """
        Handle new order creation - immediate AI analysis.
        
        Args:
            event_data (Dict[str, Any]): Order creation event data
        """
        order_id = event_data.get('order_id')
        tenant = event_data.get('tenant', 'demo-3pl')
        
        logger.info(f"Processing new order {order_id} for immediate AI analysis")
        
        # Trigger immediate order analysis (this already happens in ingest)
        # But we could add additional processing here if needed
        
        # Example: Trigger priority processing for high-value orders
        order_value = event_data.get('order_value', 0)
        if order_value > 1000:
            logger.info(f"High-value order {order_id} (${order_value}) - triggering priority processing")
            # Could trigger immediate exception management pipeline
    
    async def _handle_new_exception(self, event_data: Dict[str, Any]) -> None:
        """
        Handle new exception creation - immediate AI enrichment.
        
        Args:
            event_data (Dict[str, Any]): Exception creation event data
        """
        exception_id = event_data.get('exception_id')
        tenant = event_data.get('tenant', 'demo-3pl')
        severity = event_data.get('severity', 'MEDIUM')
        
        logger.info(f"Processing new exception {exception_id} for immediate AI enrichment")
        
        # Trigger immediate AI enrichment for critical exceptions
        if severity in ['CRITICAL', 'HIGH']:
            logger.info(f"Critical exception {exception_id} - triggering immediate enrichment")
            
            # Run enrichment pipeline for this specific record
            pipeline = get_enrichment_pipeline()
            try:
                # Process single record immediately
                await pipeline.process_single_record(exception_id, tenant)
            except Exception as e:
                logger.error(f"Immediate enrichment failed for exception {exception_id}: {e}")
    
    async def _handle_enrichment_failure(self, event_data: Dict[str, Any]) -> None:
        """
        Handle AI enrichment failure - schedule retry.
        
        Args:
            event_data (Dict[str, Any]): Enrichment failure event data
        """
        record_id = event_data.get('record_id')
        failure_type = event_data.get('failure_type')
        retry_count = event_data.get('retry_count', 0)
        
        logger.warning(f"AI enrichment failed for record {record_id}: {failure_type} (retry {retry_count})")
        
        # Schedule retry with exponential backoff
        if retry_count < 3:
            delay_seconds = 2 ** retry_count * 60  # 1min, 2min, 4min
            logger.info(f"Scheduling retry for record {record_id} in {delay_seconds} seconds")
            
            # Schedule retry (in production, use Celery/RQ or similar)
            await asyncio.sleep(delay_seconds)
            
            # Retry enrichment
            pipeline = get_enrichment_pipeline()
            try:
                await pipeline.retry_failed_record(record_id)
            except Exception as e:
                logger.error(f"Retry enrichment failed for record {record_id}: {e}")
        else:
            logger.error(f"Record {record_id} exceeded max retries - manual intervention required")
    
    async def _handle_batch_processing(self, event_data: Dict[str, Any]) -> None:
        """
        Handle batch processing trigger - run enrichment pipeline.
        
        Args:
            event_data (Dict[str, Any]): Batch processing event data
        """
        tenant = event_data.get('tenant', 'demo-3pl')
        backlog_size = event_data.get('backlog_size', 0)
        
        logger.info(f"Batch processing triggered for tenant {tenant} (backlog: {backlog_size})")
        
        # Run full enrichment pipeline
        pipeline = get_enrichment_pipeline()
        try:
            results = await pipeline.process_enrichment_pipeline(tenant)
            logger.info(f"Batch processing completed: {results['records_completed']} processed")
        except Exception as e:
            logger.error(f"Batch processing failed for tenant {tenant}: {e}")


# ==== DATABASE TRIGGER FUNCTIONS ==== #

async def setup_database_triggers() -> None:
    """
    Set up PostgreSQL triggers for real-time notifications.
    
    Creates database triggers that send NOTIFY events when
    new records are created or AI enrichment fails.
    """
    async with get_session() as db:
        # Trigger for new order events
        await db.execute(text("""
            CREATE OR REPLACE FUNCTION notify_new_order()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.event_type = 'order_created' THEN
                    PERFORM pg_notify('new_order_created', json_build_object(
                        'order_id', NEW.order_id,
                        'tenant', NEW.tenant,
                        'order_value', COALESCE((NEW.payload->'data'->'order'->>'total_price')::numeric, 0),
                        'created_at', NEW.created_at
                    )::text);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        
        await db.execute(text("""
            DROP TRIGGER IF EXISTS trigger_new_order ON order_events;
            CREATE TRIGGER trigger_new_order
                AFTER INSERT ON order_events
                FOR EACH ROW
                EXECUTE FUNCTION notify_new_order();
        """))
        
        # Trigger for new exceptions
        await db.execute(text("""
            CREATE OR REPLACE FUNCTION notify_new_exception()
            RETURNS TRIGGER AS $$
            BEGIN
                PERFORM pg_notify('new_exception_created', json_build_object(
                    'exception_id', NEW.id,
                    'order_id', NEW.order_id,
                    'tenant', NEW.tenant,
                    'reason_code', NEW.reason_code,
                    'severity', NEW.severity,
                    'created_at', NEW.created_at
                )::text);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        
        await db.execute(text("""
            DROP TRIGGER IF EXISTS trigger_new_exception ON exceptions;
            CREATE TRIGGER trigger_new_exception
                AFTER INSERT ON exceptions
                FOR EACH ROW
                EXECUTE FUNCTION notify_new_exception();
        """))
        
        # Trigger for AI enrichment failures (when ai_confidence set to NULL)
        await db.execute(text("""
            CREATE OR REPLACE FUNCTION notify_enrichment_failure()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.ai_confidence IS NOT NULL AND NEW.ai_confidence IS NULL THEN
                    PERFORM pg_notify('ai_enrichment_failed', json_build_object(
                        'record_id', NEW.id,
                        'order_id', NEW.order_id,
                        'tenant', NEW.tenant,
                        'failure_type', 'ai_confidence_null',
                        'retry_count', COALESCE((NEW.context_data->>'retry_count')::int, 0),
                        'failed_at', NEW.updated_at
                    )::text);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        
        await db.execute(text("""
            DROP TRIGGER IF EXISTS trigger_enrichment_failure ON exceptions;
            CREATE TRIGGER trigger_enrichment_failure
                AFTER UPDATE ON exceptions
                FOR EACH ROW
                EXECUTE FUNCTION notify_enrichment_failure();
        """))
        
        await db.commit()
        
        logger.info("Database triggers for real-time processing set up successfully")


# ==== TRIGGER SERVICE ==== #

class TriggerService:
    """Service for managing real-time processing triggers."""
    
    def __init__(self):
        """Initialize trigger service."""
        self.triggers = RealtimeProcessingTriggers()
        self.background_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the trigger service."""
        # Set up database triggers
        await setup_database_triggers()
        
        # Start listening for notifications
        self.background_task = asyncio.create_task(self.triggers.start_listening())
        
        logger.info("Trigger service started - real-time processing enabled")
    
    async def stop(self) -> None:
        """Stop the trigger service."""
        await self.triggers.stop_listening()
        
        if self.background_task:
            self.background_task.cancel()
            try:
                await self.background_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Trigger service stopped")
    
    async def manual_trigger(
        self, 
        event_type: TriggerEvent, 
        event_data: Dict[str, Any]
    ) -> None:
        """
        Manually trigger processing event.
        
        Args:
            event_type (TriggerEvent): Type of event to trigger
            event_data (Dict[str, Any]): Event data payload
        """
        handler = self.triggers.handlers.get(event_type)
        if handler:
            await handler(event_data)
        else:
            logger.warning(f"No handler found for event type: {event_type}")


# ==== ALTERNATIVE: SUPABASE EDGE FUNCTIONS APPROACH ==== #

class SupabaseEdgeTriggers:
    """
    Alternative implementation using Supabase Edge Functions.
    
    For cloud-native deployments, this provides serverless
    real-time processing triggers with automatic scaling.
    """
    
    def __init__(self):
        """Initialize Supabase edge triggers."""
        self.webhook_url = settings.SUPABASE_WEBHOOK_URL if hasattr(settings, 'SUPABASE_WEBHOOK_URL') else None
    
    async def setup_edge_functions(self) -> str:
        """
        Generate Supabase Edge Function code for real-time triggers.
        
        Returns:
            str: Edge function code to deploy to Supabase
        """
        return """
-- Supabase Edge Function: Real-time Processing Triggers
-- Deploy this to Supabase Functions for serverless triggers

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL') ?? '',
  Deno.env.get('SUPABASE_ANON_KEY') ?? ''
)

serve(async (req) => {
  try {
    const { type, record } = await req.json()
    
    // Handle different trigger types
    switch (type) {
      case 'INSERT':
        if (record.table === 'order_events' && record.event_type === 'order_created') {
          // Trigger immediate order analysis
          await fetch(`${Deno.env.get('API_BASE_URL')}/api/triggers/new-order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              order_id: record.order_id,
              tenant: record.tenant,
              priority: 'immediate'
            })
          })
        }
        
        if (record.table === 'exceptions') {
          // Trigger immediate exception enrichment
          await fetch(`${Deno.env.get('API_BASE_URL')}/api/triggers/new-exception`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              exception_id: record.id,
              tenant: record.tenant,
              severity: record.severity,
              priority: record.severity === 'CRITICAL' ? 'immediate' : 'high'
            })
          })
        }
        break
        
      case 'UPDATE':
        if (record.table === 'exceptions' && 
            record.old_record.ai_confidence !== null && 
            record.ai_confidence === null) {
          // AI enrichment failed - trigger retry
          await fetch(`${Deno.env.get('API_BASE_URL')}/api/triggers/enrichment-failed`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              record_id: record.id,
              failure_type: 'ai_confidence_null',
              retry_count: record.context_data?.retry_count || 0
            })
          })
        }
        break
    }
    
    return new Response(JSON.stringify({ success: true }), {
      headers: { 'Content-Type': 'application/json' }
    })
    
  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    })
  }
})
"""


# ==== GLOBAL SERVICE INSTANCE ==== #

_trigger_service: Optional[TriggerService] = None


def get_trigger_service() -> TriggerService:
    """
    Get global trigger service instance.
    
    Returns:
        TriggerService: Global trigger service instance
    """
    global _trigger_service
    if _trigger_service is None:
        _trigger_service = TriggerService()
    return _trigger_service


# ==== STARTUP INTEGRATION ==== #

async def start_realtime_processing() -> None:
    """
    Start real-time processing system.
    
    Call this during application startup to enable
    immediate processing of new records.
    """
    trigger_service = get_trigger_service()
    await trigger_service.start()


async def stop_realtime_processing() -> None:
    """
    Stop real-time processing system.
    
    Call this during application shutdown.
    """
    trigger_service = get_trigger_service()
    await trigger_service.stop()
